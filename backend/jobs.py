"""Функции, выполняемые RQ-воркером (отдельный процесс, не API-процесс).

Импортируется по строке ("jobs.transcribe_job") в queue_service.enqueue_transcription
и напрямую RQ worker'ом при старте — должна быть top-level и без циклических
импортов из routers/.
"""
from s3_service import upload_audio_to_s3
from stt_service import transcribe_audio


def transcribe_job(audio_bytes: bytes, filename: str, user_id: int) -> dict:
    s3_key = upload_audio_to_s3(audio_bytes, user_id, filename)
    text = transcribe_audio(audio_bytes, filename)
    return {"text": text, "audio_s3_key": s3_key}
