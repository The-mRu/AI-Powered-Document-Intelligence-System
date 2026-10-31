"""API + worker + database tests. They run against a REAL PostgreSQL (with pgvector) in a separate
`<db>_test` database, so they never touch real data. Skipped automatically when DATABASE_URL is unset
or unreachable (e.g. plain `docker run ... pytest`); run them with `docker compose run --rm api pytest`."""
import os
from pathlib import Path

import pytest

_BASE = os.environ.get("DATABASE_URL")
if not _BASE:
    pytest.skip("DATABASE_URL not set: API tests need PostgreSQL (use docker compose)", allow_module_level=True)

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

_url = make_url(_BASE)
_test_url = _url.set(database="docintel_test")
try:
    _admin = create_engine(_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with _admin.connect() as c:
        if not c.execute(text("SELECT 1 FROM pg_database WHERE datname=:n"), {"n": _test_url.database}).scalar():
            c.execute(text(f'CREATE DATABASE "{_test_url.database}"'))
except Exception as e:  # noqa: BLE001
    pytest.skip(f"PostgreSQL not reachable: {type(e).__name__}", allow_module_level=True)
_test_engine = create_engine(_test_url, pool_pre_ping=True)
_test_sessionmaker = sessionmaker(_test_engine, expire_on_commit=False)
from .db_isolation import assert_test_database, truncate_test_database  # noqa: E402

assert_test_database(_test_engine)

import io  # noqa: E402

import pymupdf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import services  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db.models import Correction, Document, Page, ValidationIssue  # noqa: E402
from app.db.session import get_db, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app import main as main_module  # noqa: E402
from app.workers import pipeline  # noqa: E402
from app.workers.celery_app import celery_app  # noqa: E402

from .fakes import FakeEmbedder, FakeLLM  # noqa: E402


def _test_db():
    db = _test_sessionmaker()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _test_db
main_module.get_engine = lambda: _test_engine
main_module.init_db = lambda: init_db(_test_engine)
pipeline.get_sessionmaker = lambda: _test_sessionmaker


def make_pdf(number="INV-1001", total="110.00", currency="USD", supplier="Acme Trading Ltd", extra="") -> bytes:
    lines = [f"Invoice Number: {number}", "Invoice Date: 2024-03-15", f"Supplier: {supplier}",
             "Customer: Globex Corporation", "Subtotal: 100.00", "Tax: 10.00", f"Total: {total}"]
    if currency:
        lines.append(f"Currency: {currency}")
    lines.append("Widget 2 50.00 100.00")
    if extra:
        lines.append(extra)
    doc = pymupdf.open()
    page = doc.new_page()
    for i, ln in enumerate(lines):
        page.insert_text((72, 72 + 18 * i), ln, fontsize=11)
    return doc.tobytes()


@pytest.fixture(scope="session", autouse=True)
def _schema():
    init_db(_test_engine)
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    truncate_test_database(_test_engine)
    llm = FakeLLM()
    monkeypatch.setattr(services, "get_llm", lambda: llm)
    monkeypatch.setattr(services, "get_embedder", lambda: FakeEmbedder())
    yield llm
    get_settings.cache_clear()


@pytest.fixture
def llm(env):
    return env


@pytest.fixture
def client():
    return TestClient(app)


def upload(client, files):
    payload = [("files", (n, io.BytesIO(b), "application/octet-stream")) for n, b in files]
    return client.post("/api/documents", files=payload)


def upload_one(client, name="invoice.pdf", data=None):
    r = upload(client, [(name, data if data is not None else make_pdf())])
    assert r.status_code == 202, r.text
    return r.json()["documents"][0]


def result(client, doc_id):
    return client.get(f"/api/documents/{doc_id}/result").json()


def rules(client, doc_id):
    return {i["rule"] for i in result(client, doc_id)["validation"]["issues"]}


# ------------------------------------------------------------------ basics
def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_original_file_returns_exact_bytes_and_mime_type(client):
    source = make_pdf()
    document = upload_one(client, "invoice.pdf", source)

    response = client.get(f"/api/documents/{document['id']}/original")

    assert response.status_code == 200
    assert response.content == source
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'inline; filename="invoice.pdf"'

    download = client.get(f"/api/documents/{document['id']}/original?download=true")
    assert download.status_code == 200
    assert download.headers["content-disposition"] == 'attachment; filename="invoice.pdf"'


def test_original_file_returns_not_found_when_storage_is_missing(client):
    document = upload_one(client, "invoice.pdf")
    stored = _test_sessionmaker()
    try:
        row = stored.get(Document, document["id"])
        Path(row.storage_path).unlink()
    finally:
        stored.close()

    response = client.get(f"/api/documents/{document['id']}/original")

    assert response.status_code == 404
    assert response.json()["detail"] == "Original file is unavailable"


def test_test_database_configuration_is_explicit():
    with _test_engine.connect() as connection:
        assert connection.execute(text("SELECT current_database()")).scalar() == "docintel_test"
    assert str(_test_engine.url).split("@")[-1].endswith("/docintel_test")


def test_production_database_is_rejected_by_cleanup_guard():
    production_engine = create_engine(_url)
    with pytest.raises(RuntimeError, match="docintel_test"):
        truncate_test_database(production_engine)
    production_engine.dispose()


def test_api_requests_use_test_database(client):
    d = upload_one(client)
    with _test_sessionmaker() as db:
        assert db.query(Page).filter(Page.document_id == d["id"]).count() == 1


def test_upload_processes_end_to_end(client):
    d = upload_one(client)
    detail = client.get(f"/api/documents/{d['id']}").json()
    assert detail["status"] == "completed" and detail["progress"]["percent"] == 100
    assert detail["kind"] == "pdf" and detail["supplier_name"] == "Acme Trading Ltd"
    assert [h["stage"] for h in detail["history"]] == ["processing", "extraction", "validation", "embedding"]
    res = result(client, d["id"])
    assert res["effective"]["invoice_number"]["value"] == "INV-1001"
    assert res["effective"]["total"]["value"] == "110.00"
    assert client.get(f"/api/documents/{d['id']}/pages").json()["items"][0]["method"] == "text_layer"
    with _test_sessionmaker() as db:
        assert db.query(Page).filter(Page.embedding.is_not(None)).count() == 1


def test_upload_many_with_mixed_outcomes(client, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    r = upload(client, [("a.pdf", make_pdf("INV-1")), ("b.exe", b"MZ"), ("big.pdf", b"%PDF" + b"0" * 1_100_000),
                        ("empty.pdf", b""), ("c.pdf", make_pdf("INV-3", supplier="Initech"))])
    out = {x["filename"]: x for x in r.json()["documents"]}
    assert out["b.exe"]["error"] == "unsupported_extension"
    assert out["big.pdf"]["error"] == "file_too_large" and out["empty.pdf"]["error"] == "empty_file"
    assert out["a.pdf"]["status"] == "completed" and out["c.pdf"]["status"] == "completed"
    assert client.get("/api/documents").json()["total"] == 2


def test_too_many_files_rejected(client, monkeypatch):
    monkeypatch.setenv("MAX_FILES_PER_REQUEST", "2")
    get_settings.cache_clear()
    assert upload(client, [(f"{i}.pdf", make_pdf(f"INV-{i}")) for i in range(3)]).status_code == 413


def test_path_traversal_filename_is_neutralised(client, tmp_path):
    d = upload_one(client, name="../../evil.pdf")
    assert d["filename"] == "evil.pdf"
    stored = list((tmp_path / "storage").iterdir())
    assert len(stored) == 1 and stored[0].name.endswith(".pdf") and stored[0].parent == tmp_path / "storage"
    assert not (tmp_path.parent / "evil.pdf").exists()


def test_spreadsheet_is_processed(client):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Invoice No", "Total"])
    ws.append(["00123", 99.5])
    buf = io.BytesIO()
    wb.save(buf)
    d = upload_one(client, "book.xlsx", buf.getvalue())
    detail = client.get(f"/api/documents/{d['id']}").json()
    assert detail["kind"] == "xlsx" and detail["status"] == "needs_review"  # fake LLM finds no invoice fields
    assert client.get(f"/api/documents/{d['id']}/pages").json()["items"][0]["method"] == "spreadsheet"


# ------------------------------------------------------------------ failures and reprocessing
def test_corrupted_file_fails_with_reason_and_can_be_reprocessed(client):
    d = upload_one(client, "bad.pdf", b"%PDF-1.7 this is not really a pdf")
    detail = client.get(f"/api/documents/{d['id']}").json()
    assert detail["status"] == "failed" and detail["error_code"] == "corrupted_file"
    r = client.post(f"/api/documents/{d['id']}/reprocess")
    assert r.status_code == 202
    assert client.get(f"/api/documents/{d['id']}").json()["attempts"] == 2


def test_result_of_failed_document_explains_why(client):
    d = upload_one(client, "bad.pdf", b"%PDF-1.7 broken")
    res = result(client, d["id"])
    assert res["status"] == "failed" and res["error_code"] == "corrupted_file" and res["effective"] is None


def test_llm_outage_then_recovery_via_reprocess_failed(client, llm):
    llm.fail = True
    d = upload_one(client)
    detail = client.get(f"/api/documents/{d['id']}").json()
    assert detail["status"] == "failed" and detail["error_code"] == "extraction_failed"
    assert client.get(f"/api/documents/{d['id']}/pages").json()["items"], "OCR/text work is kept"
    llm.fail = False
    r = client.post("/api/documents/reprocess-failed").json()
    assert r["requeued"] == 1
    assert client.get(f"/api/documents/{d['id']}").json()["status"] == "completed"


def test_reprocess_refuses_finished_documents_without_force(client):
    d = upload_one(client)
    assert client.post(f"/api/documents/{d['id']}/reprocess").status_code == 409
    assert client.post(f"/api/documents/{d['id']}/reprocess?force=true").status_code == 202


def test_queue_outage_does_not_lose_the_document(client, monkeypatch):
    import app.api.documents as docs

    def boom(_):
        raise ConnectionError("redis down")
    monkeypatch.setattr(docs.process_document, "delay", boom)
    d = upload_one(client)
    assert d["status"] == "failed" and d["error"] == "queue_unavailable"
    monkeypatch.undo()


def test_unknown_document_is_404(client):
    assert client.get("/api/documents/nope").status_code == 404


def test_delete_document_removes_record_and_file(client, tmp_path):
    d = upload_one(client)
    stored = list((tmp_path / "storage").iterdir())
    assert len(stored) == 1 and stored[0].exists()

    response = client.delete(f"/api/documents/{d['id']}")

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "document_id": d["id"]}
    assert not stored[0].exists()
    assert client.get(f"/api/documents/{d['id']}").status_code == 404


def test_delete_processing_document_is_rejected(client):
    d = upload_one(client)
    with _test_sessionmaker() as db:
        db.get(Document, d["id"]).status = "processing"
        db.commit()
    assert client.delete(f"/api/documents/{d['id']}").status_code == 409


# ------------------------------------------------------------------ duplicates via the database
def test_same_file_twice_is_flagged_as_duplicate_file(client):
    same = make_pdf()  # byte-identical content, uploaded twice
    a = upload_one(client, data=same)
    b = upload_one(client, data=same)
    assert "duplicate_file" in rules(client, b["id"])
    assert client.get(f"/api/documents/{b['id']}").json()["status"] == "needs_review"
    assert "duplicate_file" not in rules(client, a["id"])  # first upload was clean


def test_same_invoice_in_a_different_file_is_flagged_as_duplicate_invoice(client):
    upload_one(client)
    b = upload_one(client, data=make_pdf(extra="Notes: re-sent copy"))
    assert "duplicate_invoice" in rules(client, b["id"]) and "duplicate_file" not in rules(client, b["id"])


def test_other_suppliers_are_not_duplicates(client):
    upload_one(client)
    b = upload_one(client, data=make_pdf(supplier="Initech Holdings"))
    assert not {"duplicate_invoice", "duplicate_file", "possible_duplicate"} & rules(client, b["id"])


# ------------------------------------------------------------------ manual corrections
def test_correction_fixes_missing_currency_and_is_audited(client):
    d = upload_one(client, data=make_pdf(currency=None))
    assert client.get(f"/api/documents/{d['id']}").json()["status"] == "needs_review"
    r = client.patch(f"/api/documents/{d['id']}/corrections", json={"fields": {"currency": "usd"}, "note": "from PO"})
    assert r.status_code == 200
    body = r.json()
    assert body["effective"]["currency"]["value"] == "USD" and body["extraction_ai"]["currency"]["value"] is None
    assert body["status"] == "completed"
    with _test_sessionmaker() as db:
        c = db.query(Correction).one()
        assert (c.field, c.old_value, c.new_value, c.note) == ("currency", None, "USD", "from PO")


def test_wrong_correction_is_revalidated_and_flagged(client):
    d = upload_one(client)
    r = client.patch(f"/api/documents/{d['id']}/corrections", json={"fields": {"total": "999.00"}}).json()
    assert r["status"] == "needs_review" and "total_mismatch" in {i["rule"] for i in r["validation"]["issues"]}


def test_correction_input_is_validated(client):
    d = upload_one(client)
    url = f"/api/documents/{d['id']}/corrections"
    assert client.patch(url, json={"fields": {"total": "abc"}}).status_code == 422
    assert client.patch(url, json={"fields": {"invoice_date": "15/03/2024"}}).status_code == 422
    assert client.patch(url, json={"fields": {"currency": "DOLLARS"}}).status_code == 422
    assert client.patch(url, json={"fields": {"password": "x"}}).status_code == 422


def test_cannot_correct_a_failed_document(client):
    d = upload_one(client, "bad.pdf", b"%PDF-1.7 broken")
    assert client.patch(f"/api/documents/{d['id']}/corrections", json={"fields": {"total": "1"}}).status_code == 409


def test_line_item_correction(client):
    d = upload_one(client)
    r = client.patch(f"/api/documents/{d['id']}/corrections", json={"line_items": [
        {"description": "Widget", "quantity": "2", "unit_price": "60.00", "line_total": "120.00"}]}).json()
    assert {"line_sum_mismatch"} & {i["rule"] for i in r["validation"]["issues"]}


def test_approve_flagged_document(client):
    d = upload_one(client, data=make_pdf(currency=None))
    assert client.post(f"/api/documents/{d['id']}/approve").json()["status"] == "completed"
    assert client.post(f"/api/documents/{d['id']}/approve").status_code == 409


def test_truncated_document_is_flagged_not_silent(client, monkeypatch):
    import app.extraction.extractor as ex
    monkeypatch.setattr(ex, "MAX_CHARS", 60)
    d = upload_one(client)
    assert "document_truncated" in rules(client, d["id"])


# ------------------------------------------------------------------ search
def test_keyword_search_filters_and_snippet(client):
    a = upload_one(client)
    upload_one(client, data=make_pdf("INV-2002", supplier="Initech Holdings", currency="EUR"))
    hits = client.get("/api/search", params={"q": "Globex"}).json()["results"]
    assert len(hits) == 2 and "<mark>" in hits[0]["snippet"]
    only = client.get("/api/search", params={"q": "Globex", "supplier": "initech"}).json()["results"]
    assert [h["invoice_number"] for h in only] == ["INV-2002"]
    by_number = client.get("/api/search", params={"q": "INV-1001"}).json()["results"]
    assert by_number[0]["document_id"] == a["id"]
    assert client.get("/api/search", params={"q": "zzzzqqqq"}).json()["results"] == []


def test_search_filters_by_date_and_status(client):
    upload_one(client)
    base = {"q": "Globex"}
    assert client.get("/api/search", params={**base, "date_from": "2024-03-01", "date_to": "2024-03-31"}).json()["results"]
    assert not client.get("/api/search", params={**base, "date_from": "2025-01-01"}).json()["results"]
    assert not client.get("/api/search", params={**base, "status": "failed"}).json()["results"]


def test_semantic_search_ranks_related_document_first(client):
    upload_one(client)
    b = upload_one(client, data=make_pdf("INV-2002", supplier="Initech Holdings", currency="EUR"))
    hits = client.get("/api/search", params={"q": "Initech Holdings invoice", "mode": "semantic"}).json()["results"]
    assert hits[0]["document_id"] == b["id"] and hits[0]["score"] > hits[1]["score"]


def test_search_validates_input(client):
    assert client.get("/api/search", params={"q": "x"}).status_code == 422
    assert client.get("/api/search", params={"q": "abc", "mode": "magic"}).status_code == 422
    assert client.get("/api/search", params={"q": "abc", "date_from": "yesterday"}).status_code == 422


# ------------------------------------------------------------------ listing, stats, security
def test_list_filters_and_pagination(client):
    for i in range(3):
        upload_one(client, data=make_pdf(f"INV-{i}", supplier=f"Supplier {i} Ltd"))
    upload_one(client, "bad.pdf", b"%PDF-1.7 broken")
    assert client.get("/api/documents", params={"status": "failed"}).json()["total"] == 1
    page = client.get("/api/documents", params={"limit": 2, "offset": 0}).json()
    assert page["total"] == 4 and len(page["items"]) == 2
    assert client.get("/api/documents", params={"q": "Supplier 1"}).json()["total"] == 1


def test_stats_report_success_and_failure_rates(client):
    upload_one(client)
    upload_one(client, "bad.pdf", b"%PDF-1.7 broken")
    s = client.get("/api/stats").json()
    assert s["total"] == 2 and s["success_rate"] == 0.5 and s["failure_rate"] == 0.5
    assert s["processing_seconds"]["p50"] is not None


def test_all_document_operations_are_public(client):
    assert client.get("/api/documents").status_code == 200
    assert client.get("/api/stats").status_code == 200
    assert client.post("/api/documents", files=[("files", ("invoice.pdf", io.BytesIO(make_pdf()), "application/pdf"))]).status_code == 202
    assert client.get("/health").status_code == 200  # health stays open for load balancers
