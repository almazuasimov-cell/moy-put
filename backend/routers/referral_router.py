"""Referral program endpoints."""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from models import User, Referral
from schemas import ReferralApplyRequest, ReferralInfo
from auth import get_current_user, get_client_ip
from audit import audit_log
from referral import get_or_create_referral_code
from subscription import grant_premium_days
from config import REFERRAL_PREMIUM_DAYS

logger = logging.getLogger("voice-diary")
router = APIRouter(tags=["referral"])


@router.get("/referral/code")
def get_referral_code(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    code = get_or_create_referral_code(user.id, db)
    return {"code": code}


@router.post("/referral/apply")
def apply_referral_code(
    data: ReferralApplyRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    code = data.code.strip().upper()
    my_code = get_or_create_referral_code(user.id, db)
    if code == my_code:
        raise HTTPException(status_code=400, detail="Нельзя использовать собственный реферальный код")
    inviter = db.query(User).filter(User.referral_code == code).first()
    if not inviter:
        raise HTTPException(status_code=404, detail="Реферальный код не найден")
    existing = db.query(Referral).filter(Referral.invited_id == user.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Вы уже активировали реферальный код ранее")
    # Раньше — 300₽ каждому на баланс; теперь дни Premium (мотивирует
    # пользоваться приложением активнее, а не просто копить деньги).
    BONUS_DAYS = REFERRAL_PREMIUM_DAYS
    referral = Referral(inviter_id=inviter.id, invited_id=user.id, bonus_amount=BONUS_DAYS)
    db.add(referral)
    grant_premium_days(inviter.id, db, BONUS_DAYS)
    sub = grant_premium_days(user.id, db, BONUS_DAYS)
    db.commit()
    audit_log(db, user.id, "referral_apply", get_client_ip(request), f"code={code} inviter={inviter.id}")
    logger.info(f"REFERRAL: user={user.id} applied code={code} from inviter={inviter.id}, bonus={BONUS_DAYS} days each")
    return {
        "status": "ok",
        "bonus_days": BONUS_DAYS,
        "premium_until": sub.expires_at.isoformat() if sub.expires_at else None,
        "message": f"Вам и другу начислено по {BONUS_DAYS} дней Premium!",
    }


@router.get("/referral/stats", response_model=ReferralInfo)
def get_referral_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    code = get_or_create_referral_code(user.id, db)
    refs = db.query(Referral).filter(Referral.inviter_id == user.id).all()
    invited_list = []
    for r in refs:
        invited_user = db.query(User).filter(User.id == r.invited_id).first()
        invited_list.append({
            "name": invited_user.name if invited_user else "?",
            "date": r.created_at.strftime("%d.%m.%Y") if r.created_at else "",
            "bonus": r.bonus_amount,
        })
    # Всего дней Premium, заработанных за рефералов: как приглашающий
    # (сумма по всем приглашённым) + как приглашённый (одна запись, раз
    # чужой код можно применить только один раз).
    inviter_days = db.query(func.sum(Referral.bonus_amount)).filter(Referral.inviter_id == user.id).scalar() or 0
    invited_row = db.query(Referral).filter(Referral.invited_id == user.id).first()
    invited_days = invited_row.bonus_amount if invited_row else 0
    return ReferralInfo(
        code=code,
        premium_days_earned=inviter_days + invited_days,
        invited_count=len(refs),
        referrals=invited_list,
    )
