"""Keyword search (PostgreSQL full-text) and semantic search (pgvector cosine similarity)."""
from dataclasses import dataclass

from sqlalchemy import Select, desc, func, literal_column, select
from sqlalchemy.orm import Session

from app.db.models import Document, Extraction, Page


@dataclass
class Filters:
    supplier: str | None = None
    status: str | None = None
    needs_review: bool | None = None
    date_from: str | None = None  # ISO dates compare correctly as strings
    date_to: str | None = None


def _apply(stmt: Select, f: Filters) -> Select:
    if f.supplier:
        stmt = stmt.where(Extraction.supplier_name.icontains(f.supplier, autoescape=True))
    if f.status:
        stmt = stmt.where(Document.status == f.status)
    if f.needs_review is not None:
        stmt = stmt.where(Extraction.needs_review == f.needs_review)
    if f.date_from:
        stmt = stmt.where(Extraction.invoice_date >= f.date_from)
    if f.date_to:
        stmt = stmt.where(Extraction.invoice_date <= f.date_to)
    return stmt


def _row(r, score, snippet, match):
    return {"document_id": r.document_id, "filename": r.filename, "status": r.status, "page_no": getattr(r, "page_no", None),
            "score": round(float(score), 4), "snippet": snippet, "match": match,
            "supplier_name": r.supplier_name, "invoice_number": r.invoice_number,
            "total": float(r.total) if r.total is not None else None, "currency": r.currency}


def keyword_search(db: Session, q: str, f: Filters, limit: int = 20) -> list[dict]:
    tsq = func.websearch_to_tsquery(literal_column("'english'"), q)
    tsv = func.to_tsvector(literal_column("'english'"), Page.text)  # same expression as the GIN index
    snippet = func.ts_headline(literal_column("'english'"), Page.text, tsq,
                               "MaxFragments=1,MaxWords=30,MinWords=10,StartSel=<mark>,StopSel=</mark>")
    base = (select(Page.document_id, Page.page_no, func.ts_rank(tsv, tsq).label("score"), snippet.label("snip"),
                   Document.filename, Document.status, Extraction.supplier_name, Extraction.invoice_number,
                   Extraction.total, Extraction.currency)
            .join(Document, Document.id == Page.document_id)
            .outerjoin(Extraction, Extraction.document_id == Document.id)
            .where(tsv.op("@@")(tsq)))
    rows = db.execute(_apply(base, f).order_by(desc("score")).limit(limit * 5)).all()
    out, seen = [], set()
    for r in rows:
        if r.document_id not in seen:
            seen.add(r.document_id)
            out.append(_row(r, r.score, r.snip, "text"))

    # structured-field matches (invoice numbers like INV-3337 tokenise badly in full-text search)
    fm = (select(Document.id.label("document_id"), Document.filename, Document.status, Extraction.supplier_name,
                 Extraction.invoice_number, Extraction.total, Extraction.currency)
          .join(Extraction, Extraction.document_id == Document.id)
          .where(Extraction.invoice_number.icontains(q, autoescape=True)
                 | Extraction.supplier_name.icontains(q, autoescape=True)
                 | Document.filename.icontains(q, autoescape=True)))
    for r in db.execute(_apply(fm, f).limit(limit)).all():
        if r.document_id not in seen:
            seen.add(r.document_id)
            out.append(_row(r, 0.5, f"{r.supplier_name or ''} {r.invoice_number or ''}".strip(), "field"))
    return out[:limit]


def semantic_search(db: Session, embedder, q: str, f: Filters, limit: int = 20) -> list[dict]:
    vec = embedder.embed([q])[0]
    dist = Page.embedding.cosine_distance(vec)
    base = (select(Page.document_id, Page.page_no, dist.label("distance"), Page.text, Document.filename,
                   Document.status, Extraction.supplier_name, Extraction.invoice_number, Extraction.total,
                   Extraction.currency)
            .join(Document, Document.id == Page.document_id)
            .outerjoin(Extraction, Extraction.document_id == Document.id)
            .where(Page.embedding.is_not(None)))
    rows = db.execute(_apply(base, f).order_by(dist).limit(limit * 5)).all()
    out, seen = [], set()
    for r in rows:
        if r.document_id not in seen:
            seen.add(r.document_id)
            out.append(_row(r, 1 - r.distance, (r.text or "")[:240], "semantic"))
    return out[:limit]
