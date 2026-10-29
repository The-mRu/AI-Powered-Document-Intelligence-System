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
    tax: str | None = None
    discount: str | None = None


class InvoiceLLM(BaseModel):
    invoice_number: Field
    invoice_date: Field
    supplier_name: Field
    supplier_address: Field
    supplier_city: Field
    supplier_postal_code: Field
    customer_name: Field
    customer_address: Field
    customer_city: Field
    customer_postal_code: Field
    ship_to_name: Field
    ship_to_address: Field
    ship_to_city: Field
    ship_to_postal_code: Field
    subtotal: Field
    tax: Field
    discount: Field  # not in the brief, but needed to reconcile real invoices
    total: Field
    currency: Field
    line_items: list[LineItem]
    shipping: Field | None
    other_charges: Field | None
    payments_received: Field | None
    balance_due: Field | None


SCALAR_FIELDS = ["invoice_number", "invoice_date", "supplier_name", "supplier_address",
                 "supplier_city", "supplier_postal_code", "customer_name", "customer_address",
                 "customer_city", "customer_postal_code", "ship_to_name", "ship_to_address",
                 "ship_to_city", "ship_to_postal_code",
                 "subtotal", "tax", "discount", "total", "currency"]
SCALAR_FIELDS += ["shipping", "other_charges", "payments_received", "balance_due"]
MONEY_FIELDS = {"subtotal", "tax", "discount", "total", "shipping", "other_charges",
                "payments_received", "balance_due"}
