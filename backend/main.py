"""Voice Diary API — «Мой путь» v2.1
Персональный AI-дневник с голосовым вводом.
Поддерживает SQLite (локально) и PostgreSQL (продакшен).
S3-хранилище для аудиофайлов. 152-ФЗ compliant.
"""
import os
import json
import secrets
import io
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, JSON, ForeignKey, desc, func, Boolean
from sqlalchemy.orm import sessionmaker, Session, declarative_base, relationship
from jose import jwt, JWTError
import bcrypt
from pydantic import BaseModel, Field
import httpx

# ── Logging (аудит — требование 152-ФЗ) ──────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("voice-diary")

# ── Config ────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 дней

# PostgreSQL или SQLite
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./voice_diary.db")

# API keys
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = "https://api.openai.com/v1"

# S3 storage (для аудиофайлов)
S3_ENABLED = os.environ.get("S3_ENABLED", "false").lower() == "true"
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "")
S3_BUCKET = os.environ.get("S3_BUCKET", "voice-diary-audio")
S3_REGION = os.environ.get("S3_REGION", "ru-1")
AUDIO_RETENTION_DAYS = int(os.environ.get("AUDIO_RETENTION_DAYS", "365"))  # 1 год по умолчанию

# S3 client (ленивая инициализация)
_s3_client = None


def get_s3():
    global _s3_client
    if not S3_ENABLED:
        return None
    if _s3_client is None:
        import boto3
        _s3_client = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            region_name=S3_REGION,
        )
        # Создаём бакет если нет
        try:
            _s3_client.head_bucket(Bucket=S3_BUCKET)
        except Exception:
            _s3_client.create_bucket(Bucket=S3_BUCKET)
    return _s3_client


# ── Subscription limits ──────────────────────────────────────
FREE_LIMITS = {
    "voice_entries": 3,
    "biography_generations": 1,
    "ai_searches": 5,
}
PREMIUM_LIMITS = {
    "voice_entries": 999999,
    "biography_generations": 999999,
    "ai_searches": 999999,
}

# ── FastAPI app ──────────────────────────────────────────────
app = FastAPI(title="Voice Diary API — Мой путь", version="2.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Database ──────────────────────────────────────────────────
_is_postgres = DATABASE_URL.startswith("postgresql")
_engine_kwargs = {}
if not _is_postgres:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Models ────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    password_hash = Column(String, default="")
    consent_given = Column(Boolean, default=False)  # Согласие на обработку ПД
    consent_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))


class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    plan = Column(String, default="free")
    status = Column(String, default="active")
    voice_entries_used = Column(Integer, default=0)
    biography_generations_used = Column(Integer, default=0)
    ai_searches_used = Column(Integer, default=0)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))


class DiaryEntry(Base):
    __tablename__ = "diary_entries"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    transcript_text = Column(Text, default="")
    structured_text = Column(Text, default="")
    mood = Column(Integer, default=5)
    tags = Column(JSON, default=list)
    topics = Column(JSON, default=list)
    ai_summary = Column(Text, default="")
    reflection = Column(Text, default="")
    audio_s3_key = Column(String, nullable=True)  # Ключ аудиофайла в S3
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))


class DiaryBiography(Base):
    __tablename__ = "diary_biographies"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    content = Column(Text, default="")
    generated_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))


class AuditLog(Base):
    """Аудит-лог доступа к данным (требование 152-ФЗ)"""
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String, nullable=False)  # login, transcribe, process, search, biography, export_pdf, delete_account
    ip_address = Column(String, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))


# ── Pydantic schemas ──────────────────────────────────────────
class RegisterRequest(BaseModel):
    phone: str
    name: str
    password: str
    consent: bool = False  # Согласие на обработку ПД


class LoginRequest(BaseModel):
    phone: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    name: str
    plan: str = "free"


class DiaryEntryCreate(BaseModel):
    transcript_text: str
    structured_text: str = ""
    mood: int = 5
    tags: list = []
    topics: list = []
    ai_summary: str = ""
    reflection: str = ""


class ProcessRequest(BaseModel):
    text: str


class ProcessResponse(BaseModel):
    mood: int
    tags: list
    topics: list
    structured_text: str
    ai_summary: str
    reflection: str


class SearchRequest(BaseModel):
    query: str


class BiographyUpdate(BaseModel):
    content: str


class SubscriptionInfo(BaseModel):
    plan: str
    status: str
    voice_entries_used: int
    voice_entries_limit: int
    biography_generations_used: int
    biography_generations_limit: int
    ai_searches_used: int
    ai_searches_limit: int
    expires_at: Optional[str] = None


# ── Auth helpers ──────────────────────────────────────────────
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
        return int(user_id)
    except JWTError:
        raise HTTPException(status_code=401, detail="Невалидный токен")


def get_client_ip(request: Request) -> str:
    """Получить IP клиента (для аудит-лога)"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def audit_log(db: Session, user_id: int, action: str, ip: str = "", details: str = ""):
    """Запись в аудит-лог"""
    try:
        log = AuditLog(user_id=user_id, action=action, ip_address=ip, details=details)
        db.add(log)
        db.commit()
        logger.info(f"AUDIT user={user_id} action={action} ip={ip}")
    except Exception as e:
        logger.error(f"Audit log failed: {e}")


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


# ── S3 helpers ────────────────────────────────────────────────
def upload_audio_to_s3(audio_bytes: bytes, user_id: int, filename: str) -> Optional[str]:
    """Загружает аудио в S3, возвращает ключ или None."""
    s3 = get_s3()
    if not s3:
        return None
    try:
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "ogg"
        key = f"audio/{user_id}/{uuid.uuid4().hex}.{ext}"
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=audio_bytes,
            ContentType=f"audio/{ext}",
        )
        logger.info(f"S3 upload: {key}")
        return key
    except Exception as e:
        logger.error(f"S3 upload failed: {e}")
        return None


def delete_audio_from_s3(key: str) -> None:
    """Удаляет аудио из S3."""
    s3 = get_s3()
    if not s3 or not key:
        return
    try:
        s3.delete_object(Bucket=S3_BUCKET, Key=key)
    except Exception as e:
        logger.error(f"S3 delete failed: {e}")


def delete_all_user_audio(user_id: int, db: Session) -> None:
    """Удаляет все аудиофайлы пользователя из S3."""
    s3 = get_s3()
    if not s3:
        return
    entries = db.query(DiaryEntry).filter(
        DiaryEntry.user_id == user_id,
        DiaryEntry.audio_s3_key.isnot(None),
    ).all()
    for e in entries:
        if e.audio_s3_key:
            delete_audio_from_s3(e.audio_s3_key)


# ── Auth endpoints ────────────────────────────────────────────
@app.post("/auth/register", response_model=TokenResponse)
def register(data: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    if not data.consent:
        raise HTTPException(status_code=400, detail="Необходимо согласие на обработку персональных данных")
    existing = db.query(User).filter(User.phone == data.phone).first()
    if existing:
        raise HTTPException(status_code=400, detail="Пользователь с таким телефоном уже существует")
    user = User(
        phone=data.phone,
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
    return TokenResponse(access_token=token, user_id=user.id, name=user.name, plan="free")


@app.post("/auth/login", response_model=TokenResponse)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.phone == data.phone).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный телефон или пароль")
    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    plan = sub.plan if sub else "free"
    token = create_access_token({"sub": str(user.id)})
    audit_log(db, user.id, "login", get_client_ip(request))
    return TokenResponse(access_token=token, user_id=user.id, name=user.name, plan=plan)


# ── DELETE /account — полное удаление (152-ФЗ) ───────────────
@app.delete("/account")
def delete_account(
    request: Request,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Полное удаление аккаунта и всех данных пользователя."""
    ip = get_client_ip(request)

    # Удаляем аудио из S3
    delete_all_user_audio(user_id, db)

    # Удаляем из БД (каскадно: entries, biography, subscription, audit_logs)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Явное удаление связанных записей (для SQLite, где FK не всегда каскадные)
    db.query(DiaryEntry).filter(DiaryEntry.user_id == user_id).delete()
    db.query(DiaryBiography).filter(DiaryBiography.user_id == user_id).delete()
    db.query(Subscription).filter(Subscription.user_id == user_id).delete()
    db.query(AuditLog).filter(AuditLog.user_id == user_id).delete()
    db.delete(user)
    db.commit()

    logger.info(f"ACCOUNT DELETED user={user_id} ip={ip}")
    return {"status": "deleted", "message": "Все ваши данные полностью удалены"}


# ── Subscription endpoints ────────────────────────────────────
@app.get("/subscription", response_model=SubscriptionInfo)
def get_subscription(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    sub = get_or_create_subscription(user_id, db)
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


@app.post("/subscription/upgrade")
def upgrade_subscription(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    sub = get_or_create_subscription(user_id, db)
    sub.plan = "premium"
    sub.status = "active"
    sub.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    db.commit()
    return {"status": "ok", "plan": "premium", "expires_at": sub.expires_at.isoformat()}


# ── STT endpoint ──────────────────────────────────────────────
@app.post("/stt/transcribe")
async def transcribe_audio(
    request: Request,
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OpenAI API ключ не настроен")
    check_limit(user_id, db, "voice_entries")
    ip = get_client_ip(request)
    try:
        audio_bytes = await file.read()

        # Сохраняем аудио в S3 (если настроено)
        s3_key = upload_audio_to_s3(audio_bytes, user_id, file.filename or "audio.ogg")

        # Транскрибация
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{OPENAI_BASE_URL}/audio/transcriptions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                files={"file": (file.filename or "audio.ogg", audio_bytes, file.content_type or "audio/ogg")},
                data={"model": "whisper-1", "language": "ru"},
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Whisper error: {resp.text}")
            result = resp.json()
            text = result.get("text", "")

        increment_usage(user_id, db, "voice_entries")
        audit_log(db, user_id, "transcribe", ip, f"audio_s3_key={s3_key}")

        return {"text": text, "user_id": user_id, "audio_s3_key": s3_key}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка распознавания: {str(e)}")


# ── AI processing ─────────────────────────────────────────────
@app.post("/entries/process", response_model=ProcessResponse)
async def process_entry(
    data: ProcessRequest,
    request: Request,
    user_id: int = Depends(get_current_user),
):
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="DeepSeek API ключ не настроен")
    try:
        prompt = f"""Ты — AI-ассистент дневника «Мой путь». Проанализируй запись пользователя и верни СТРОГО JSON.

Запись: «{data.text}»

Верни JSON с полями:
- mood: число 1-10 (настроение, где 1=ужасное, 10=превосходное)
- tags: массив строк (ключевые теги: духовное, бизнес, семья, здоровье, отношения, финансы, саморазвитие, путешествия, дом, творчество)
- topics: массив строк (конкретные темы из записи, 1-3 шт)
- structured_text: строка (переформулированный текст с исправленной грамматикой и связностью, сохрани смысл и стиль автора)
- ai_summary: строка (краткое саммари 2-3 предложения)
- reflection: строка (один глубокий вопрос для размышления на основе записи)

Верни ТОЛЬКО JSON, без markdown-блоков."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": DEEPSEEK_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 2000,
                },
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=500, detail=f"DeepSeek error: {resp.text}")
            content = resp.json()["choices"][0]["message"]["content"]
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.endswith("```"):
                    content = content[:-3]
            result = json.loads(content)
            return ProcessResponse(
                mood=result.get("mood", 5),
                tags=result.get("tags", []),
                topics=result.get("topics", []),
                structured_text=result.get("structured_text", data.text),
                ai_summary=result.get("ai_summary", ""),
                reflection=result.get("reflection", ""),
            )
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="AI вернул невалидный JSON")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка AI-обработки: {str(e)}")


# ── CRUD: Diary Entries ───────────────────────────────────────
def _entry_out(e: DiaryEntry) -> dict:
    return {
        "id": e.id,
        "user_id": e.user_id,
        "transcript_text": e.transcript_text or "",
        "structured_text": e.structured_text or "",
        "mood": e.mood or 5,
        "tags": e.tags or [],
        "topics": e.topics or [],
        "ai_summary": e.ai_summary or "",
        "reflection": e.reflection or "",
        "audio_s3_key": e.audio_s3_key,
        "created_at": e.created_at.isoformat() if e.created_at else "",
        "updated_at": e.updated_at.isoformat() if e.updated_at else "",
    }


@app.post("/entries")
def create_entry(
    data: DiaryEntryCreate,
    request: Request,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = DiaryEntry(user_id=user_id, **data.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    audit_log(db, user_id, "create_entry", get_client_ip(request), f"entry_id={entry.id}")
    return _entry_out(entry)


@app.get("/entries")
def list_entries(
    user_id: int = Depends(get_current_user),
    date_from: str = "",
    date_to: str = "",
    tag: str = "",
    mood_min: int = 0,
    mood_max: int = 10,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(DiaryEntry).filter(DiaryEntry.user_id == user_id)
    if date_from:
        q = q.filter(DiaryEntry.created_at >= date_from)
    if date_to:
        q = q.filter(DiaryEntry.created_at <= date_to)
    if mood_min > 0:
        q = q.filter(DiaryEntry.mood >= mood_min)
    if mood_max < 10:
        q = q.filter(DiaryEntry.mood <= mood_max)
    entries = q.order_by(desc(DiaryEntry.created_at)).offset(offset).limit(limit).all()
    if tag:
        entries = [e for e in entries if tag in (e.tags or [])]
    return [_entry_out(e) for e in entries]


@app.get("/entries/{entry_id}")
def get_entry(entry_id: int, user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    entry = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id, DiaryEntry.user_id == user_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return _entry_out(entry)


@app.put("/entries/{entry_id}")
def update_entry(
    entry_id: int,
    data: DiaryEntryCreate,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id, DiaryEntry.user_id == user_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    for field in ["transcript_text", "structured_text", "mood", "tags", "topics", "ai_summary", "reflection"]:
        setattr(entry, field, getattr(data, field))
    entry.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(entry)
    return _entry_out(entry)


@app.delete("/entries/{entry_id}")
def delete_entry(
    entry_id: int,
    request: Request,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id, DiaryEntry.user_id == user_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    # Удаляем аудио из S3
    if entry.audio_s3_key:
        delete_audio_from_s3(entry.audio_s3_key)
    db.delete(entry)
    db.commit()
    audit_log(db, user_id, "delete_entry", get_client_ip(request), f"entry_id={entry_id}")
    return {"status": "deleted"}


# ── AI Search (RAG) ───────────────────────────────────────────
@app.post("/search")
def search_diary(
    data: SearchRequest,
    request: Request,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="DeepSeek API ключ не настроен")
    check_limit(user_id, db, "ai_searches")
    entries = (
        db.query(DiaryEntry)
        .filter(DiaryEntry.user_id == user_id)
        .order_by(desc(DiaryEntry.created_at))
        .limit(100)
        .all()
    )
    if not entries:
        return {"answer": "У тебя пока нет записей в дневнике. Начни с первой записи!", "entries_count": 0}
    context_parts = []
    for e in entries:
        date_str = e.created_at.strftime("%d.%m.%Y") if e.created_at else "?"
        context_parts.append(
            f"[{date_str}] Настроение: {e.mood}/10. Теги: {', '.join(e.tags or [])}. {e.structured_text or e.transcript_text}"
        )
    context = "\n\n".join(context_parts)
    prompt = f"""Ты — AI-ассистент дневника «Мой путь». Ответь на вопрос пользователя, используя ТОЛЬКО контекст его дневниковых записей.

КОНТЕКСТ (записи пользователя):
{context}

ВОПРОС: {data.query}

Ответь на русском языке. Если в контексте нет ответа — скажи об этом честно. Будь тёплым и внимательным, как личный дневник."""
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": DEEPSEEK_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 2000,
                },
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=500, detail=f"DeepSeek error: {resp.text}")
            answer = resp.json()["choices"][0]["message"]["content"]
            increment_usage(user_id, db, "ai_searches")
            audit_log(db, user_id, "search", get_client_ip(request), f"query={data.query[:100]}")
            return {"answer": answer, "entries_count": len(entries)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка поиска: {str(e)}")


# ── Biography ─────────────────────────────────────────────────
@app.post("/biography/generate")
def generate_biography(
    request: Request,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="DeepSeek API ключ не настроен")
    check_limit(user_id, db, "biography_generations")
    entries = (
        db.query(DiaryEntry)
        .filter(DiaryEntry.user_id == user_id)
        .order_by(DiaryEntry.created_at.asc())
        .all()
    )
    if not entries:
        raise HTTPException(status_code=400, detail="Нет записей для составления биографии")
    context_parts = []
    for e in entries:
        date_str = e.created_at.strftime("%d.%m.%Y") if e.created_at else "?"
        context_parts.append(f"[{date_str}] {e.structured_text or e.transcript_text}")
    context = "\n\n".join(context_parts)
    prompt = f"""Ты — биограф. Составь черновик биографии на основе дневниковых записей человека.

ЗАПИСИ:
{context}

Напиши биографию в следующей структуре (используй markdown):

## Кто я
(2-3 предложения — самое главное о человеке)

## Мой путь
(хронология ключевых событий и решений)

## Ценности и убеждения
(что важно для этого человека)

## Уроки и инсайты
(чему научился, какие выводы сделал)

## Взгляд в будущее
(к чему стремится, о чём мечтает)

Пиши от первого лица («Я»). Сохрани тёплый, искренний тон. Не придумывай факты, которых нет в записях."""
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": DEEPSEEK_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.8,
                    "max_tokens": 4000,
                },
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=500, detail=f"DeepSeek error: {resp.text}")
            content = resp.json()["choices"][0]["message"]["content"]
            bio = db.query(DiaryBiography).filter(DiaryBiography.user_id == user_id).first()
            if bio:
                bio.content = content
                bio.generated_at = datetime.now(timezone.utc)
                bio.updated_at = datetime.now(timezone.utc)
            else:
                bio = DiaryBiography(user_id=user_id, content=content, generated_at=datetime.now(timezone.utc))
                db.add(bio)
            db.commit()
            increment_usage(user_id, db, "biography_generations")
            audit_log(db, user_id, "biography_generate", get_client_ip(request), f"entries={len(entries)}")
            return {"content": content, "entries_analyzed": len(entries)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации биографии: {str(e)}")


@app.get("/biography")
def get_biography(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    bio = db.query(DiaryBiography).filter(DiaryBiography.user_id == user_id).first()
    if not bio:
        return {"content": "", "generated_at": None}
    return {
        "content": bio.content,
        "generated_at": bio.generated_at.isoformat() if bio.generated_at else None,
    }


@app.put("/biography")
def update_biography(data: BiographyUpdate, user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    bio = db.query(DiaryBiography).filter(DiaryBiography.user_id == user_id).first()
    if bio:
        bio.content = data.content
        bio.updated_at = datetime.now(timezone.utc)
    else:
        bio = DiaryBiography(user_id=user_id, content=data.content)
        db.add(bio)
    db.commit()
    return {"status": "updated"}


# ── PDF Export ────────────────────────────────────────────────
@app.get("/biography/pdf")
def export_biography_pdf(
    request: Request,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bio = db.query(DiaryBiography).filter(DiaryBiography.user_id == user_id).first()
    if not bio or not bio.content:
        raise HTTPException(status_code=404, detail="Биография не найдена. Сначала сгенерируйте её.")

    user = db.query(User).filter(User.id == user_id).first()
    author_name = user.name if user else "Автор"

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.enums import TA_CENTER
    except ImportError:
        raise HTTPException(status_code=500, detail="reportlab не установлен")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"Биография — {author_name}",
        author=author_name,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("CustomTitle", parent=styles["Title"], fontSize=22, spaceAfter=6 * mm, alignment=TA_CENTER)
    subtitle_style = ParagraphStyle("CustomSubtitle", parent=styles["Normal"], fontSize=10, textColor="#666666", alignment=TA_CENTER, spaceAfter=12 * mm)
    body_style = ParagraphStyle("CustomBody", parent=styles["Normal"], fontSize=11, leading=16, spaceAfter=4 * mm)
    h2_style = ParagraphStyle("CustomH2", parent=styles["Heading2"], fontSize=16, spaceBefore=8 * mm, spaceAfter=4 * mm)

    story = []
    story.append(Paragraph("Биография", title_style))
    story.append(Paragraph(f"«Мой путь» — {author_name}", subtitle_style))
    story.append(Spacer(1, 5 * mm))

    for line in bio.content.split("\n"):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 3 * mm))
            continue
        if line.startswith("## "):
            story.append(Paragraph(line[3:], h2_style))
        elif line.startswith("# "):
            story.append(Paragraph(line[2:], title_style))
        else:
            safe_line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe_line, body_style))

    doc.build(story)
    buf.seek(0)

    audit_log(db, user_id, "export_pdf", get_client_ip(request))
    filename = f"biography_{author_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Stats ─────────────────────────────────────────────────────
@app.get("/stats")
def get_stats(user_id: int = Depends(get_current_user), period: str = "month", db: Session = Depends(get_db)):
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
            "total_entries": total,
            "period_entries": 0,
            "avg_mood": 0,
            "mood_trend": [],
            "top_tags": [],
            "streak": 0,
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


# ── Privacy policy ────────────────────────────────────────────
@app.get("/privacy")
def privacy_policy():
    """Политика конфиденциальности (152-ФЗ)"""
    return {
        "title": "Политика конфиденциальности «Мой путь»",
        "version": "1.0",
        "effective_date": "2026-08-04",
        "sections": [
            {
                "title": "1. Какие данные мы собираем",
                "content": "Мы собираем: номер телефона (для авторизации), имя, голосовые записи (аудиофайлы), "
                           "текстовые расшифровки голосовых записей, результаты AI-анализа (настроение, теги, саммари). "
                           "Голос является биометрическим персональным данным и обрабатывается только с вашего явного согласия."
            },
            {
                "title": "2. Цели обработки",
                "content": "Данные используются для: распознавания речи (Whisper API), AI-анализа записей (DeepSeek API), "
                           "генерации биографии, предоставления статистики, улучшения качества сервиса."
            },
            {
                "title": "3. Хранение данных",
                "content": "Все данные хранятся на серверах на территории Российской Федерации. "
                           "Аудиофайлы хранятся в S3-совместимом хранилище (РФ) в течение 1 года, после чего автоматически удаляются. "
                           "Текстовые данные хранятся до момента удаления аккаунта пользователем."
            },
            {
                "title": "4. Передача третьим лицам",
                "content": "Аудиофайлы передаются OpenAI (Whisper API) для распознавания речи. "
                           "Тексты записей передаются DeepSeek API для AI-анализа. "
                           "Мы не передаём ваши данные рекламным сетям и не продаём их."
            },
            {
                "title": "5. Ваши права",
                "content": "Вы имеете право: получить копию всех ваших данных, потребовать исправления неточных данных, "
                           "потребовать полного удаления всех данных (DELETE /account), отозвать согласие на обработку."
            },
            {
                "title": "6. Контакты",
                "content": "По всем вопросам: email поддержки (будет указан при запуске). "
                           "Оператор персональных данных: ИП Аюпов А.Р. (будет уточнено)."
            },
        ],
    }


# ── Health ────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": "Мой путь",
        "version": "2.1.0",
        "db": "postgresql" if _is_postgres else "sqlite",
        "s3_enabled": S3_ENABLED,
    }


# ── Startup ──────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    logger.info(f"✅ Voice Diary API v2.1 started — {'PostgreSQL' if _is_postgres else 'SQLite'}, S3={'on' if S3_ENABLED else 'off'}")
