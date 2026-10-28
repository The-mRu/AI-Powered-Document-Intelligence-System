"""What the LLM must return. Every field carries its own confidence and evidence,
and "unknown" is a first-class answer (value = null), never a guess.

Strict structured outputs need every key present, so nullability is expressed
with `| None`, not with defaults. Money/dates are strings here and become
Decimal/date only in our own deterministic code (floats corrupt money).
"""
from pydantic import BaseModel


class Field(BaseModel):
    value: str | None
    confidence: float  # 0..1, model's own estimate; we clamp and may lower it
    evidence: str | None  # exact text copied from the document


class LineItem(BaseModel):
    description: str | None
    quantity: str | None  # number only, e.g. "5"
    unit: str | None = None  # e.g. "KG"
    unit_price: str | None
    line_total: str | None
    confidence: float
    evidence: str | None


class InvoiceLLM(BaseModel):
    invoice_number: Field
    invoice_date: Field
    supplier_name: Field
    customer_name: Field
    subtotal: Field
    tax: Field
    discount: Field  # not in the brief, but needed to reconcile real invoices
    total: Field
    currency: Field
    line_items: list[LineItem]


SCALAR_FIELDS = ["invoice_number", "invoice_date", "supplier_name", "customer_name",
                 "subtotal", "tax", "discount", "total", "currency"]
MONEY_FIELDS = {"subtotal", "tax", "discount", "total"}
