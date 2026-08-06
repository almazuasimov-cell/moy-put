"""Biography generation, CRUD, PDF export."""
import io
import os
from datetime import datetime, timezone
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
from models import DiaryEntry, DiaryBiography, User
from schemas import BiographyUpdate
from auth import get_current_user, get_client_ip
from audit import audit_log
from subscription import check_limit, increment_usage
from prompts import BIOGRAPHY_PROMPT
from ai_service import call_deepseek_sync

router = APIRouter(tags=["biography"])


@router.post("/biography/generate")
def generate_biography(
    request: Request,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
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
    prompt = BIOGRAPHY_PROMPT.format(context=context)
    content = call_deepseek_sync(prompt, "biography_generate", user_id, max_tokens=4000, temperature=0.8, timeout=120.0)
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


@router.get("/biography")
def get_biography(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
    bio = db.query(DiaryBiography).filter(DiaryBiography.user_id == user_id).first()
    if not bio:
        return {"content": "", "generated_at": None}
    return {
        "content": bio.content,
        "generated_at": bio.generated_at.isoformat() if bio.generated_at else None,
    }


@router.put("/biography")
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


@router.get("/biography/pdf")
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
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        raise HTTPException(status_code=500, detail="reportlab не установлен")
    # Стандартные PDF-шрифты (Helvetica и т.п.) не содержат кириллицу —
    # текст показывался квадратиками. DejaVu Sans поддерживает кириллицу
    # полностью, шрифт лежит в репозитории (backend/fonts/), чтобы не
    # зависеть от того, установлен ли он в системе на сервере.
    _fonts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")
    if "DejaVuSans" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DejaVuSans", os.path.join(_fonts_dir, "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", os.path.join(_fonts_dir, "DejaVuSans-Bold.ttf")))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=20 * mm, leftMargin=20 * mm, topMargin=20 * mm, bottomMargin=20 * mm,
        title=f"Биография — {author_name}", author=author_name,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("CustomTitle", parent=styles["Title"], fontName="DejaVuSans-Bold", fontSize=22, spaceAfter=6 * mm, alignment=TA_CENTER)
    subtitle_style = ParagraphStyle("CustomSubtitle", parent=styles["Normal"], fontName="DejaVuSans", fontSize=10, textColor="#666666", alignment=TA_CENTER, spaceAfter=12 * mm)
    body_style = ParagraphStyle("CustomBody", parent=styles["Normal"], fontName="DejaVuSans", fontSize=11, leading=16, spaceAfter=4 * mm)
    h2_style = ParagraphStyle("CustomH2", parent=styles["Heading2"], fontName="DejaVuSans-Bold", fontSize=16, spaceBefore=8 * mm, spaceAfter=4 * mm)
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
    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"biography_{author_name}_{date_str}.pdf"
    # Content-Disposition — заголовок HTTP, поддерживает только Latin-1.
    # Кириллица в имени файла ломала бы ответ 500 (UnicodeEncodeError) —
    # ASCII-запасной вариант + filename* (RFC 6266) для настоящего UTF-8-имени.
    ascii_fallback = f"biography_{date_str}.pdf"
    encoded_filename = quote(filename)
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_fallback}"; '
                f"filename*=UTF-8''{encoded_filename}"
            )
        },
    )
