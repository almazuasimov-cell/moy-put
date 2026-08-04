"""Referral program endpoints."""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from database import get_db
from models import User, Referral
from schemas import ReferralApplyRequest, ReferralInfo
from auth import get_current_user, get_client_ip
from audit import audit_log
from referral import get_or_create_referral_code

logger = logging.getLogger("voice-diary")
router = APIRouter(tags=["referral"])


@router.get("/referral/code")
def get_referral_code(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    code = get_or_create_referral_code(user_id, db)
    return {"code": code}


@router.post("/referral/apply")
def apply_referral_code(
    data: ReferralApplyRequest,
    request: Request,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    code = data.code.strip().upper()
    my_code = get_or_create_referral_code(user_id, db)
    if code == my_code:
        raise HTTPException(status_code=400, detail="Нельзя использовать собственный реферальный код")
    inviter = db.query(User).filter(User.referral_code == code).first()
    if not inviter:
        raise HTTPException(status_code=404, detail="Реферальный код не найден")
    existing = db.query(Referral).filter(Referral.invited_id == user_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Вы уже активировали реферальный код ранее")
    BONUS = 300
    referral = Referral(inviter_id=inviter.id, invited_id=user_id, bonus_amount=BONUS)
    db.add(referral)
    inviter.balance = (inviter.balance or 0) + BONUS
    invited = db.query(User).filter(User.id == user_id).first()
    invited.balance = (invited.balance or 0) + BONUS
    db.commit()
    audit_log(db, user_id, "referral_apply", get_client_ip(request), f"code={code} inviter={inviter.id}")
    logger.info(f"REFERRAL: user={user_id} applied code={code} from inviter={inviter.id}, bonus={BONUS} each")
    return {"status": "ok", "bonus": BONUS, "balance": invited.balance, "message": f"На ваш баланс начислено {BONUS}₽!"}


@router.get("/referral/stats", response_model=ReferralInfo)
def get_referral_stats(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    code = get_or_create_referral_code(user_id, db)
    user = db.query(User).filter(User.id == user_id).first()
    refs = db.query(Referral).filter(Referral.inviter_id == user_id).all()
    invited_list = []
    for r in refs:
        invited_user = db.query(User).filter(User.id == r.invited_id).first()
        invited_list.append({
            "name": invited_user.name if invited_user else "?",
            "date": r.created_at.strftime("%d.%m.%Y") if r.created_at else "",
            "bonus": r.bonus_amount,
        })
    return ReferralInfo(code=code, balance=user.balance or 0, invited_count=len(refs), referrals=invited_list)
