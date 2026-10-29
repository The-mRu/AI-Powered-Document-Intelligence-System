"""Task 3: deterministic validation of an extraction result. No LLM involved.

Why plain code: the extractor can be fooled; arithmetic cannot. Every rule has a
stable `rule` id so the UI can group them and the evaluation can count them.

Real-world formats this must tolerate (both found on the sample invoices):
  * "Sub Total" that already INCLUDES tax:  subtotal - discount = total
  * line totals that include per-line tax:  qty x price < line_total
So we test both identities and only fail when NEITHER holds.
"""
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.extraction.verify import to_decimal

from .duplicates import DuplicateIndex, key, record_from_extraction
from .models import Issue, ValidationReport

TOLERANCE = Decimal("0.02")  # rounding slack for header identities
REQUIRED = ["invoice_number", "invoice_date", "supplier_name", "total"]
RECOMMENDED = ["customer_name", "currency"]
HUGE = Decimal("1000000000")
MAX_TAX_RATE = Decimal("0.35")

_TAX_ID_LOOSE = re.compile(r"\b[0-9OIl]{2}[A-Z]{5}[0-9OIl]{4}[A-Z][0-9A-Z][A-Z][0-9A-Z]\b")
_DIGIT_SLOTS = (slice(0, 2), slice(7, 11))  # positions that must be digits in an Indian GSTIN


def _d(extraction: dict, name: str) -> Decimal | None:
    return to_decimal((extraction.get(name) or {}).get("value"))


def _v(extraction: dict, name: str):
    return (extraction.get(name) or {}).get("value")


def _s(x: Decimal) -> str:
    return format(x, "f")


def validate_invoice(extraction: dict, *, source_text: str | None = None, doc_id: str | None = None,
                     file_hash: str | None = None, dup_index: DuplicateIndex | None = None,
                     today: date | None = None, tolerance: Decimal = TOLERANCE) -> ValidationReport:
    issues: list[Issue] = []
    ctx = dict(x=extraction, issues=issues, tol=tolerance, today=today or date.today())
    _required(**{k: ctx[k] for k in ("x", "issues")})
    _uncertain(**{k: ctx[k] for k in ("x", "issues")})
    _numeric_sanity(**ctx)
    _header_arithmetic(**{k: ctx[k] for k in ("x", "issues", "tol")})
    _line_items(**{k: ctx[k] for k in ("x", "issues", "tol")})
    if source_text:
        _tax_ids(source_text, issues)
    if dup_index is not None and doc_id is not None:
        _duplicates(extraction, doc_id, file_hash, dup_index, issues, tolerance)
    return ValidationReport(issues)


# ---------------------------------------------------------------- rules
def _required(x, issues):
    for name in REQUIRED:
        if _v(x, name) is None:
            issues.append(Issue("missing_required_field", "error", f"Required field '{name}' is missing",
                                name, {"extraction_flags": (x.get(name) or {}).get("flags", [])}))
    for name in RECOMMENDED:
        if _v(x, name) is None:
            issues.append(Issue("missing_recommended_field", "warning", f"Field '{name}' is missing", name,
                                {"extraction_flags": (x.get(name) or {}).get("flags", [])}))
    if not x.get("line_items"):
        issues.append(Issue("no_line_items", "warning", "No line items were extracted", "line_items"))


def _uncertain(x, issues):
    for name in x.get("needs_review_fields", []):
        if name == "line_items":
            continue  # reported per item in _line_items
        f = x.get(name) or {}
        if f.get("value") is None and name in REQUIRED + RECOMMENDED:
            continue  # already reported as missing
        issues.append(Issue("uncertain_extraction", "warning",
                            f"'{name}' was extracted with low confidence or failed verification",
                            name, {"flags": f.get("flags", []), "confidence": f.get("confidence"),
                                   "evidence": f.get("evidence")}))


def _numeric_sanity(x, issues, tol, today):
    for name in ("subtotal", "tax", "total"):
        d = _d(x, name)
        if d is None:
            continue
        if d < 0:
            issues.append(Issue("negative_amount", "error", f"'{name}' is negative ({_s(d)})", name))
        if d > HUGE:
            issues.append(Issue("implausibly_large_amount", "warning", f"'{name}' is implausibly large ({_s(d)})", name))
    total, sub, tax = _d(x, "total"), _d(x, "subtotal"), _d(x, "tax")
    if total is not None and total == 0:
        issues.append(Issue("zero_total", "warning", "Total amount is zero", "total"))
    if tax is not None and sub is not None and sub > 0 and tax > sub:
        issues.append(Issue("tax_exceeds_subtotal", "warning", f"Tax ({_s(tax)}) is larger than subtotal ({_s(sub)})", "tax"))
    ds = _v(x, "invoice_date")
    if ds:
        try:
            dt = datetime.strptime(ds, "%Y-%m-%d").date()
        except ValueError:
            issues.append(Issue("invalid_date", "error", f"Invoice date '{ds}' is not a real date", "invoice_date"))
        else:
            if dt > today + timedelta(days=1):
                issues.append(Issue("future_date", "warning", f"Invoice date {ds} is in the future", "invoice_date"))
            elif dt.year < 2000:
                issues.append(Issue("very_old_date", "warning", f"Invoice date {ds} is before year 2000", "invoice_date"))


def _header_arithmetic(x, issues, tol):
    sub, tax, disc, total = _d(x, "subtotal"), _d(x, "tax"), _d(x, "discount"), _d(x, "total")
    if total is None or sub is None:
        if total is not None or sub is not None:
            issues.append(Issue("cannot_verify_totals", "warning",
                                "Subtotal or total is missing, so the amounts cannot be cross-checked", "total"))
        return
    disc = abs(disc) if disc is not None else Decimal(0)
    t = tax if tax is not None else Decimal(0)
    identities = {"tax_exclusive": sub + t - disc, "tax_inclusive": sub - disc}
    matched = [k for k, v in identities.items() if abs(v - total) <= tol]
    if matched:
        used = matched[0]
        issues.append(Issue("totals_consistent", "info", f"Totals reconcile ({used.replace('_', ' ')} subtotal)",
                            "total", {"identity": used}))
        if used == "tax_inclusive" and t > 0:
            issues.append(Issue("subtotal_includes_tax", "info",
                                "Subtotal appears to already include tax", "subtotal"))
        return
    issues.append(Issue("total_mismatch", "error",
                        f"Totals do not reconcile: subtotal {_s(sub)} + tax {_s(t)} - discount {_s(disc)} "
                        f"= {_s(identities['tax_exclusive'])}, but total is {_s(total)}",
                        "total", {"subtotal": _s(sub), "tax": _s(t), "discount": _s(disc), "total": _s(total),
                                  "expected_tax_exclusive": _s(identities["tax_exclusive"]),
                                  "expected_tax_inclusive": _s(identities["tax_inclusive"]),
                                  "tax_missing": tax is None}))


def _line_items(x, issues, tol):
    items = x.get("line_items") or []
    if not items:
        return
    line_tol = tol + Decimal("0.01") * len(items)  # per-line rounding accumulates
    sub, tax, disc, total = _d(x, "subtotal"), _d(x, "tax"), _d(x, "discount"), _d(x, "total")

    parsed, missing_total, mismatches = [], [], []
    for i, it in enumerate(items):
        qty, price, lt = to_decimal(it.get("quantity")), to_decimal(it.get("unit_price")), to_decimal(it.get("line_total"))
        parsed.append(lt)
        if it.get("flags"):
            issues.append(Issue("line_item_uncertain", "warning", f"Line item {i + 1} failed verification: "
                                f"{', '.join(it['flags'])}", f"line_items[{i}]", {"flags": it["flags"]}))
        if lt is None:
            missing_total.append(i + 1)
        if qty is not None and price is not None and lt is not None:
            exp = qty * price
            if abs(exp - lt) > tol + Decimal("0.01"):
                mismatches.append((i, exp, lt))
    if missing_total:
        issues.append(Issue("line_total_missing", "warning",
                            f"Line item(s) {missing_total} have no line total", "line_items"))

    if mismatches:
        rates = [(lt / exp - 1) for _, exp, lt in mismatches if exp > 0]
        implied_tax = sum((lt - exp) for _, exp, lt in mismatches)
        consistent = (len(rates) == len(mismatches) and min(rates) > 0 and max(rates) <= MAX_TAX_RATE
                      and max(rates) - min(rates) <= Decimal("0.01"))
        corroborated = (abs(implied_tax - tax) <= line_tol) if tax is not None else len(mismatches) >= 2
        if consistent and corroborated:
            issues.append(Issue("line_totals_include_tax", "info",
                                f"Line totals appear tax-inclusive (implied rate ~{(sum(rates) / len(rates) * 100):.1f}%)",
                                "line_items", {"implied_tax": _s(implied_tax)}))
        else:
            for i, exp, lt in mismatches:
                issues.append(Issue("line_total_mismatch", "error",
                                    f"Line {i + 1}: quantity x unit price = {_s(exp)}, but line total is {_s(lt)}",
                                    f"line_items[{i}]", {"expected": _s(exp), "actual": _s(lt)}))

    if not missing_total and (sub is not None or total is not None):
        s = sum(p for p in parsed if p is not None)
        cands = {}
        if sub is not None:
            cands["subtotal"] = sub
            if tax is not None:
                cands["subtotal_plus_tax"] = sub + tax
        if total is not None:
            cands["total"] = total
            cands["total_plus_discount"] = total + (abs(disc) if disc is not None else Decimal(0))
        hit = next((k for k, v in cands.items() if abs(v - s) <= line_tol), None)
        if hit is None:
            issues.append(Issue("line_sum_mismatch", "error",
                                f"Line items add up to {_s(s)}, which matches neither subtotal nor total",
                                "line_items", {"sum": _s(s), **{k: _s(v) for k, v in cands.items()}}))
        else:
            issues.append(Issue("line_sum_consistent", "info", f"Line items add up to {_s(s)} (matches {hit})", "line_items"))


def _tax_ids(text: str, issues):
    """OCR turns 0->O and 1->I/l. In an Indian GSTIN the digit slots can never hold
    letters, so a letter there is almost certainly an OCR error (seen on a real sample)."""
    seen = set()
    for tok in _TAX_ID_LOOSE.findall(text):
        if tok in seen:
            continue
        seen.add(tok)
        if any(c in "OIl" for sl in _DIGIT_SLOTS for c in tok[sl]):
            fixed = "".join(("0" if c == "O" else "1") if (c in "OIl" and (i < 2 or 7 <= i < 11)) else c
                            for i, c in enumerate(tok))
            issues.append(Issue("suspected_ocr_error_in_tax_id", "warning",
                                f"Tax ID '{tok}' has letters where digits are required (OCR?); maybe '{fixed}'",
                                "tax_id", {"found": tok, "suggested": fixed}))


def _duplicates(x, doc_id, file_hash, index, issues, tol):
    rec = record_from_extraction(x, doc_id, file_hash)
    reported: set[str] = set()
    for o in index.candidates(rec):
        if rec.file_hash and o.file_hash == rec.file_hash:
            issues.append(Issue("duplicate_file", "error", f"Identical file already processed (document {o.doc_id})",
                                None, {"other": o.doc_id}))
        elif rec.supplier_key and rec.invoice_key and o.supplier_key == rec.supplier_key and o.invoice_key == rec.invoice_key:
            same_total = rec.total is not None and o.total is not None and abs(rec.total - o.total) <= tol
            if same_total:
                issues.append(Issue("duplicate_invoice", "error",
                                    f"Same supplier, invoice number and total as document {o.doc_id}",
                                    "invoice_number", {"other": o.doc_id}))
            else:
                issues.append(Issue("invoice_number_reused", "warning",
                                    f"Invoice number already used by document {o.doc_id} with a different total",
                                    "invoice_number", {"other": o.doc_id,
                                                       "other_total": _s(o.total) if o.total is not None else None}))
        elif o.doc_id not in reported:
            issues.append(Issue("possible_duplicate", "warning",
                                f"Same supplier, total and date as document {o.doc_id} but a different invoice number",
                                "invoice_number", {"other": o.doc_id}))
        reported.add(o.doc_id)
