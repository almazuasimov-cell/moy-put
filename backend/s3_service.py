"""S3 storage helpers for audio files."""
import uuid
import logging
from typing import Optional
from sqlalchemy.orm import Session
from models import DiaryEntry
from config import S3_ENABLED, S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET, S3_REGION

logger = logging.getLogger("voice-diary")
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
        try:
            _s3_client.head_bucket(Bucket=S3_BUCKET)
        except Exception:
            _s3_client.create_bucket(Bucket=S3_BUCKET)
    return _s3_client


def upload_audio_to_s3(audio_bytes: bytes, user_id: int, filename: str) -> Optional[str]:
    s3 = get_s3()
    if not s3:
        return None
    try:
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "ogg"
        key = f"audio/{user_id}/{uuid.uuid4().hex}.{ext}"
        s3.put_object(Bucket=S3_BUCKET, Key=key, Body=audio_bytes, ContentType=f"audio/{ext}")
        logger.info(f"S3 upload: {key}")
        return key
    except Exception as e:
        logger.error(f"S3 upload failed: {e}")
        return None


def delete_audio_from_s3(key: str) -> None:
    s3 = get_s3()
    if not s3 or not key:
        return
    try:
        s3.delete_object(Bucket=S3_BUCKET, Key=key)
    except Exception as e:
        logger.error(f"S3 delete failed: {e}")


def delete_all_user_audio(user_id: int, db: Session) -> None:
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
