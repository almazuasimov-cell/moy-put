"""AI service: DeepSeek calls with retry logic."""
import json
import logging
import httpx
from fastapi import HTTPException
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

logger = logging.getLogger("voice-diary")
AI_ERROR_LOG = "/var/log/voice-diary-ai.log"
ai_error_logger = logging.getLogger("voice-diary-ai")
_ai_handler_initialized = False


def _ensure_ai_handler():
    global _ai_handler_initialized
    if _ai_handler_initialized:
        return
    try:
        handler = logging.FileHandler(AI_ERROR_LOG)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        ai_error_logger.addHandler(handler)
        ai_error_logger.setLevel(logging.WARNING)
        _ai_handler_initialized = True
    except PermissionError:
        # Fallback: log to stderr if file not writable (local dev)
        ai_error_logger.setLevel(logging.WARNING)
        _ai_handler_initialized = True


def _log_ai_error(level: str, endpoint: str, user_id: int, attempt: int, error: str):
    _ensure_ai_handler()
    ai_error_logger.log(
        logging.WARNING if level == "WARN" else logging.ERROR,
        f"endpoint={endpoint} user_id={user_id} attempt={attempt} error={error}"
    )


def call_deepseek_sync(prompt: str, endpoint: str, user_id: int, max_tokens: int = 2000, temperature: float = 0.7, timeout: float = 60.0) -> str:
    """Синхронный вызов DeepSeek с 3 попытками."""
    last_error = None
    for attempt in range(1, 4):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(
                    f"{DEEPSEEK_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": DEEPSEEK_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                if resp.status_code != 200:
                    raise Exception(f"DeepSeek HTTP {resp.status_code}: {resp.text[:200]}")
                content = resp.json()["choices"][0]["message"]["content"]
                return content
        except Exception as e:
            last_error = str(e)
            _log_ai_error("WARN", endpoint, user_id, attempt, last_error)
            if attempt < 3:
                import time
                time.sleep(2)
    _log_ai_error("ERROR", endpoint, user_id, 3, f"All retries failed: {last_error}")
    raise HTTPException(status_code=500, detail=f"AI error after 3 retries: {last_error}")


async def call_deepseek_async(prompt: str, endpoint: str, user_id: int, max_tokens: int = 2000, temperature: float = 0.7, timeout: float = 60.0) -> str:
    """Асинхронный вызов DeepSeek с 3 попытками."""
    last_error = None
    for attempt in range(1, 4):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{DEEPSEEK_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": DEEPSEEK_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                if resp.status_code != 200:
                    raise Exception(f"DeepSeek HTTP {resp.status_code}: {resp.text[:200]}")
                content = resp.json()["choices"][0]["message"]["content"]
                return content
        except Exception as e:
            last_error = str(e)
            _log_ai_error("WARN", endpoint, user_id, attempt, last_error)
            if attempt < 3:
                import asyncio
                await asyncio.sleep(2)
    _log_ai_error("ERROR", endpoint, user_id, 3, f"All retries failed: {last_error}")
    raise HTTPException(status_code=500, detail=f"AI error after 3 retries: {last_error}")
