"""The background job: file -> pages -> extraction -> validation -> embeddings.

Written as a plain function (not a Celery task) so it can be tested without a broker.
Failure policy:
  * whole-file problems (corrupt, encrypted, unsupported)  -> status=failed + error_code
  * LLM/infrastructure problems                            -> status=failed, retryable via /reprocess
  * embedding problems                                     -> logged, keyword search still works
Every stage writes a processing_event with its duration (history + evaluation metrics)."""
import logging
import time
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import services
from app.db.models import Document, Extraction, Page, ProcessingEvent, ValidationIssue, utcnow
from app.db.ops import revalidate_and_store
from app.db.session import get_sessionmaker
from app.extraction.extractor import ExtractionError, build_source_text, extract_from_document
from app.pipelines import ProcessingError, process_file
from app.pipelines.detect import detect_kind
from app.storage import materialize

log = logging.getLogger(__name__)


def estimate_pages(path: str) -> int | None:
    """Best-effort total so the UI can show a progress bar."""
    try:
        kind = detect_kind(Path(path))
        if kind == "pdf":
            import pymupdf
            with pymupdf.open(path) as d:
                return d.page_count
        if kind in ("jpeg", "png"):
            return 1
        if kind == "tiff":
            from PIL import Image
            with Image.open(path) as im:
                return getattr(im, "n_frames", 1)
    except Exception:
        pass
    return None


def _event(db: Session, doc: Document, stage: str, status: str, detail: str | None = None, t0: float | None = None):
    ms = int((time.perf_counter() - t0) * 1000) if t0 is not None else None
    db.add(ProcessingEvent(document_id=doc.id, stage=stage, status=status, detail=(detail or None) and detail[:2000],
                           duration_ms=ms))


def _fail(db: Session, doc: Document, code: str, message: str, stage: str, t0: float) -> str:
    doc.status, doc.error_code, doc.error_message, doc.finished_at = "failed", code, message[:2000], utcnow()
    _event(db, doc, stage, "failed", f"{code}: {message}", t0)
    db.commit()
    return "failed"


def _reset(db: Session, doc: Document) -> None:
    """Clear derived data so a reprocess starts clean. Events/corrections are kept as history."""
    db.execute(delete(Page).where(Page.document_id == doc.id))
    db.execute(delete(ValidationIssue).where(ValidationIssue.document_id == doc.id))
    db.execute(delete(Extraction).where(Extraction.document_id == doc.id))


def run_pipeline(doc_id: str) -> str:
    with get_sessionmaker()() as db:
        doc = db.get(Document, doc_id)
        if doc is None:
            return "missing"
        with materialize(doc.storage_path, doc.filename) as local_path:
            return _run_pipeline(db, doc, str(local_path))


def _run_pipeline(db: Session, doc: Document, local_path: str) -> str:
    doc_id = doc.id
    if doc is not None:
        _reset(db, doc)
        doc.status, doc.started_at, doc.finished_at = "processing", utcnow(), None
        doc.error_code = doc.error_message = None
        doc.attempts += 1
        doc.pages_done = 0
        doc.page_count = estimate_pages(local_path)
        db.commit()

        # ---- stage 1: read the file (text layer / OCR / spreadsheet) ----
        t0 = time.perf_counter()

        def on_page(p):
            db.add(Page(document_id=doc.id, page_no=p.page_no, label=p.label, method=p.method,
                        confidence=p.confidence, text=p.text, error=p.error, duration_ms=p.duration_ms))
            doc.pages_done += 1
            db.commit()  # commit per page: progress is visible while a big file is processing

        try:
            result = process_file(local_path, original_name=doc.filename, on_page=on_page)
        except ProcessingError as e:
            return _fail(db, doc, e.code, str(e), "processing", t0)
        except Exception as e:  # unexpected bug: record it, never leave the job hanging
            log.exception("processing crashed for %s", doc_id)
            return _fail(db, doc, "internal_error", f"{type(e).__name__}: {e}", "processing", t0)
        doc.kind, doc.warnings = result.kind, result.warnings
        doc.page_count = len(result.pages)
        _event(db, doc, "processing", "ok", f"{len(result.pages)} page(s), status={result.status}", t0)
        db.commit()
        if not any(p.text.strip() for p in result.pages):
            return _fail(db, doc, "no_text_extracted", "No text could be extracted from this file", "processing", t0)

        # ---- stage 2: AI extraction ----
        t0 = time.perf_counter()
        try:
            data = extract_from_document(result, services.get_llm())
        except ExtractionError as e:
            return _fail(db, doc, e.code, str(e), "extraction", t0)
        except Exception as e:
            log.exception("extraction crashed for %s", doc_id)
            return _fail(db, doc, "extraction_failed", f"{type(e).__name__}: {e}", "extraction", t0)
        _event(db, doc, "extraction", "ok", f"tokens={data.get('usage')}", t0)

        # ---- stage 3: validation ----
        t0 = time.perf_counter()
        ext = Extraction(document_id=doc.id, data=data)
        report = revalidate_and_store(db, doc, ext)
        _event(db, doc, "validation", "ok", f"{report.status}: {report.reasons[:3]}", t0)
        db.commit()

        # ---- stage 4: embeddings for semantic search (best effort) ----
        t0 = time.perf_counter()
        try:
            pages = db.execute(select(Page).where(Page.document_id == doc.id, Page.text != "")
                               .order_by(Page.page_no)).scalars().all()
            vectors = services.get_embedder().embed([p.text for p in pages])
            for p, v in zip(pages, vectors):
                p.embedding = v
            _event(db, doc, "embedding", "ok", f"{len(pages)} page(s)", t0)
        except Exception as e:
            log.warning("embedding failed for %s: %s", doc_id, e)
            _event(db, doc, "embedding", "failed", f"{type(e).__name__}: {e}", t0)

        doc.finished_at = utcnow()
        db.commit()
        return doc.status
