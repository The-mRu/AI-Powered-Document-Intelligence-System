"""Fixtures SLICED / AKASH are the real extraction results from the owner's live runs."""
import copy
import json
from datetime import date

from app.validation.duplicates import InMemoryDuplicateIndex, record_from_extraction
from app.validation.validator import validate_invoice

TODAY = date(2026, 10, 28)


def f(value, status="ok", flags=None, conf=0.9):
    return {"value": value, "confidence": conf, "evidence": "x", "status": status, "flags": flags or []}


def item(desc, qty, price, total, flags=None):
    return {"description": desc, "quantity": qty, "unit_price": price, "line_total": total, "unit": None,
            "confidence": 0.9, "evidence": "x", "flags": flags or []}


SLICED = {
    "invoice_number": f("INV-3337"), "invoice_date": f("2016-01-25"),
    "supplier_name": f("DEMO - Sliced Invoices"), "customer_name": f("Test Business"),
    "subtotal": f("85.00"), "tax": f("8.50"), "discount": f(None, "missing", conf=0.0), "total": f("93.50"),
    "currency": f(None, "missing", conf=0.0),
    "line_items": [item("Web Design", "1.00", "85.00", "85.00")],
    "needs_review_fields": [],
}

AKASH = {
    "invoice_number": f("S01"), "invoice_date": f("2023-08-11"), "supplier_name": f("Akash Enterprises"),
    "customer_name": f("Sampath singh", "uncertain", ["evidence_not_verbatim"], 0.6),
    "subtotal": f("1155.00"), "tax": f("55.00", "uncertain", ["evidence_not_verbatim", "value_not_in_evidence"], 0.4),
    "discount": f("100.0"), "total": f("1055.00"), "currency": f("INR"),
    "line_items": [item("Apple normal", "5", "100.00", "525.00"), item("Orange", "10", "40.00", "420.00"),
                   item("Banana", "5", "40", "210.00")],
    "needs_review_fields": ["customer_name", "tax"],
}


def run(x, **kw):
    kw.setdefault("today", TODAY)
    return validate_invoice(x, **kw)


def rules(report, severity=None):
    return {i.rule for i in report.issues if severity is None or i.severity == severity}


def mod(base, **changes):
    x = copy.deepcopy(base)
    for k, v in changes.items():
        x[k] = v
    return x


# ---------- the two real invoices ----------
def test_sliced_only_problem_is_the_missing_currency():
    r = run(SLICED)
    assert rules(r, "error") == set()
    assert rules(r, "warning") == {"missing_recommended_field"}
    assert "totals_consistent" in rules(r, "info") and r.needs_manual_review


def test_akash_tax_inclusive_invoice_has_no_errors():
    """1155 + 55 - 100 != 1055, but 1155 - 100 == 1055. A naive validator rejects this correct invoice."""
    r = run(AKASH)
    assert rules(r, "error") == set()
    assert {"subtotal_includes_tax", "line_totals_include_tax", "line_sum_consistent"} <= rules(r, "info")
    assert rules(r, "warning") == {"uncertain_extraction"}  # customer_name + tax flagged by the extractor


# ---------- missing / wrong values ----------
def test_missing_required_fields_are_errors():
    r = run(mod(SLICED, invoice_number=f(None, "missing", ["no_evidence"], 0.0), total=f(None, "missing", conf=0.0)))
    errs = [i for i in r.issues if i.rule == "missing_required_field"]
    assert {e.field for e in errs} == {"invoice_number", "total"}
    assert errs[0].details["extraction_flags"] == ["no_evidence"]


def test_total_mismatch_is_an_error_with_numbers():
    r = run(mod(SLICED, total=f("100.00")))
    e = next(i for i in r.issues if i.rule == "total_mismatch")
    assert e.severity == "error" and e.details["expected_tax_exclusive"] == "93.50"


def test_rounding_difference_within_tolerance_passes():
    x = mod(SLICED, subtotal=f("33.33"), tax=f("3.33"), total=f("36.67"),
            line_items=[item("a", "1", "33.33", "33.33")])
    assert "total_mismatch" not in rules(run(x))


def test_negative_and_zero_amounts():
    r = run(mod(SLICED, tax=f("-8.50")))
    assert "negative_amount" in rules(r, "error")
    r2 = run(mod(SLICED, subtotal=f("0"), tax=f("0"), total=f("0"), line_items=[]))
    assert "zero_total" in rules(r2, "warning")


def test_tax_larger_than_subtotal_and_huge_amount_warn():
    assert "tax_exceeds_subtotal" in rules(run(mod(SLICED, tax=f("500.00"))), "warning")
    assert "implausibly_large_amount" in rules(run(mod(SLICED, total=f("5000000000"))), "warning")


def test_dates():
    assert "future_date" in rules(run(mod(SLICED, invoice_date=f("2027-05-01"))), "warning")
    assert "very_old_date" in rules(run(mod(SLICED, invoice_date=f("1985-05-01"))), "warning")
    assert "invalid_date" in rules(run(mod(SLICED, invoice_date=f("2024-02-31"))), "error")


def test_cannot_verify_when_subtotal_missing():
    r = run(mod(SLICED, subtotal=f(None, "missing", conf=0.0)))
    assert "cannot_verify_totals" in rules(r, "warning")


def test_discount_sign_does_not_matter():
    x = mod(AKASH, discount=f("-100.0"))
    assert "total_mismatch" not in rules(run(x))


# ---------- line items ----------
def test_line_total_mismatch_with_no_tax_explanation_is_an_error():
    x = mod(SLICED, line_items=[item("Web Design", "2", "85.00", "85.00")])
    e = next(i for i in run(x).issues if i.rule == "line_total_mismatch")
    assert e.details == {"expected": "170.00", "actual": "85.00"}


def test_single_wrong_line_is_not_excused_as_tax():
    """25% 'implied tax' on one line, and the header tax disagrees -> still an error."""
    x = mod(SLICED, subtotal=f("125.00"), tax=f("8.50"), total=f("133.50"),
            line_items=[item("a", "2", "50.00", "125.00")])
    assert "line_total_mismatch" in rules(run(x), "error")


def test_line_sum_mismatch():
    x = mod(SLICED, line_items=[item("Web Design", "1", "85.00", "85.00"), item("Extra", "1", "40.00", "40.00")])
    assert "line_sum_mismatch" in rules(run(x), "error")


def test_missing_line_total_and_flagged_item():
    x = mod(SLICED, line_items=[item("Web Design", "1", "85.00", None, flags=["line_total_not_in_source"])])
    r = run(x)
    assert {"line_total_missing", "line_item_uncertain"} <= rules(r, "warning")


def test_no_line_items_warns():
    assert "no_line_items" in rules(run(mod(SLICED, line_items=[])), "warning")


# ---------- tax id OCR check ----------
def test_ocr_zero_vs_letter_o_in_gstin_is_caught():
    text = "GSTIN: O8AALCR2857A1ZD  PAN Number: AVHPC9999A"
    w = next(i for i in run(SLICED, source_text=text).issues if i.rule == "suspected_ocr_error_in_tax_id")
    assert w.details == {"found": "O8AALCR2857A1ZD", "suggested": "08AALCR2857A1ZD"}


def test_correct_gstin_is_not_flagged():
    assert "suspected_ocr_error_in_tax_id" not in rules(run(SLICED, source_text="GSTIN: 08AALCR2857A1ZD"))


# ---------- duplicates ----------
def _index_with(x, doc_id="doc-1", file_hash="h1"):
    idx = InMemoryDuplicateIndex()
    idx.add(record_from_extraction(x, doc_id, file_hash))
    return idx


def test_same_file_uploaded_twice():
    r = run(SLICED, doc_id="doc-2", file_hash="h1", dup_index=_index_with(SLICED))
    assert "duplicate_file" in rules(r, "error")


def test_same_invoice_in_a_different_file_is_a_duplicate():
    r = run(SLICED, doc_id="doc-2", file_hash="h2", dup_index=_index_with(SLICED))
    assert "duplicate_invoice" in rules(r, "error") and "duplicate_file" not in rules(r)


def test_invoice_number_reused_with_different_total_is_a_warning():
    other = mod(SLICED, total=f("500.00"))
    r = run(SLICED, doc_id="doc-2", file_hash="h2", dup_index=_index_with(other))
    assert "invoice_number_reused" in rules(r, "warning") and "duplicate_invoice" not in rules(r)


def test_same_supplier_amount_date_different_number():
    other = mod(SLICED, invoice_number=f("INV-9999"))
    r = run(SLICED, doc_id="doc-2", file_hash="h2", dup_index=_index_with(other))
    assert "possible_duplicate" in rules(r, "warning")


def test_invoice_number_formatting_does_not_hide_a_duplicate():
    other = mod(SLICED, invoice_number=f("inv 3337"))
    assert "duplicate_invoice" in rules(run(SLICED, doc_id="d2", file_hash="h2", dup_index=_index_with(other)), "error")


def test_document_is_not_a_duplicate_of_itself():
    r = run(SLICED, doc_id="doc-1", file_hash="h1", dup_index=_index_with(SLICED, "doc-1", "h1"))
    assert not {"duplicate_file", "duplicate_invoice", "possible_duplicate"} & rules(r)


def test_different_suppliers_are_not_duplicates():
    other = mod(SLICED, supplier_name=f("Globex"))
    r = run(SLICED, doc_id="doc-2", file_hash="h2", dup_index=_index_with(other))
    assert not {"duplicate_invoice", "possible_duplicate", "invoice_number_reused"} & rules(r)


# ---------- report shape ----------
def test_report_is_json_serializable_with_counts():
    d = run(AKASH, source_text="O8AALCR2857A1ZD").to_dict()
    json.dumps(d)
    assert d["status"] == "needs_review" and d["counts"]["error"] == 0 and d["counts"]["warning"] >= 2
    assert all(isinstance(r, str) for r in d["reasons"])


def test_clean_invoice_passes():
    x = mod(SLICED, currency=f("USD"))
    r = run(x)
    assert r.status == "passed" and not r.needs_manual_review and r.reasons == []
