"""Deterministic stand-ins for OpenAI, so API/worker tests are free, fast and repeatable."""
import hashlib
import math
import re

from app.extraction.schema import Field, InvoiceLLM, LineItem


def _f(text, pat, value=None):
    m = re.search(pat, text, re.M)
    if not m:
        return Field(value=None, confidence=0.0, evidence=None)
    return Field(value=value or m.group(1), confidence=0.9, evidence=m.group(0))


class FakeLLM:
    """Reads 'Label: value' lines from the document text and 'answers' like a model would."""
    model = "fake-llm"

    def __init__(self):
        self.calls, self.fail = 0, False

    def extract(self, system, user):
        self.calls += 1
        if self.fail:
            raise TimeoutError("LLM unavailable")
        items = [LineItem(description=m[1], quantity=m[2], unit_price=m[3], line_total=m[4], confidence=0.9,
                          evidence=m[0]) for m in re.finditer(r"^(\w+) (\d+) ([\d.]+) ([\d.]+)$", user, re.M)]
        return InvoiceLLM(
            invoice_number=_f(user, r"Invoice Number: (\S+)"), invoice_date=_f(user, r"Invoice Date: (\S+)"),
            supplier_name=_f(user, r"Supplier: (.+)"), customer_name=_f(user, r"Customer: (.+)"),
            supplier_address=Field(value=None, confidence=0.0, evidence=None),
            supplier_city=Field(value=None, confidence=0.0, evidence=None),
            supplier_postal_code=Field(value=None, confidence=0.0, evidence=None),
            customer_address=Field(value=None, confidence=0.0, evidence=None),
            customer_city=Field(value=None, confidence=0.0, evidence=None),
            customer_postal_code=Field(value=None, confidence=0.0, evidence=None),
            ship_to_name=Field(value=None, confidence=0.0, evidence=None),
            ship_to_address=Field(value=None, confidence=0.0, evidence=None),
            ship_to_city=Field(value=None, confidence=0.0, evidence=None),
            ship_to_postal_code=Field(value=None, confidence=0.0, evidence=None),
            subtotal=_f(user, r"Subtotal: ([\d.]+)"), tax=_f(user, r"Tax: ([\d.]+)"),
            discount=Field(value=None, confidence=0.0, evidence=None), total=_f(user, r"Total: ([\d.]+)"),
            currency=_f(user, r"Currency: ([A-Z]{3})"), line_items=items,
            shipping=Field(value=None, confidence=0.0, evidence=None),
            other_charges=Field(value=None, confidence=0.0, evidence=None),
            payments_received=Field(value=None, confidence=0.0, evidence=None),
            balance_due=Field(value=None, confidence=0.0, evidence=None)), {"prompt_tokens": 1, "completion_tokens": 1}


class FakeEmbedder:
    """Bag-of-words hashing: texts sharing words get similar vectors, which is all the tests need."""

    def embed(self, texts):
        out = []
        for t in texts:
            v = [0.0] * 1536
            for w in re.findall(r"[a-z0-9]+", t.lower()):
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 1536] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out
