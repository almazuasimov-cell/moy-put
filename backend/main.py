"""
Voice Diary API — «Мой путь»
Локальный бэкенд (WSL), SQLite, полностью независимый.
"""
import os
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, JSON, ForeignKey, desc, func
from sqlalchemy.orm import sessionmaker, Session, declarative_base, relationship
from jose import jwt, JWTError
import bcrypt
from pydantic import BaseModel, Field
import httpx

# ── Config ────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 дней
DATABASE_URL = "sqlite:///./voice_diary.db"

# API keys (из переменных окружения)
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = "https://api.openai.com/v1"

# ── FastAPI app ──────────────────────────────────────────────
app = FastAPI(title="Voice Diary API — Мой путь", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Database ──────────────────────────────────────────────────
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
# bcrypt used directly

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
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

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
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

class DiaryBiography(Base):
    __tablename__ = "diary_biographies"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    content = Column(Text, default="")
    generated_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

# ── Pydantic schemas ──────────────────────────────────────────
class RegisterRequest(BaseModel):
    phone: str
    name: str
    password: str

class LoginRequest(BaseModel):
    phone: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    name: str

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

# ── Auth endpoints ────────────────────────────────────────────
@app.post("/auth/register", response_model=TokenResponse)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.phone == data.phone).first()
    if existing:
        raise HTTPException(status_code=400, detail="Пользователь с таким телефоном уже существует")
    user = User(
        phone=data.phone,
        name=data.name,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token, user_id=user.id, name=user.name)

@app.post("/auth/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.phone == data.phone).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный телефон или пароль")
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token, user_id=user.id, name=user.name)

# ── STT endpoint ──────────────────────────────────────────────
@app.post("/stt/transcribe")
async def transcribe_audio(file: UploadFile = File(...), user_id: int = Depends(get_current_user)):
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OpenAI API ключ не настроен. Установи OPENAI_API_KEY в .env")
    try:
        audio_bytes = await file.read()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{OPENAI_BASE_URL}/audio/transcriptions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                files={"file": (file.filename or "audio.ogg", audio_bytes, file.content_type or "audio/ogg")},
                data={"model": "whisper-1", "language": "ru"}
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Whisper error: {resp.text}")
            result = resp.json()
            return {"text": result.get("text", ""), "user_id": user_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка распознавания: {str(e)}")

# ── AI processing ─────────────────────────────────────────────
@app.post("/entries/process", response_model=ProcessResponse)
async def process_entry(data: ProcessRequest, user_id: int = Depends(get_current_user)):
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="DeepSeek API ключ не настроен. Установи DEEPSEEK_API_KEY в .env")
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
                }
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка AI-обработки: {str(e)}")

# ── CRUD: Diary Entries ───────────────────────────────────────
def _entry_out(e: DiaryEntry) -> dict:
    return {
        "id": e.id, "user_id": e.user_id,
        "transcript_text": e.transcript_text or "",
        "structured_text": e.structured_text or "",
        "mood": e.mood or 5, "tags": e.tags or [],
        "topics": e.topics or [], "ai_summary": e.ai_summary or "",
        "reflection": e.reflection or "",
        "created_at": e.created_at.isoformat() if e.created_at else "",
        "updated_at": e.updated_at.isoformat() if e.updated_at else "",
    }

@app.post("/entries")
def create_entry(data: DiaryEntryCreate, user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    entry = DiaryEntry(user_id=user_id, **data.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _entry_out(entry)

@app.get("/entries")
def list_entries(
    user_id: int = Depends(get_current_user),
    date_from: str = "", date_to: str = "", tag: str = "",
    mood_min: int = 0, mood_max: int = 10,
    limit: int = 50, offset: int = 0,
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
def update_entry(entry_id: int, data: DiaryEntryCreate, user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
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
def delete_entry(entry_id: int, user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    entry = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id, DiaryEntry.user_id == user_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    db.delete(entry)
    db.commit()
    return {"status": "deleted"}

# ── AI Search (RAG) ───────────────────────────────────────────
@app.post("/search")
def search_diary(data: SearchRequest, user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="DeepSeek API ключ не настроен")
    entries = db.query(DiaryEntry).filter(DiaryEntry.user_id == user_id).order_by(desc(DiaryEntry.created_at)).limit(100).all()
    if not entries:
        return {"answer": "У тебя пока нет записей в дневнике. Начни с первой записи!", "entries_count": 0}
    context_parts = []
    for e in entries:
        date_str = e.created_at.strftime("%d.%m.%Y") if e.created_at else "?"
        context_parts.append(f"[{date_str}] Настроение: {e.mood}/10. Теги: {', '.join(e.tags or [])}. {e.structured_text or e.transcript_text}")
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
                json={"model": DEEPSEEK_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 2000}
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=500, detail=f"DeepSeek error: {resp.text}")
            answer = resp.json()["choices"][0]["message"]["content"]
            return {"answer": answer, "entries_count": len(entries)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка поиска: {str(e)}")

# ── Biography ─────────────────────────────────────────────────
@app.post("/biography/generate")
def generate_biography(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="DeepSeek API ключ не настроен")
    entries = db.query(DiaryEntry).filter(DiaryEntry.user_id == user_id).order_by(DiaryEntry.created_at.asc()).all()
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
                json={"model": DEEPSEEK_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.8, "max_tokens": 4000}
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
            return {"content": content, "entries_analyzed": len(entries)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации биографии: {str(e)}")

@app.get("/biography")
def get_biography(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    bio = db.query(DiaryBiography).filter(DiaryBiography.user_id == user_id).first()
    if not bio:
        return {"content": "", "generated_at": None}
    return {"content": bio.content, "generated_at": bio.generated_at.isoformat() if bio.generated_at else None}

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
    entries = db.query(DiaryEntry).filter(DiaryEntry.user_id == user_id, DiaryEntry.created_at >= since).order_by(DiaryEntry.created_at.asc()).all()
    total = db.query(DiaryEntry).filter(DiaryEntry.user_id == user_id).count()
    if not entries:
        return {"total_entries": total, "period_entries": 0, "avg_mood": 0, "mood_trend": [], "top_tags": [], "streak": 0}
    avg_mood = round(sum(e.mood for e in entries) / len(entries), 1)
    mood_trend = [{"date": e.created_at.strftime("%d.%m"), "mood": e.mood} for e in entries]
    tag_counts = {}
    for e in entries:
        for t in (e.tags or []):
            tag_counts[t] = tag_counts.get(t, 0) + 1
    top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    streak = _calculate_streak(db, user_id)
    return {
        "total_entries": total, "period_entries": len(entries),
        "avg_mood": avg_mood, "mood_trend": mood_trend,
        "top_tags": [{"tag": t, "count": c} for t, c in top_tags],
        "streak": streak,
    }

def _calculate_streak(db: Session, user_id: int) -> int:
    entries = db.query(DiaryEntry).filter(DiaryEntry.user_id == user_id).order_by(desc(DiaryEntry.created_at)).limit(365).all()
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

# ── Health ────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "app": "Мой путь", "version": "1.0.0"}

# ── Startup ──────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    print("✅ Voice Diary API started — tables created")
