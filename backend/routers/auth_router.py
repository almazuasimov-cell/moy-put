"""Auth endpoints: register, login, delete account."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from database import get_db
from models import User, Subscription, DiaryEntry, DiaryBiography, AuditLog, Referral
from schemas import RegisterRequest, LoginRequest, TokenResponse, PHONE_RE
from auth import hash_password, verify_password, create_access_token, get_current_user, get_client_ip
from audit import audit_log
from s3_service import delete_all_user_audio
import logging

logger = logging.getLogger("voice-diary")
router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=TokenResponse)
def register(data: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    if not data.consent:
        raise HTTPException(status_code=400, detail="Необходимо согласие на обработку персональных данных")
    phone = data.phone.strip()
    if not PHONE_RE.match(phone):
        raise HTTPException(status_code=400, detail="Номер телефона должен состоять из 10-11 цифр")
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Пароль должен быть не короче 8 символов")
    existing = db.query(User).filter(User.phone == phone).first()
    if existing:
        raise HTTPException(status_code=400, detail="Пользователь с таким телефоном уже существует")
    user = User(
        phone=phone,
        name=data.name,
        password_hash=hash_password(data.password),
        consent_given=True,
        consent_date=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    sub = Subscription(user_id=user.id, plan="free", status="active")
    db.add(sub)
    db.commit()
    audit_log(db, user.id, "register", get_client_ip(request))
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token, user_id=user.id, name=user.name, plan="free", balance=0, onboarding_completed=False)


@router.post("/auth/login", response_model=TokenResponse)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.phone == data.phone).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный телефон или пароль")
    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    plan = sub.plan if sub else "free"
    balance = user.balance or 0
    token = create_access_token({"sub": str(user.id)})
    audit_log(db, user.id, "login", get_client_ip(request))
    return TokenResponse(access_token=token, user_id=user.id, name=user.name, plan=plan, balance=balance, onboarding_completed=user.onboarding_completed)


@router.delete("/account")
def delete_account(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = user.id
    ip = get_client_ip(request)
    delete_all_user_audio(user_id, db)
    db.query(DiaryEntry).filter(DiaryEntry.user_id == user_id).delete()
    db.query(DiaryBiography).filter(DiaryBiography.user_id == user_id).delete()
    db.query(Subscription).filter(Subscription.user_id == user_id).delete()
    # Журнал аудита анонимизируем (user_id → NULL), а не стираем — записи
    # об удалении аккаунта, входах и т.п. должны пережить сам аккаунт.
    # Модель уже объявляет ondelete="SET NULL" на этом FK, но полагаться
    # на уровень БД ненадёжно кроссбазово (SQLite не включает FK по
    # умолчанию) — делаем анонимизацию явно в коде.
    db.query(AuditLog).filter(AuditLog.user_id == user_id).update({"user_id": None})
    db.query(Referral).filter(
        (Referral.inviter_id == user_id) | (Referral.invited_id == user_id)
    ).delete()
    db.delete(user)
    db.commit()
    logger.info(f"ACCOUNT DELETED user={user_id} ip={ip}")
    return {"status": "deleted", "message": "Все ваши данные полностью удалены"}


@router.post("/auth/onboarding/complete")
def complete_onboarding(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.onboarding_completed = True
    db.commit()
    return {"status": "ok", "onboarding_completed": True}
