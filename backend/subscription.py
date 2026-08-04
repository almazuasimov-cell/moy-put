"""Subscription management: limits, usage tracking."""
from fastapi import HTTPException
from sqlalchemy.orm import Session
from models import Subscription
from config import FREE_LIMITS, PREMIUM_LIMITS


def get_or_create_subscription(user_id: int, db: Session) -> Subscription:
    sub = db.query(Subscription).filter(Subscription.user_id == user_id).first()
    if not sub:
        sub = Subscription(user_id=user_id, plan="free", status="active")
        db.add(sub)
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
