"""Database schema (Task 5).

documents        one row per uploaded file: metadata, status, progress, error
pages            extracted text per page/sheet + full-text index + embedding (pgvector)
extractions      structured AI result (JSONB), human corrections, validation report,
                 plus denormalised columns used for filtering and duplicate detection
validation_issues one row per validation finding (queryable)
processing_events audit trail of every stage with duration (also feeds the evaluation)
corrections      who/what changed which field (original AI value is never overwritten)
"""
from datetime import datetime, timezone
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, Numeric,
                        String, Text, func, literal_column)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBED_DIM = 1536  # text-embedding-3-small


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(255))  # display only; never used as a path
    file_hash: Mapped[str] = mapped_column(String(64), index=True)  # sha256
    kind: Mapped[str | None] = mapped_column(String(16))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    storage_path: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    pages_done: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    pages = relationship("Page", cascade="all, delete-orphan", passive_deletes=True, order_by="Page.page_no")
    extraction = relationship("Extraction", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    issues = relationship("ValidationIssue", cascade="all, delete-orphan", passive_deletes=True)
    events = relationship("ProcessingEvent", cascade="all, delete-orphan", passive_deletes=True,
                          order_by="ProcessingEvent.id")


class Page(Base):
    __tablename__ = "pages"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_no: Mapped[int] = mapped_column(Integer)
    label: Mapped[str | None] = mapped_column(String(255))  # sheet name
    method: Mapped[str] = mapped_column(String(16))  # text_layer | ocr | spreadsheet | failed
    confidence: Mapped[float | None] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    embedding = mapped_column(Vector(EMBED_DIM), nullable=True)


Index("ix_pages_fts", func.to_tsvector(literal_column("'english'"), Page.text), postgresql_using="gin")
Index("ix_pages_embedding", Page.embedding, postgresql_using="hnsw",
      postgresql_with={"m": 16, "ef_construction": 64}, postgresql_ops={"embedding": "vector_cosine_ops"})


class Extraction(Base):
    __tablename__ = "extractions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), unique=True)
    data: Mapped[dict] = mapped_column(JSONB)  # raw verified AI output, never modified
    corrected: Mapped[dict | None] = mapped_column(JSONB)  # {"fields": {...}, "line_items": [...]}
    validation: Mapped[dict | None] = mapped_column(JSONB)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    # denormalised from the EFFECTIVE data (AI + corrections) for filtering/duplicates
    supplier_name: Mapped[str | None] = mapped_column(String(255))
    supplier_key: Mapped[str | None] = mapped_column(String(255), index=True)
    invoice_number: Mapped[str | None] = mapped_column(String(128))
    invoice_key: Mapped[str | None] = mapped_column(String(128), index=True)
    invoice_date: Mapped[str | None] = mapped_column(String(10), index=True)
    total: Mapped[float | None] = mapped_column(Numeric(18, 4))
    currency: Mapped[str | None] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ValidationIssue(Base):
    __tablename__ = "validation_issues"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    rule: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(8))
    field: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)


class ProcessingEvent(Base):
    __tablename__ = "processing_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    detail: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Correction(Base):
    __tablename__ = "corrections"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    field: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
