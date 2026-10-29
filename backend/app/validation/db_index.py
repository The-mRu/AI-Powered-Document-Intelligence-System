"""PostgreSQL-backed DuplicateIndex (same interface as the in-memory one from Task 3).
IMPORTANT: invoice-number and amount/date matches only count within the SAME supplier."""
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.models import Document, Extraction

from .duplicates import DuplicateRecord


class DBDuplicateIndex:
    def __init__(self, db: Session):
        self.db = db

    def candidates(self, r: DuplicateRecord) -> list[DuplicateRecord]:
        out: list[DuplicateRecord] = []
        seen: set[str] = set()
        if r.file_hash:
            for row in self.db.execute(select(Document.id, Document.file_hash).where(
                    Document.file_hash == r.file_hash, Document.id != r.doc_id)):
                out.append(DuplicateRecord(row.id, row.file_hash, "", "", None, None))
                seen.add(row.id)
        conds = []
        if r.supplier_key and r.invoice_key:
            conds.append(and_(Extraction.supplier_key == r.supplier_key, Extraction.invoice_key == r.invoice_key))
        if r.supplier_key and r.total is not None and r.invoice_date:
            conds.append(and_(Extraction.supplier_key == r.supplier_key, Extraction.total == r.total,
                              Extraction.invoice_date == r.invoice_date))
        if conds:
            rows = self.db.execute(
                select(Extraction, Document.file_hash).join(Document, Document.id == Extraction.document_id)
                .where(Extraction.document_id != r.doc_id, or_(*conds)))
            for e, fh in rows:
                if e.document_id in seen:
                    continue
                out.append(DuplicateRecord(e.document_id, fh, e.supplier_key or "", e.invoice_key or "",
                                           e.total, e.invoice_date))
        return out
