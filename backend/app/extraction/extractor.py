import re

from app.pipelines.models import ProcessedDocument

from .llm import LLMClient
from .prompts import SYSTEM_PROMPT, build_user_message
from .schema import MONEY_FIELDS, SCALAR_FIELDS
from .verify import check_field, check_line_item, norm, numbers_in, source_contains

MAX_CHARS = 60_000  # ~15k tokens; longer docs need per-invoice chunking (see PROJECT_BRAIN)


def _party_from_labeled_block(text: str, label: str) -> tuple[str | None, str | None]:
    match = re.search(rf"\b{label}\s*:?(.*?)(?=\b(?:BILL\s+TO|SHIP\s+TO|INVOICE)\b|$)",
                      text, re.I | re.S)
    if not match:
        return None, None
    lines = []
    for line in match.group(1).splitlines():
        line = re.sub(r"\s+", " ", line).strip(" \t:,-")
        if not line or re.match(r"(?:H\.?\s*No|PIN|[A-Z][A-Za-z ]*-\s*\d)", line, re.I):
            break
        if re.search(r"\b(order\s+number|invoice\s+date|due\s+date)\b", line, re.I):
            return None, None
        lines.append(line)
        if len(lines) == 2:
            break
    return (" ".join(lines), "\n".join(lines)) if lines else (None, None)


def _party_name_from_header(text: str, label: str) -> tuple[str | None, str | None]:
    match = re.search(rf"\b{label}\b(.*?)(?=\b(?:FROM|BILL\s+TO|SHIP\s+TO|INVOICE)\b|$)",
                      text, re.I | re.S)
    if not match:
        return None, None
    lines = []
    for line in match.group(1).splitlines():
        line = re.sub(r"\s+", " ", line).strip(" \t:,-")
        if not line or re.match(r"(?:H\.?\s*No|PIN|[A-Z][A-Za-z ]*-\s*\d)", line, re.I):
            break
        lines.append(line)
        if len(lines) == 2:
            break
    return (" ".join(lines), "\n".join(lines)) if lines else (None, None)


def _party_from_multicolumn_header(text: str, column: int) -> tuple[str | None, str | None]:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if re.search(r"\bFROM\b", line, re.I) and re.search(r"\bBILL\s+TO\b", line, re.I):
            names, evidence = [], []
            for candidate_line in lines[index + 1:]:
                candidate_line = re.sub(r"\s+", " ", candidate_line).strip()
                if not candidate_line:
                    continue
                if re.match(r"H\.?\s*No\b", candidate_line, re.I):
                    break
                if re.search(r"\b(?:INVOICE|DATE|NUMBER)\b", candidate_line, re.I):
                    continue
                words = candidate_line.split()
                if len(words) < 2 or len(words) % 2:
                    break
                width = len(words) // 2
                names.append(" ".join(words[column * width:(column + 1) * width]))
                evidence.append(" ".join(words[column * width:(column + 1) * width]))
                if len(names) == 2:
                    return " ".join(names), "\n".join(evidence)
    return None, None


def _table_rows(text: str) -> list[dict] | None:
    if not re.search(r"\bS\.?\s*NO\b.*\bNAME\b.*\bQTY\b.*\bDISCOUNT\b.*\bTAX\b.*\bPRICE\b",
                     text, re.I | re.S):
        return None
    rows = []
    pattern = re.compile(
        r"^\s*\d+\s+(?P<description>[A-Za-z][A-Za-z ]*?)\s+"
        r"(?P<quantity>\d+(?:\.\d+)?)\s+(?P<unit>[A-Za-z]+)\s+"
        r"(?P<discount>\d+(?:\.\d+)?%)\s+(?P<tax>\d+(?:\.\d+)?%)\s+"
        r"(?P<price>\d+(?:\.\d+)?)\s*$", re.I
    )
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            row = match.groupdict()
            rows.append({
                "description": row["description"].strip(),
                "quantity": row["quantity"],
                "unit": row["unit"],
                "unit_price": row["price"],
                "line_total": None,
                "tax": row["tax"],
                "discount": row["discount"],
                "confidence": 0.8,
                "evidence": line.strip(),
            })
    return rows or None


class ExtractionError(Exception):
    code = "extraction_failed"


def build_source_text(doc: ProcessedDocument) -> str:
    parts = []
    for p in doc.pages:
        if p.text:
            label = f"[Sheet: {p.label}]" if p.label else f"[Page {p.page_no}]"
            parts.append(f"{label}\n{p.text}")
    return "\n\n".join(parts)


def extract_invoice(text: str, llm: LLMClient) -> dict:
    """text -> verified JSON. Never returns a value that is not found in `text`."""
    warnings = []
    if not text.strip():
        raise ExtractionError("No text to extract from (empty document)")
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
        warnings.append(f"Text truncated to {MAX_CHARS} characters; later content was not analysed")

    try:
        parsed, usage = llm.extract(SYSTEM_PROMPT, build_user_message(text))
    except Exception as e:
        raise ExtractionError(f"LLM call failed: {type(e).__name__}: {e}") from e

    src_norm, src_nums = norm(text), numbers_in(text)
    result: dict = {}
    for name in SCALAR_FIELDS:
        field = getattr(parsed, name, None)
        raw = field.model_dump() if field is not None else {"value": None, "confidence": 0, "evidence": None}
        result[name] = check_field(name, raw, text, src_norm, src_nums, money=name in MONEY_FIELDS)
    for name, label in (("supplier_name", "FROM"), ("customer_name", r"BILL\s+TO")):
        if result[name]["value"] is None or result[name]["flags"]:
            candidate, evidence = _party_name_from_header(text, label)
            candidate, evidence = _party_from_multicolumn_header(
                text, 0 if name == "supplier_name" else 1
            ) if not candidate else (candidate, evidence)
            if not candidate:
                candidate, evidence = _party_from_labeled_block(text, label)
            if candidate and evidence and source_contains(text, evidence):
                result[name] = check_field(
                    name, {"value": candidate, "confidence": 0.8, "evidence": evidence},
                    candidate, norm(candidate), numbers_in(candidate), money=False,
                )
    extracted_items = [check_line_item(li.model_dump(), src_norm, src_nums) for li in parsed.line_items]
    table_items = _table_rows(text)
    if table_items and len(extracted_items) < len(table_items):
        extracted_items = [check_line_item(item, src_norm, src_nums) for item in table_items]
    result["line_items"] = extracted_items

    result["needs_review_fields"] = [
        n for n in SCALAR_FIELDS
        if result[n]["status"] == "uncertain"
        or (result[n]["status"] == "missing" and result[n]["flags"])  # nulled by a guard
    ]
    if any(li["flags"] for li in result["line_items"]):
        result["needs_review_fields"].append("line_items")
    result["warnings"] = warnings
    result["model"] = llm.model
    result["usage"] = usage
    return result


def extract_from_document(doc: ProcessedDocument, llm: LLMClient) -> dict:
    return extract_invoice(build_source_text(doc), llm)
