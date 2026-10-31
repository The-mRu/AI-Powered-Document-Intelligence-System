"""Run the real worker pipeline against an isolated benchmark database.

The Celery broker is intentionally not used: run_pipeline is the production
worker body, and direct invocation avoids queue loss/retry behavior changing
the measurement. Embeddings are replaced only by a local no-op because they
are unrelated to extraction accuracy and the benchmark requirement excludes
embedding calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def benchmark_database_url(value: str) -> str:
    from sqlalchemy.engine import make_url

    database = make_url(value).database
    if not database or not database.startswith("docintel_benchmark"):
        raise ValueError("BENCHMARK_DATABASE_URL must name a dedicated docintel_benchmark* database")
    return value


def benchmark_storage_dir(value: str) -> Path:
    path = Path(value).resolve()
    if "benchmark" not in path.name.casefold():
        raise ValueError("BENCHMARK_STORAGE_DIR must name a dedicated benchmark directory")
    return path


class NoOpEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return []


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def setup_isolation(database_url: str, storage_dir: Path):
    from app.db.session import create_database_engine, create_sessionmaker, init_db
    from app.workers import pipeline
    from app import services

    engine = create_database_engine(database_url)
    init_db(engine)
    sessionmaker = create_sessionmaker(engine)
    pipeline.get_sessionmaker = lambda: sessionmaker
    services.get_embedder = lambda: NoOpEmbedder()
    storage_dir.mkdir(parents=True, exist_ok=True)
    return engine, sessionmaker


def create_document(sessionmaker, source: Path, storage_dir: Path, relative_name: str):
    from app.db.models import Document

    stored = storage_dir / f"{source.stem}.benchmark{source.suffix}"
    stored.write_bytes(source.read_bytes())
    with sessionmaker() as db:
        doc = Document(filename=relative_name, file_hash=sha256(stored), size_bytes=stored.stat().st_size,
                       storage_path=str(stored), status="queued")
        db.add(doc)
        db.commit()
        return doc.id


def read_run(sessionmaker, doc_id: str, before_event_id: int, wall_ms: float, run_number: int,
             filename: str, document_type: str) -> dict:
    from sqlalchemy import select
    from app.db.models import Document, Extraction, ProcessingEvent

    with sessionmaker() as db:
        doc = db.get(Document, doc_id)
        ext = db.execute(select(Extraction).where(Extraction.document_id == doc_id)).scalar_one_or_none()
        events = db.execute(select(ProcessingEvent).where(
            ProcessingEvent.document_id == doc_id, ProcessingEvent.id > before_event_id
        ).order_by(ProcessingEvent.id)).scalars().all()
        by_stage = {event.stage: event for event in events}
        usage = (ext.data or {}).get("usage") if ext else None
        return {
            "filename": filename,
            "document_type": document_type,
            "run_number": run_number,
            "processing_status": by_stage.get("processing").status if by_stage.get("processing") else "not_run",
            "extraction_status": by_stage.get("extraction").status if by_stage.get("extraction") else "not_run",
            "validation_status": by_stage.get("validation").status if by_stage.get("validation") else "not_run",
            "document_status": doc.status if doc else "missing",
            "processing_time_ms": round(wall_ms, 2),
            "processing_stage_ms": by_stage.get("processing").duration_ms if by_stage.get("processing") else None,
            "extraction_time_ms": by_stage.get("extraction").duration_ms if by_stage.get("extraction") else None,
            "validation_time_ms": by_stage.get("validation").duration_ms if by_stage.get("validation") else None,
            "needs_review": bool(ext.needs_review) if ext else None,
            "model": (ext.data or {}).get("model") if ext else None,
            "input_tokens": usage.get("prompt_tokens") if isinstance(usage, dict) else None,
            "output_tokens": usage.get("completion_tokens") if isinstance(usage, dict) else None,
            "raw_extracted": ext.data if ext else None,
            "error": {"code": doc.error_code, "message": doc.error_message} if doc and doc.error_code else None,
            "events": [{"stage": e.stage, "status": e.status, "duration_ms": e.duration_ms} for e in events],
        }


def run_one(sessionmaker, record: dict, storage_dir: Path, runs: int) -> list[dict]:
    from sqlalchemy import func, select
    from app.db.models import ProcessingEvent
    from app.workers.pipeline import run_pipeline

    source = ROOT / Path(record["path"].replace("\\", "/"))
    doc_id = create_document(sessionmaker, source, storage_dir, record["filename"])
    results = []
    for run_number in range(1, runs + 1):
        with sessionmaker() as db:
            before_event_id = db.execute(select(func.coalesce(func.max(ProcessingEvent.id), 0))).scalar_one()
        started = time.perf_counter()
        try:
            run_pipeline(doc_id)
            error = None
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
        wall_ms = (time.perf_counter() - started) * 1000
        result = read_run(sessionmaker, doc_id, before_event_id, wall_ms, run_number,
                          record["filename"], record["document_type"])
        if error:
            result["runner_error"] = error
        results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default="evaluation/extraction_dataset/labels.json")
    parser.add_argument("--output")
    parser.add_argument("--database-url", default=os.environ.get("BENCHMARK_DATABASE_URL"))
    parser.add_argument("--storage-dir", default=os.environ.get("BENCHMARK_STORAGE_DIR"))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--expected-failures", action="store_true")
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("Set BENCHMARK_DATABASE_URL to a dedicated PostgreSQL database URL")
    if not args.storage_dir:
        raise SystemExit("Set BENCHMARK_STORAGE_DIR to an isolated directory")
    database_url = benchmark_database_url(args.database_url)
    labels = json.loads((ROOT / args.labels).read_text(encoding="utf-8"))
    storage_dir = benchmark_storage_dir(args.storage_dir)
    os.environ["STORAGE_DIR"] = str(storage_dir)
    _, sessionmaker = setup_isolation(database_url, storage_dir)
    records = labels["expected_failures"] if args.expected_failures else labels["documents"]
    all_results = []
    for record in records:
        all_results.extend(run_one(sessionmaker, record, storage_dir, 1 if args.expected_failures else args.runs))
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "configuration": {
            "runs_per_valid_document": args.runs,
            "embeddings": "bypassed_with_benchmark_noop",
            "celery": "not_used_direct_run_pipeline",
            "database": "dedicated_database_required",
            "storage": str(storage_dir),
        },
        "valid_document_count": len(labels["documents"]),
        "expected_failure_count": len(labels["expected_failures"]),
        "scope": "expected_failures" if args.expected_failures else "valid_documents",
        "results": all_results,
    }
    output_name = args.output or (
        "evaluation/extraction_expected_results.json" if args.expected_failures
        else "evaluation/extraction_results.json"
    )
    output = ROOT / output_name
    output.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"scope": payload["scope"], "runs": len(all_results), "output": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
