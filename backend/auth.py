"""Auth helpers: password hashing, JWT, current user dependency."""
from datetime import datetime, timedelta, timezone
from fastapi import Depends, Header, HTTPException, Request
from jose import jwt, JWTError
import bcrypt
from sqlalchemy.orm import Session
from config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from database import get_db
from models import User


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(authorization: str = Header(""), db: Session = Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    token = authorization.split("Bearer ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Невалидный токен")
        user_id = int(user_id)
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Невалидный токен")
    # Токен валиден 30 дней — за это время пользователь мог удалить аккаунт.
    # Без этой проверки удалённый пользователь с ещё живым токеном ловил
    # 500 (IntegrityError) вместо честного 401 на первом же запросе.
    if not db.query(User).filter(User.id == user_id).first():
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return user_id


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
