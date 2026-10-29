"""Duplicate detection behind a tiny interface.

Task 3 ships an in-memory index so the rules are testable now; Task 5 will add a
PostgreSQL-backed class with the same `candidates()` method. The validator never
knows which one it is talking to.
"""
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.extraction.verify import to_decimal


def key(s: str | None) -> str:
    """'INV-0042 ' and 'inv0042' are the same invoice number."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


@dataclass
class DuplicateRecord:
    doc_id: str
    file_hash: str | None
    supplier_key: str
    invoice_key: str
    total: Decimal | None
    invoice_date: str | None


class DuplicateIndex(Protocol):
    def candidates(self, record: DuplicateRecord) -> list[DuplicateRecord]: ...


def record_from_extraction(extraction: dict, doc_id: str, file_hash: str | None) -> DuplicateRecord:
    val = lambda n: (extraction.get(n) or {}).get("value")  # noqa: E731
    return DuplicateRecord(doc_id, file_hash, key(val("supplier_name")), key(val("invoice_number")),
                           to_decimal(val("total")), val("invoice_date"))


class InMemoryDuplicateIndex:
    def __init__(self):
        self._records: list[DuplicateRecord] = []

    def add(self, record: DuplicateRecord) -> None:
        self._records.append(record)

    def candidates(self, r: DuplicateRecord) -> list[DuplicateRecord]:
        out = []
        for o in self._records:
            if o.doc_id == r.doc_id:
                continue
            same_supplier = bool(r.supplier_key) and o.supplier_key == r.supplier_key
            if ((r.file_hash and o.file_hash == r.file_hash)
                    or (same_supplier and r.invoice_key and o.invoice_key == r.invoice_key)
                    or (same_supplier and r.total is not None and o.total == r.total
                        and r.invoice_date and o.invoice_date == r.invoice_date)):
                out.append(o)
        return out
