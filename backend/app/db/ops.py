"""Shared by the worker (first processing) and the API (after a human correction):
combine AI output + corrections, validate, and persist the result."""
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.extraction.schema import SCALAR_FIELDS
from app.extraction.verify import to_decimal
from app.validation.db_index import DBDuplicateIndex
from app.validation.duplicates import key
from app.validation.models import Issue, ValidationReport
from app.validation.validator import validate_invoice

from .models import Document, Extraction, Page, ValidationIssue


def effective_extraction(data: dict, corrected: dict | None) -> dict:
    """AI result with human corrections applied on top. The AI result itself is never modified."""
    eff = {k: (dict(v) if isinstance(v, dict) else v) for k, v in data.items()}
    if not corrected:
        return eff
    review = set(eff.get("needs_review_fields", []))
    for name, value in (corrected.get("fields") or {}).items():
        eff[name] = {"value": value, "confidence": 1.0, "evidence": "manual correction",
                     "status": "ok" if value is not None else "missing", "flags": ["manually_corrected"]}
        review.discard(name)
    if corrected.get("line_items") is not None:
        eff["line_items"] = [{"description": li.get("description"), "quantity": li.get("quantity"),
                              "unit": li.get("unit"), "unit_price": li.get("unit_price"),
                              "line_total": li.get("line_total"), "tax": li.get("tax"),
                              "discount": li.get("discount"), "confidence": 1.0,
                              "evidence": "manual correction", "flags": []} for li in corrected["line_items"]]
        review.discard("line_items")
    eff["needs_review_fields"] = sorted(review)
    return eff


def denormalize(eff: dict) -> dict:
    val = lambda n: (eff.get(n) or {}).get("value")  # noqa: E731
    total: Decimal | None = to_decimal(val("total"))
    return {"supplier_name": (val("supplier_name") or None) and val("supplier_name")[:255],
            "supplier_key": key(val("supplier_name")) or None,
            "invoice_number": (val("invoice_number") or None) and val("invoice_number")[:128],
            "invoice_key": key(val("invoice_number")) or None,
            "invoice_date": val("invoice_date"), "total": total, "currency": val("currency")}


def revalidate_and_store(db: Session, doc: Document, ext: Extraction) -> ValidationReport:
    rows = db.execute(select(Page.text, Page.error).where(Page.document_id == doc.id)
                      .order_by(Page.page_no)).all()
    source_text = "\n\n".join(t for t, _ in rows if t)
    eff = effective_extraction(ext.data, ext.corrected)
    report = validate_invoice(eff, source_text=source_text, doc_id=doc.id, file_hash=doc.file_hash,
                              dup_index=DBDuplicateIndex(db))
    failed_pages = sum(1 for _, e in rows if e)
    if failed_pages:
        report.issues.append(Issue("pages_failed", "warning", f"{failed_pages} page(s) could not be processed",
                                   None, {"count": failed_pages}))
    if any("truncated" in w for w in (ext.data.get("warnings") or [])):
        report.issues.append(Issue("document_truncated", "warning",
                                   "Document is longer than the extraction limit; later content was not analysed"))
    for k, v in denormalize(eff).items():
        setattr(ext, k, v)
    ext.validation = report.to_dict()
    ext.needs_review = report.needs_manual_review
    db.add(ext)
    db.execute(delete(ValidationIssue).where(ValidationIssue.document_id == doc.id))
    db.add_all(ValidationIssue(document_id=doc.id, rule=i.rule, severity=i.severity, field=i.field,
                               message=i.message, details=i.details) for i in report.issues)
    doc.status = "needs_review" if report.needs_manual_review else "completed"
    return report


__all__ = ["effective_extraction", "denormalize", "revalidate_and_store", "SCALAR_FIELDS"]
