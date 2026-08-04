"""Referral program: code generation, application, stats."""
import hashlib
import secrets
from fastapi import HTTPException
from sqlalchemy.orm import Session
from models import User, Referral


def generate_referral_code(user_id: int, name: str) -> str:
    raw = f"{user_id}-{name}-{secrets.token_hex(4)}"
    short_hash = hashlib.sha256(raw.encode()).hexdigest()[:6].upper()
    translit = name.strip().split()[0] if name.strip() else "USER"
    safe_name = "".join(c for c in translit if c.isascii() and c.isalpha())[:4].upper()
    if len(safe_name) < 2:
        safe_name = "USER"
    return f"{safe_name}{short_hash}"


def get_or_create_referral_code(user_id: int, db: Session) -> str:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if user.referral_code:
        return user.referral_code
    code = generate_referral_code(user_id, user.name)
    while db.query(User).filter(User.referral_code == code).first():
        code = generate_referral_code(user_id, user.name)
    user.referral_code = code
    db.commit()
    return code
