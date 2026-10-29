import hashlib
import os
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import services
from app.config import get_settings
from app.db.models import Correction, Document, Extraction, Page, ProcessingEvent, new_id, utcnow
from app.db.ops import effective_extraction, revalidate_and_store
from app.db.session import get_db
from app.extraction.schema import MONEY_FIELDS, SCALAR_FIELDS
from app.extraction.verify import to_decimal
from app.search.search import Filters, keyword_search, semantic_search
from app.workers.tasks import process_document

from .deps import require_api_key

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])
ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".xlsx", ".xls", ".csv"}
READY = {"completed", "needs_review"}


# ------------------------------------------------------------------ helpers
def _safe_name(raw: str | None) -> str:
    name = os.path.basename((raw or "").replace("\\", "/"))
    name = re.sub(r"[\x00-\x1f]", "", name).strip()[:200]
    return name or "unnamed"


def _get(db: Session, doc_id: str) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    return doc


def _enqueue(db: Session, doc: Document) -> None:
    try:
        process_document.delay(doc.id)
    except Exception as e:  # broker down: keep the document, mark retryable instead of losing it
        doc.status, doc.error_code, doc.error_message = "failed", "queue_unavailable", f"{type(e).__name__}: {e}"[:500]
        db.commit()


def _progress(doc: Document) -> dict:
    if doc.status in READY:
        pct = 100
    elif doc.page_count:
        pct = min(99, round(100 * doc.pages_done / doc.page_count)) if doc.status == "processing" else 0
    else:
        pct = None
    return {"pages_done": doc.pages_done, "page_count": doc.page_count, "percent": pct}


def _summary(d: Document, e: Extraction | None) -> dict:
    return {"id": d.id, "filename": d.filename, "status": d.status, "kind": d.kind, "size_bytes": d.size_bytes,
            "progress": _progress(d), "error_code": d.error_code, "created_at": d.created_at,
            "supplier_name": e.supplier_name if e else None, "invoice_number": e.invoice_number if e else None,
            "invoice_date": e.invoice_date if e else None,
            "total": float(e.total) if e and e.total is not None else None,
            "currency": e.currency if e else None, "needs_review": e.needs_review if e else None}


# ------------------------------------------------------------------ upload
@router.post("/documents", status_code=202)
def upload_documents(files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    s = get_settings()
    if not files:
        raise HTTPException(400, "No files provided")
    if len(files) > s.max_files_per_request:
        raise HTTPException(413, f"At most {s.max_files_per_request} files per request")
    storage = Path(s.storage_dir)
    storage.mkdir(parents=True, exist_ok=True)
    max_bytes, results = s.max_upload_mb * 1024 * 1024, []

    for up in files:
        name = _safe_name(up.filename)
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_EXT:
            results.append({"filename": name, "status": "rejected", "error": "unsupported_extension"})
            continue
        doc_id = new_id()
        dest = storage / f"{doc_id}{ext}"  # server-generated name: user input never touches the path
        sha, size, too_big = hashlib.sha256(), 0, False
        with dest.open("wb") as out:
            while chunk := up.file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    too_big = True
                    break
                sha.update(chunk)
                out.write(chunk)
        if too_big or size == 0:
            dest.unlink(missing_ok=True)
            results.append({"filename": name, "status": "rejected",
                            "error": "file_too_large" if too_big else "empty_file"})
            continue
        doc = Document(id=doc_id, filename=name, file_hash=sha.hexdigest(), size_bytes=size,
                       storage_path=str(dest), status="queued", warnings=[])
        db.add(doc)
        db.commit()
        _enqueue(db, doc)
        db.refresh(doc)
        results.append({"id": doc.id, "filename": name, "status": doc.status, "error": doc.error_code})
    return {"documents": results}


# ------------------------------------------------------------------ read
@router.get("/documents")
def list_documents(status: str | None = None, q: str | None = None, needs_review: bool | None = None,
                   limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    base = select(Document, Extraction).outerjoin(Extraction, Extraction.document_id == Document.id)
    if status:
        base = base.where(Document.status.in_(status.split(",")))
    if needs_review is not None:
        base = base.where(Extraction.needs_review == needs_review)
    if q:
        base = base.where(Document.filename.icontains(q, autoescape=True)
                          | Extraction.invoice_number.icontains(q, autoescape=True)
                          | Extraction.supplier_name.icontains(q, autoescape=True))
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.execute(base.order_by(Document.created_at.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "items": [_summary(d, e) for d, e in rows]}


@router.get("/documents/{doc_id}")
def document_detail(doc_id: str, db: Session = Depends(get_db)):
    doc = _get(db, doc_id)
    out = _summary(doc, doc.extraction)
    out.update({"error_message": doc.error_message, "attempts": doc.attempts, "warnings": doc.warnings,
                "started_at": doc.started_at, "finished_at": doc.finished_at, "file_hash": doc.file_hash,
                "history": [{"stage": e.stage, "status": e.status, "detail": e.detail, "duration_ms": e.duration_ms,
                             "at": e.created_at} for e in doc.events]})
    return out


@router.get("/documents/{doc_id}/result")
def document_result(doc_id: str, db: Session = Depends(get_db)):
    doc = _get(db, doc_id)
    if doc.status in ("queued", "processing"):
        raise HTTPException(409, "Document is still being processed")
    ext = doc.extraction
    if ext is None:  # failed before extraction finished
        return {"document_id": doc.id, "status": doc.status, "error_code": doc.error_code,
                "error_message": doc.error_message, "extraction_ai": None, "corrections": None,
                "effective": None, "validation": None}
    return {"document_id": doc.id, "status": doc.status, "extraction_ai": ext.data, "corrections": ext.corrected,
            "effective": effective_extraction(ext.data, ext.corrected), "validation": ext.validation}


@router.get("/documents/{doc_id}/pages")
def document_pages(doc_id: str, limit: int = Query(20, ge=1, le=200), offset: int = Query(0, ge=0),
                   db: Session = Depends(get_db)):
    _get(db, doc_id)
    rows = db.execute(select(Page).where(Page.document_id == doc_id).order_by(Page.page_no)
                      .limit(limit).offset(offset)).scalars().all()
    return {"items": [{"page_no": p.page_no, "label": p.label, "method": p.method, "confidence": p.confidence,
                       "text": p.text, "error": p.error, "duration_ms": p.duration_ms} for p in rows]}


# ------------------------------------------------------------------ manual corrections
class LineItemIn(BaseModel):
    description: str | None = Field(default=None, max_length=500)
    quantity: str | None = None
    unit: str | None = Field(default=None, max_length=32)
    unit_price: str | None = None
    line_total: str | None = None


class CorrectionIn(BaseModel):
    fields: dict[str, str | None] = Field(default_factory=dict)
    line_items: list[LineItemIn] | None = None
    note: str | None = Field(default=None, max_length=1000)


def _clean_field(name: str, value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    v = str(value).strip()
    if name in MONEY_FIELDS:
        d = to_decimal(v)
        if d is None:
            raise HTTPException(422, f"'{name}' must be a plain decimal number (e.g. 1150.50)")
        return format(d, "f")
    if name == "invoice_date":
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(422, "'invoice_date' must be a real date in YYYY-MM-DD format")
        return v
    if name == "currency":
        if not re.fullmatch(r"[A-Za-z]{3}", v):
            raise HTTPException(422, "'currency' must be a 3-letter ISO code (e.g. USD)")
        return v.upper()
    return v[:255]


@router.patch("/documents/{doc_id}/corrections")
def correct_document(doc_id: str, body: CorrectionIn, db: Session = Depends(get_db)):
    doc = _get(db, doc_id)
    ext = doc.extraction
    if doc.status not in READY or ext is None:
        raise HTTPException(409, "Only processed documents can be corrected")
    unknown = set(body.fields) - set(SCALAR_FIELDS)
    if unknown:
        raise HTTPException(422, f"Unknown field(s): {sorted(unknown)}")
    new_fields = {k: _clean_field(k, v) for k, v in body.fields.items()}
    new_items = None
    if body.line_items is not None:
        new_items = []
        for li in body.line_items:
            item = li.model_dump()
            for k in ("quantity", "unit_price", "line_total"):
                if item[k] is not None:
                    d = to_decimal(item[k])
                    if d is None:
                        raise HTTPException(422, f"line item '{k}' must be a plain decimal number")
                    item[k] = format(d, "f")
            new_items.append(item)

    before = effective_extraction(ext.data, ext.corrected)
    for name, new in new_fields.items():
        old = (before.get(name) or {}).get("value")
        if old != new:
            db.add(Correction(document_id=doc.id, field=name, old_value=old, new_value=new, note=body.note))
    if new_items is not None:
        db.add(Correction(document_id=doc.id, field="line_items", old_value=None,
                          new_value=f"{len(new_items)} item(s)", note=body.note))
    merged = dict(ext.corrected or {})
    merged["fields"] = {**(merged.get("fields") or {}), **new_fields}
    if new_items is not None:
        merged["line_items"] = new_items
    ext.corrected = merged  # new dict object so the JSONB change is detected
    report = revalidate_and_store(db, doc, ext)
    db.add(ProcessingEvent(document_id=doc.id, stage="correction", status="ok",
                           detail=f"fields={sorted(new_fields)} -> {report.status}"))
    db.commit()
    return document_result(doc_id, db)


@router.post("/documents/{doc_id}/approve")
def approve_document(doc_id: str, db: Session = Depends(get_db)):
    """A human reviewer signs off a flagged document (e.g. a missing currency that is genuinely absent)."""
    doc = _get(db, doc_id)
    if doc.status != "needs_review" or doc.extraction is None:
        raise HTTPException(409, "Only documents in 'needs_review' can be approved")
    doc.status, doc.extraction.needs_review = "completed", False
    db.add(ProcessingEvent(document_id=doc.id, stage="review", status="ok", detail="approved by reviewer"))
    db.commit()
    return _summary(doc, doc.extraction)


# ------------------------------------------------------------------ reprocessing
def _requeue(db: Session, doc: Document) -> None:
    doc.status, doc.error_code, doc.error_message, doc.finished_at = "queued", None, None, None
    db.commit()
    _enqueue(db, doc)


@router.post("/documents/{doc_id}/reprocess", status_code=202)
def reprocess_document(doc_id: str, force: bool = False, db: Session = Depends(get_db)):
    doc = _get(db, doc_id)
    if doc.status in ("queued", "processing"):
        raise HTTPException(409, "Document is already being processed")
    if doc.status != "failed" and not force:
        raise HTTPException(409, "Only failed documents are reprocessed by default; pass force=true to redo "
                                 "a finished one (this discards its AI result and corrections)")
    _requeue(db, doc)
    db.refresh(doc)
    return _summary(doc, doc.extraction)


@router.post("/documents/reprocess-failed", status_code=202)
def reprocess_failed(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    docs = db.execute(select(Document).where(Document.status == "failed").order_by(Document.created_at)
                      .limit(limit)).scalars().all()
    for d in docs:
        _requeue(db, d)
    return {"requeued": len(docs), "ids": [d.id for d in docs]}


# ------------------------------------------------------------------ search + stats
@router.get("/search")
def search(q: str = Query(..., min_length=2, max_length=300), mode: str = Query("keyword", pattern="^(keyword|semantic)$"),
           supplier: str | None = None, status: str | None = None, needs_review: bool | None = None,
           date_from: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
           date_to: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
           limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    f = Filters(supplier, status, needs_review, date_from, date_to)
    if mode == "keyword":
        results = keyword_search(db, q, f, limit)
    else:
        try:
            results = semantic_search(db, services.get_embedder(), q, f, limit)
        except Exception as e:
            raise HTTPException(503, f"Semantic search unavailable: {type(e).__name__}")
    return {"query": q, "mode": mode, "results": results}


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Document.status, func.count()).group_by(Document.status)).all())
    secs = func.extract("epoch", Document.finished_at - Document.started_at)
    avg, p50, p95 = db.execute(select(func.avg(secs), func.percentile_cont(0.5).within_group(secs),
                                      func.percentile_cont(0.95).within_group(secs))
                               .where(Document.finished_at.is_not(None), Document.status != "failed")).one()
    ok = counts.get("completed", 0) + counts.get("needs_review", 0)
    finished = ok + counts.get("failed", 0)
    r = lambda x: None if x is None else round(float(x), 3)  # noqa: E731
    return {"counts": counts, "total": sum(counts.values()),
            "success_rate": round(ok / finished, 4) if finished else None,
            "failure_rate": round(counts.get("failed", 0) / finished, 4) if finished else None,
            "processing_seconds": {"avg": r(avg), "p50": r(p50), "p95": r(p95)}}
