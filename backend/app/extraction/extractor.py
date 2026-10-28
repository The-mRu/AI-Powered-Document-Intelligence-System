from app.pipelines.models import ProcessedDocument

from .llm import LLMClient
from .prompts import SYSTEM_PROMPT, build_user_message
from .schema import MONEY_FIELDS, SCALAR_FIELDS
from .verify import LOW_CONFIDENCE, check_field, check_line_item, norm, numbers_in

MAX_CHARS = 60_000  # ~15k tokens; longer docs need per-invoice chunking (see PROJECT_BRAIN)


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
        raw = getattr(parsed, name).model_dump()
        result[name] = check_field(name, raw, text, src_norm, src_nums, money=name in MONEY_FIELDS)
    result["line_items"] = [check_line_item(li.model_dump(), src_norm, src_nums) for li in parsed.line_items]

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
