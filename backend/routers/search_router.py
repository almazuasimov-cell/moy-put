"""AI-powered diary search (RAG)."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import get_db
from models import DiaryEntry, User
from schemas import SearchRequest
from auth import get_current_user, get_client_ip
from audit import audit_log
from subscription import check_and_increment_usage, decrement_usage
from prompts import SEARCH_PROMPT
from ai_service import call_deepseek_async

router = APIRouter(tags=["search"])


@router.post("/search")
async def search_diary(
    data: SearchRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = user.id
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
    prompt = SEARCH_PROMPT.format(context=context, query=data.query)
    # Атомарное резервирование лимита прямо перед вызовом ИИ — не
    # check_limit()+increment_usage() отдельными шагами (TOCTOU: два
    # параллельных запроса могли оба пройти проверку раньше коммита,
    # окно гонки тут ещё больше — включает сетевой вызов DeepSeek).
    check_and_increment_usage(user_id, db, "ai_searches")
    try:
        # async, не call_deepseek_sync — синхронная версия с retry на
        # time.sleep() блокировала бы поток из пула на несколько минут
        # при недоступности DeepSeek (3 попытки × таймаут + sleep).
        answer = await call_deepseek_async(prompt, "search", user_id, max_tokens=2000, temperature=0.7)
    except Exception:
        decrement_usage(user_id, db, "ai_searches")  # не наказываем за сбой ИИ
        raise
    audit_log(db, user_id, "search", get_client_ip(request), f"query={data.query[:100]}")
    return {"answer": answer, "entries_count": len(entries)}
