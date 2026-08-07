"""Subscription management: limits, usage tracking."""
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Subscription, User
from config import FREE_LIMITS, PREMIUM_LIMITS
from auth import get_current_user


def _aware(dt: datetime) -> datetime:
    """SQLite (в тестах, в отличие от Postgres в проде) не сохраняет
    timezone у DateTime(timezone=True) — значение возвращается naive,
    и сравнение с datetime.now(timezone.utc) падает с TypeError. Считаем
    naive-значения уже UTC (так они и записывались)."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def get_or_create_subscription(user_id: int, db: Session) -> Subscription:
    sub = db.query(Subscription).filter(Subscription.user_id == user_id).first()
    if not sub:
        sub = Subscription(user_id=user_id, plan="free", status="active")
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub
    # expires_at хранился, но нигде не проверялся — Premium, выданный на
    # ограниченный срок (например, за реферала), оставался бы навсегда.
    # Ленивая проверка при каждом обращении к подписке — просрочен → free.
    if sub.plan == "premium" and sub.expires_at and _aware(sub.expires_at) <= datetime.now(timezone.utc):
        sub.plan = "free"
        db.commit()
    return sub


def grant_premium_days(user_id: int, db: Session, days: int) -> Subscription:
    """Продлевает Premium на `days` дней. Если пользователь уже Premium и
    срок ещё не истёк — прибавляет к текущему expires_at (не сбрасывает
    остаток), иначе отсчитывает от текущего момента."""
    sub = get_or_create_subscription(user_id, db)
    now = datetime.now(timezone.utc)
    base = _aware(sub.expires_at) if (sub.expires_at and _aware(sub.expires_at) > now) else now
    sub.plan = "premium"
    sub.status = "active"
    sub.expires_at = base + timedelta(days=days)
    db.commit()
    db.refresh(sub)
    return sub


def check_limit(user_id: int, db: Session, field: str) -> None:
    sub = get_or_create_subscription(user_id, db)
    limits = PREMIUM_LIMITS if sub.plan == "premium" and sub.status == "active" else FREE_LIMITS
    used = getattr(sub, f"{field}_used", 0)
    limit = limits.get(field, 0)
    if used >= limit:
        raise HTTPException(
            status_code=402,
            detail=f"Лимит исчерпан ({field}: {used}/{limit}). Обновите подписку до Premium."
        )


def increment_usage(user_id: int, db: Session, field: str) -> None:
    sub = get_or_create_subscription(user_id, db)
    current = getattr(sub, f"{field}_used", 0)
    setattr(sub, f"{field}_used", current + 1)
    db.commit()


def check_and_increment_usage(user_id: int, db: Session, field: str) -> None:
    """Атомарно проверяет лимит и списывает его одним SQL UPDATE.

    check_limit()+increment_usage() отдельными шагами — гонка (TOCTOU):
    два одновременных запроса (двойной тап, повтор после таймаута) могли
    оба пройти проверку раньше, чем любой из них закоммитит инкремент,
    и превысить лимит. UPDATE ... WHERE used < limit защищён на уровне
    БД (row lock), не может дать false-negative под конкуренцией.
    """
    sub = get_or_create_subscription(user_id, db)
    limits = PREMIUM_LIMITS if sub.plan == "premium" and sub.status == "active" else FREE_LIMITS
    limit = limits.get(field, 0)
    column = getattr(Subscription, f"{field}_used")
    updated = (
        db.query(Subscription)
        .filter(Subscription.id == sub.id, column < limit)
        .update({column.key: column + 1}, synchronize_session=False)
    )
    db.commit()
    if not updated:
        db.refresh(sub)
        used = getattr(sub, f"{field}_used", 0)
        raise HTTPException(
            status_code=402,
            detail=f"Лимит исчерпан ({field}: {used}/{limit}). Обновите подписку до Premium."
        )


def require_quota(field: str, spend: bool = True):
    """FastAPI-зависимость: проверяет лимит `field` ДО выполнения тела роута
    (и, если spend=True, атомарно списывает его) — заменяет собой ручной вызов
    check_limit()/check_and_increment_usage() первой строкой в функции роута.
    Раньше проверку лимита можно было просто забыть добавить в новый
    AI-эндпоинт; теперь она — часть сигнатуры роута, не тело функции.

    Использовать ТОЛЬКО там, где лимит должен расходоваться безусловно при
    каждом вызове (нет ветвления с ранним return ДО списания в исходном коде).
    Если списание должно происходить только при каком-то условии (например,
    "если в дневнике вообще есть записи для анализа" — см. /search,
    /biography/generate) — эта зависимость не подходит, т.к. выполняется
    раньше тела роута и списала бы лимит даже для запроса, который сам роут
    решил бы не тратить. В таких случаях check_and_increment_usage()/
    check_limit() по-прежнему вызываются вручную внутри тела роута.
    """
    def _dependency(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if spend:
            check_and_increment_usage(user.id, db, field)
        else:
            check_limit(user.id, db, field)
        return user
    return _dependency


def decrement_usage(user_id: int, db: Session, field: str) -> None:
    """Компенсация для check_and_increment_usage, когда после резервирования
    квоты сам запрос (например, вызов ИИ) не удался — не наказываем
    пользователя за чужую ошибку (сеть, DeepSeek недоступен и т.п.)."""
    sub = get_or_create_subscription(user_id, db)
    current = getattr(sub, f"{field}_used", 0)
    if current > 0:
        setattr(sub, f"{field}_used", current - 1)
        db.commit()
