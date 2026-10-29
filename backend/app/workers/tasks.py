from .celery_app import celery_app
from .pipeline import run_pipeline


@celery_app.task(name="process_document")
def process_document(doc_id: str) -> str:
    return run_pipeline(doc_id)
