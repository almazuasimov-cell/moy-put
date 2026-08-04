"""Diary entries CRUD + AI processing + STT."""
import csv
import io
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
import httpx
from database import get_db
from models import DiaryEntry
from schemas import DiaryEntryCreate, ProcessRequest, ProcessResponse
from auth import get_current_user, get_client_ip
from audit import audit_log
from subscription import check_limit, increment_usage
from s3_service import upload_audio_to_s3, delete_audio_from_s3
from prompts import PROCESS_ENTRY_PROMPT
from ai_service import call_deepseek_async
from stt_service import transcribe_audio as local_transcribe

router = APIRouter(tags=["entries"])


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


@router.post("/stt/transcribe")
async def transcribe_audio(
    request: Request,
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    check_limit(user_id, db, "voice_entries")
    ip = get_client_ip(request)
    try:
        audio_bytes = await file.read()
        s3_key = upload_audio_to_s3(audio_bytes, user_id, file.filename or "audio.ogg")
        text = local_transcribe(audio_bytes, file.filename or "audio.ogg")
        increment_usage(user_id, db, "voice_entries")
        audit_log(db, user_id, "transcribe", ip, f"audio_s3_key={s3_key}")
        return {"text": text, "user_id": user_id, "audio_s3_key": s3_key}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка распознавания: {str(e)}")


@router.post("/entries/process", response_model=ProcessResponse)
async def process_entry(
    data: ProcessRequest,
    request: Request,
    user_id: int = Depends(get_current_user),
):
    try:
        prompt = PROCESS_ENTRY_PROMPT.format(text=data.text)
        content = await call_deepseek_async(prompt, "process_entry", user_id, max_tokens=2000, temperature=0.7)
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


@router.post("/entries")
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


@router.get("/entries")
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


@router.get("/entries/{entry_id}")
def get_entry(entry_id: int, user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    entry = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id, DiaryEntry.user_id == user_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return _entry_out(entry)


@router.put("/entries/{entry_id}")
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


@router.delete("/entries/{entry_id}")
def delete_entry(
    entry_id: int,
    request: Request,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id, DiaryEntry.user_id == user_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    if entry.audio_s3_key:
        delete_audio_from_s3(entry.audio_s3_key)
    db.delete(entry)
    db.commit()
    audit_log(db, user_id, "delete_entry", get_client_ip(request), f"entry_id={entry_id}")
    return {"status": "deleted"}


@router.get("/export")
def export_entries(
    format: str = "json",
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export all user entries as JSON or CSV."""
    entries = db.query(DiaryEntry).filter(
        DiaryEntry.user_id == user_id
    ).order_by(desc(DiaryEntry.created_at)).all()

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "date", "mood", "tags", "topics", "transcript", "structured", "summary", "reflection"])
        for e in entries:
            writer.writerow([
                e.id,
                e.created_at.isoformat() if e.created_at else "",
                e.mood,
                ", ".join(e.tags or []),
                ", ".join(e.topics or []),
                e.transcript_text or "",
                e.structured_text or "",
                e.ai_summary or "",
                e.reflection or "",
            ])
        csv_bytes = output.getvalue().encode("utf-8-sig")
        return StreamingResponse(
            io.BytesIO(csv_bytes),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=my_path_export.csv"},
        )

    # JSON (default)
    data = [_entry_out(e) for e in entries]
    json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(json_bytes),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=my_path_export.json"},
    )
