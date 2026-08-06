"""RQ/Redis очередь для CPU-тяжёлой транскрипции.

Раньше транскрипция уходила в starlette run_in_threadpool — это снимало
блокировку event loop, но не ограничивало параллелизм: default-пул
starlette допускает много одновременных потоков, которые все вместе
дерутся за 2 vCPU и тормозят друг друга под нагрузкой. Очередь с
фиксированным числом воркер-процессов (см. systemd voice-diary-worker@)
даёт реальный admission control — лишние запросы ждут в очереди, а не
конкурируют за одно и то же ядро одновременно.

API-контракт для клиента не меняется: HTTP-запрос всё так же ждёт
готового результата, просто "под капотом" появилась очередь.
"""
import asyncio
import logging
from typing import Optional
from redis import Redis
from rq import Queue
from rq.job import Job
from config import REDIS_URL

logger = logging.getLogger("voice-diary")

_redis: Optional[Redis] = None
_queue: Optional[Queue] = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(REDIS_URL)
    return _redis


def get_queue() -> Queue:
    global _queue
    if _queue is None:
        _queue = Queue("transcription", connection=get_redis())
    return _queue


class TranscriptionQueueError(Exception):
    """Ошибка воркера при обработке задачи транскрипции."""


class TranscriptionTimeoutError(Exception):
    """Сервер перегружен — задача не обработана воркерами за отведённое время."""


async def enqueue_transcription(audio_bytes: bytes, filename: str, user_id: int, timeout: int = 60) -> dict:
    """Ставит задачу транскрипции в очередь и ждёт результат (polling через Redis,
    локальный round-trip — доли миллисекунды, не блокирует event loop заметно)."""
    queue = get_queue()
    job: Job = queue.enqueue(
        "jobs.transcribe_job",
        audio_bytes, filename, user_id,
        job_timeout=timeout + 30,
        result_ttl=60,
        failure_ttl=60,
    )
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    poll_interval = 0.25
    while loop.time() < deadline:
        job.refresh()
        if job.is_finished:
            return job.return_value()
        if job.is_failed:
            logger.error(f"Transcription job {job.id} failed: {job.exc_info}")
            raise TranscriptionQueueError(job.id)
        await asyncio.sleep(poll_interval)
    raise TranscriptionTimeoutError(job.id)
