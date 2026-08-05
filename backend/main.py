"""Voice Diary API — «Мой путь» v2.1
Модульная архитектура: config → database → models → services → routers → app.
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import APP_VERSION, IS_POSTGRES, S3_ENABLED
from database import engine, Base

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("voice-diary")

# FastAPI app
app = FastAPI(title="Voice Diary API — Мой путь", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://moy-way.ru", "https://www.moy-way.ru"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and register routers
from routers.auth_router import router as auth_router
from routers.entries_router import router as entries_router
from routers.search_router import router as search_router
from routers.biography_router import router as biography_router
from routers.subscription_router import router as subscription_router
from routers.referral_router import router as referral_router
from routers.stats_router import router as stats_router

app.include_router(auth_router)
app.include_router(entries_router)
app.include_router(search_router)
app.include_router(biography_router)
app.include_router(subscription_router)
app.include_router(referral_router)
app.include_router(stats_router)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    logger.info(f"Voice Diary API v{APP_VERSION} started — {'PostgreSQL' if IS_POSTGRES else 'SQLite'}, S3={'on' if S3_ENABLED else 'off'}")
