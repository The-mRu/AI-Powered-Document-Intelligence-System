"""Deterministic guards that run AFTER the LLM. This is what makes "never invent
values" a guarantee enforced by code instead of a hope expressed in a prompt.

A value survives only if it can be found in the source text. Otherwise it is
nulled and flagged. We cannot prove a value is *right*, but we can prove it is
not *made up*; Task 3 then checks the arithmetic.
"""
import re
from decimal import Decimal, InvalidOperation

LOW_CONFIDENCE = 0.7


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def numbers_in(text: str) -> set[Decimal]:
    """Every number in the text. 1,234.50 is read the US way; 1.234,50 the European
    way ONLY when a decimal comma is actually present. (Reading every "8.50" as a
    possible 850 would let invented amounts pass; a test caught exactly that.)"""
    found: set[Decimal] = set()
    for tok in re.findall(r"\d[\d.,]*\d|\d", text):
        cands = [tok.replace(",", "")]
        if "," in tok and tok.rfind(",") > tok.rfind("."):
            cands.append(tok.replace(".", "").replace(",", "."))
        for cand in cands:
            try:
                found.add(Decimal(cand))
            except InvalidOperation:
                pass
    return found


def to_decimal(s: str | None) -> Decimal | None:
    if s is None:
        return None
    s = s.strip().replace(",", "")
    if not re.fullmatch(r"-?\d+(\.\d+)?", s):
        return None
    return Decimal(s)


def clamp(c: float | None) -> float:
    try:
        return max(0.0, min(1.0, float(c)))
    except (TypeError, ValueError):
        return 0.0


_AMBIG_DATE = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b")


def check_field(name: str, raw: dict, source: str, src_norm: str, src_numbers: set[Decimal],
                money: bool) -> dict:
    """raw = {value, confidence, evidence}. Returns the verified field dict."""
    value, ev = raw.get("value"), raw.get("evidence")
    conf, flags = clamp(raw.get("confidence")), []

    def drop(flag: str):
        return {"value": None, "confidence": 0.0, "evidence": None, "status": "missing",
                "flags": flags + [flag]}

    if value is None or str(value).strip() == "":
        return {"value": None, "confidence": 0.0, "evidence": None, "status": "missing", "flags": flags}
    value = str(value).strip()

    if not ev:
        return drop("no_evidence")
    ev_ok = norm(ev) in src_norm
    if not ev_ok:
        flags.append("evidence_not_verbatim")
        conf = min(conf, 0.6)

    if money:
        d = to_decimal(value)
        if d is None:
            return drop("unparseable_amount")
        if d not in src_numbers:
            return drop("value_not_in_source")
        if d not in numbers_in(ev):  # the quoted evidence must actually contain the number
            flags.append("value_not_in_evidence")
            conf = min(conf, 0.4)
        value = format(d, "f")
    elif name == "invoice_date":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return drop("bad_date_format")
        if not ev_ok or value[:4] not in src_norm and value[2:4] not in src_norm:
            return drop("date_not_in_source")
        m = _AMBIG_DATE.search(ev)
        if m and int(m[1]) <= 12 and int(m[2]) <= 12 and m[1] != m[2]:
            flags.append("ambiguous_date_format")
            conf = min(conf, 0.5)
    elif name == "currency":
        value = value.upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            return drop("bad_currency_code")
        if re.sub(r"[\d\s.,:]", "", ev).strip() == "$":
            return drop("currency_ambiguous_dollar_sign")
        if not ev_ok:
            return drop("currency_evidence_not_in_source")
    else:  # free text: name, invoice number, ...
        if norm(value) not in src_norm:
            return drop("value_not_in_source")

    status = "uncertain" if (flags or conf < LOW_CONFIDENCE) else "ok"
    return {"value": value, "confidence": round(conf, 3), "evidence": ev, "status": status, "flags": flags}


def _parse_quantity(v: str | None) -> tuple[Decimal | None, str | None]:
    """'5' -> (5, None); '5 KG' -> (5, 'KG'). Models often glue the unit on."""
    if v is None:
        return None, None
    d = to_decimal(v)
    if d is not None:
        return d, None
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([A-Za-z./]+)\s*", v)
    return (Decimal(m[1]), m[2]) if m else (None, None)


def check_line_item(item: dict, src_norm: str, src_numbers: set[Decimal]) -> dict:
    flags, out = [], {}
    qty, glued_unit = _parse_quantity(item.get("quantity"))
    parsed = {"quantity": qty, "unit_price": to_decimal(item.get("unit_price")),
              "line_total": to_decimal(item.get("line_total"))}
    for key, d in parsed.items():
        if item.get(key) is None:
            out[key] = None
        elif d is None:
            flags.append(f"{key}_unparseable")
            out[key] = None
        elif d not in src_numbers:
            flags.append(f"{key}_not_in_source")
            out[key] = None
        else:
            out[key] = format(d, "f")
    unit = item.get("unit") or glued_unit
    out["unit"] = unit if unit and norm(unit) in src_norm else None
    desc = item.get("description")
    if desc and norm(desc) not in src_norm:
        flags.append("description_not_in_source")
        desc = None
    out["description"] = desc
    conf = clamp(item.get("confidence"))
    out["confidence"] = round(min(conf, 0.5) if flags else conf, 3)
    out["evidence"] = item.get("evidence")
    out["flags"] = flags
    return out
