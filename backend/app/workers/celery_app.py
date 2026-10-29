from celery import Celery

from app.config import get_settings

s = get_settings()
celery_app = Celery("docintel", broker=s.redis_url, backend=s.redis_url, include=["app.workers.tasks"])
celery_app.conf.update(
    task_acks_late=True,               # a job is only acknowledged after it finishes...
    task_reject_on_worker_lost=True,   # ...so if a worker dies mid-job, the job is redelivered
    worker_prefetch_multiplier=1,      # one long OCR job must not hide other queued jobs
    task_track_started=True,
    task_time_limit=3 * 3600,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
)
