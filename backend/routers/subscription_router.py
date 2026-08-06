"""Subscription endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import User
from schemas import SubscriptionInfo
from auth import get_current_user
from subscription import get_or_create_subscription
from config import FREE_LIMITS, PREMIUM_LIMITS

router = APIRouter(tags=["subscription"])


@router.get("/subscription", response_model=SubscriptionInfo)
def get_subscription(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sub = get_or_create_subscription(user.id, db)
    limits = PREMIUM_LIMITS if sub.plan == "premium" and sub.status == "active" else FREE_LIMITS
    return SubscriptionInfo(
        plan=sub.plan,
        status=sub.status,
        voice_entries_used=sub.voice_entries_used,
        voice_entries_limit=limits["voice_entries"],
        biography_generations_used=sub.biography_generations_used,
        biography_generations_limit=limits["biography_generations"],
        ai_searches_used=sub.ai_searches_used,
        ai_searches_limit=limits["ai_searches"],
        expires_at=sub.expires_at.isoformat() if sub.expires_at else None,
    )


@router.post("/subscription/upgrade")
def upgrade_subscription(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Оплата ещё не подключена (планируется Т-Банк) — раньше эта ручка
    # выдавала Premium бесплатно любому авторизованному пользователю.
    raise HTTPException(status_code=501, detail="Оплата пока недоступна, скоро подключим")
