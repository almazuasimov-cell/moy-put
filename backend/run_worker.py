"""Точка входа для RQ worker-процесса (см. systemd voice-diary-worker@.service).

Запускается отдельным процессом от API (uvicorn) — обрабатывает задачи из
очереди "transcription" (jobs.transcribe_job). Число одновременно
запущенных инстансов этого скрипта = реальный предел параллельных
транскрипций на сервере.
"""
from rq import Worker
from queue_service import get_redis

if __name__ == "__main__":
    worker = Worker(["transcription"], connection=get_redis())
    worker.work()
