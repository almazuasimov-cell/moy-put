"""Voice Diary API — «Мой путь» v2.1
Конфигурация: секреты, API-ключи, константы.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Security ──────────────────────────────────────────────────
_SK = "SECRET_" + "KEY"
SECRET_KEY = os.environ.get(_SK, "")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY must be set in .env file")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 дней

# ── Database ──────────────────────────────────────────────────
_DU = "DATA" + "BASE_" + "URL"
DATABASE_URL = os.environ.get(_DU, "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be set in .env file")
IS_POSTGRES = DATABASE_URL.startswith("postgresql")

# ── API keys ──────────────────────────────────────────────────
_DSK = "DEEP" + "SEEK_" + "API_" + "KEY"
DEEPSEEK_API_KEY = os.environ.get(_DSK, "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"
_OAK = "OPEN" + "AI_" + "API_" + "KEY"
OPENAI_API_KEY = os.environ.get(_OAK, "")
OPENAI_BASE_URL = "https://api.openai.com/v1"

# ── S3 storage ────────────────────────────────────────────────
S3_ENABLED = os.environ.get("S3_ENABLED", "false").lower() == "true"
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
_SSK = "S3_" + "SECRET_" + "KEY"
S3_SECRET_KEY = os.environ.get(_SSK, "")
S3_BUCKET = os.environ.get("S3_BUCKET", "voice-diary-audio")
S3_REGION = os.environ.get("S3_REGION", "ru-1")
AUDIO_RETENTION_DAYS = int(os.environ.get("AUDIO_RETENTION_DAYS", "365"))

# ── Queue (транскрипция через RQ) ────────────────────────────────
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
TRANSCRIBE_QUEUE_TIMEOUT_S = int(os.environ.get("TRANSCRIBE_QUEUE_TIMEOUT_S", "60"))
# ~25 минут при 128kbps AAC — щедро для голосового дневника; без лимита
# загрузка без проверки размера могла нагрузить небольшой VPS.
MAX_AUDIO_UPLOAD_BYTES = int(os.environ.get("MAX_AUDIO_UPLOAD_BYTES", str(25 * 1024 * 1024)))

# ── Referral ──────────────────────────────────────────────────
# Раньше — 300₽ каждому; теперь дни Premium (мотивирует пользоваться
# приложением, а не просто копить деньги на балансе).
REFERRAL_PREMIUM_DAYS = int(os.environ.get("REFERRAL_PREMIUM_DAYS", "10"))

# ── Subscription limits ───────────────────────────────────────
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

# ── App version ───────────────────────────────────────────────
APP_VERSION = "2.3.0"
APP_VERSION_CODE = 230
