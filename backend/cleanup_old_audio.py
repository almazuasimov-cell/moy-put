"""Автоудаление аудио старше AUDIO_RETENTION_DAYS (152-ФЗ, политика конфиденциальности).

Политика обещает: "Аудиофайлы хранятся ... в течение 1 года, после чего
автоматически удаляются. Текстовые данные хранятся до момента удаления
аккаунта пользователем." — поэтому удаляется только S3-объект и
обнуляется audio_s3_key, сама запись (текст, настроение, теги) остаётся.

Запускается через system cron (см. установку ниже), как и backup.sh —
в приложении нет отдельного планировщика (Celery/APScheduler), и для
одной ежедневной задачи заводить его не нужно.
"""
import logging
from datetime import datetime, timedelta, timezone

from database import SessionLocal
from models import DiaryEntry
from config import AUDIO_RETENTION_DAYS
from s3_service import delete_audio_from_s3, get_s3
from audit import audit_log

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cleanup_old_audio")


def cleanup_old_audio() -> int:
    if not get_s3():
        logger.info("S3 не настроен — пропуск")
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=AUDIO_RETENTION_DAYS)
    db = SessionLocal()
    deleted = 0
    try:
        entries = (
            db.query(DiaryEntry)
            .filter(DiaryEntry.audio_s3_key.isnot(None), DiaryEntry.created_at < cutoff)
            .all()
        )
        for entry in entries:
            delete_audio_from_s3(entry.audio_s3_key)
            audit_log(
                db, entry.user_id, "audio_auto_deleted", "",
                f"entry_id={entry.id} retention_days={AUDIO_RETENTION_DAYS}",
            )
            entry.audio_s3_key = None
            db.commit()
            deleted += 1
        logger.info(f"Удалено аудио старше {AUDIO_RETENTION_DAYS} дней: {deleted}")
    finally:
        db.close()
    return deleted


if __name__ == "__main__":
    cleanup_old_audio()
