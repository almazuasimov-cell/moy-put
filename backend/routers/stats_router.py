"""Stats, health, privacy, and app version endpoints."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import get_db
from models import DiaryEntry, User
from auth import get_current_user
from config import APP_VERSION, APP_VERSION_CODE, IS_POSTGRES, S3_ENABLED

router = APIRouter(tags=["stats"])


def _calculate_streak(db: Session, user_id: int) -> int:
    entries = (
        db.query(DiaryEntry)
        .filter(DiaryEntry.user_id == user_id)
        .order_by(desc(DiaryEntry.created_at))
        .limit(365)
        .all()
    )
    if not entries:
        return 0
    streak = 0
    today = datetime.now(timezone.utc).date()
    expected_date = today
    for e in entries:
        entry_date = e.created_at.date() if e.created_at else None
        if not entry_date:
            continue
        if entry_date == expected_date:
            streak += 1
            expected_date = expected_date - timedelta(days=1)
        elif entry_date == expected_date - timedelta(days=1):
            streak += 1
            expected_date = entry_date - timedelta(days=1)
        elif entry_date < expected_date - timedelta(days=1):
            break
    return streak


@router.get("/stats")
def get_stats(user: User = Depends(get_current_user), period: str = "month", db: Session = Depends(get_db)):
    user_id = user.id
    now = datetime.now(timezone.utc)
    if period == "week":
        since = now - timedelta(days=7)
    elif period == "year":
        since = now - timedelta(days=365)
    else:
        since = now - timedelta(days=30)
    entries = (
        db.query(DiaryEntry)
        .filter(DiaryEntry.user_id == user_id, DiaryEntry.created_at >= since)
        .order_by(DiaryEntry.created_at.asc())
        .all()
    )
    total = db.query(DiaryEntry).filter(DiaryEntry.user_id == user_id).count()
    if not entries:
        return {
            "total_entries": total, "period_entries": 0, "avg_mood": 0,
            "mood_trend": [], "top_tags": [], "streak": 0,
        }
    avg_mood = round(sum(e.mood for e in entries) / len(entries), 1)
    mood_trend = [{"date": e.created_at.strftime("%d.%m"), "mood": e.mood} for e in entries]
    tag_counts = {}
    for e in entries:
        for t in e.tags or []:
            tag_counts[t] = tag_counts.get(t, 0) + 1
    top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    streak = _calculate_streak(db, user_id)
    return {
        "total_entries": total,
        "period_entries": len(entries),
        "avg_mood": avg_mood,
        "mood_trend": mood_trend,
        "top_tags": [{"tag": t, "count": c} for t, c in top_tags],
        "streak": streak,
    }


@router.get("/health")
def health():
    return {
        "status": "ok",
        "app": "Мой путь",
        "version": APP_VERSION,
        "db": "postgresql" if IS_POSTGRES else "sqlite",
        "s3_enabled": S3_ENABLED,
    }


@router.get("/app/version")
def app_version():
    return {
        "version": APP_VERSION,
        "version_code": APP_VERSION_CODE,
        "changelog": "На экране входа добавлено заметное уведомление о защите данных по 152-ФЗ, исправлена ссылка на политику конфиденциальности",
        "is_required": False,
        "apk_url": "https://moy-way.ru/apk/app-release.apk",
    }


@router.get("/privacy")
def privacy_policy():
    return {
        "title": "Политика конфиденциальности «Мой путь»",
        "version": "1.0",
        "effective_date": "2026-08-04",
        "sections": [
            {"title": "1. Какие данные мы собираем",
             "content": "Мы собираем: номер телефона (для авторизации), имя, голосовые записи (аудиофайлы), "
                        "текстовые расшифровки голосовых записей, результаты AI-анализа (настроение, теги, саммари). "
                        "Голос является биометрическим персональным данным и обрабатывается только с вашего явного согласия."},
            {"title": "2. Цели обработки",
             "content": "Данные используются для: распознавания речи (Whisper API), AI-анализа записей (DeepSeek API), "
                        "генерации биографии, предоставления статистики, улучшения качества сервиса."},
            {"title": "3. Хранение данных",
             "content": "Все данные хранятся на серверах на территории Российской Федерации. "
                        "Аудиофайлы хранятся в S3-совместимом хранилище (РФ) в течение 1 года, после чего автоматически удаляются. "
                        "Текстовые данные хранятся до момента удаления аккаунта пользователем."},
            {"title": "4. Передача третьим лицам",
             "content": "Аудиофайлы передаются OpenAI (Whisper API) для распознавания речи. "
                        "Тексты записей передаются DeepSeek API для AI-анализа. "
                        "Мы не передаём ваши данные рекламным сетям и не продаём их."},
            {"title": "5. Ваши права",
             "content": "Вы имеете право: получить копию всех ваших данных, потребовать исправления неточных данных, "
                        "потребовать полного удаления всех данных (DELETE /account), отозвать согласие на обработку."},
            {"title": "6. Контакты",
             "content": "По всем вопросам: email поддержки (будет указан при запуске). "
                        "Оператор персональных данных: ИП Аюпов А.Р. (будет уточнено)."},
        ],
    }
