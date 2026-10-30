"""Generate the reproducible 15-document extraction benchmark dataset.

Labels are built from the invoice dictionaries before any file is rendered.
They are never read back from OCR, extraction, or validation output.
"""
from __future__ import annotations

import csv
import json
import random
import shutil
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "extraction_dataset"
SEED = 20261030
MONEY = Decimal("0.01")


def money(value: Decimal) -> str:
    return str(value.quantize(MONEY, rounding=ROUND_HALF_UP))


def font(size: int):
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def make_invoice(rng: random.Random, index: int) -> dict:
    european = index % 4 == 0
    tax_inclusive = index % 3 == 0
    has_discount = index % 3 != 1
    discount_percent = index % 5 == 0
    has_shipping = index % 4 == 1
    has_payment = index % 5 == 2
    currency = None if index == 7 else ("EUR" if european else "USD")
    supplier = ["Northstar Office GmbH", "Blue Harbor Trading", "Cedar Ridge Supplies"][index % 3]
    customer = ["Atlas Retail Group", "Summit Works", "Pinecrest Services"][index % 3]
    item_count = 1 + (index * 3) % 8
    items = []
    subtotal = Decimal("0")
    for item_index in range(item_count):
        quantity = Decimal(str([1, 2, 3, 5, "2.5"][rng.randrange(5)]))
        unit = ["pcs", "boxes", "kg", "litres"][item_index % 4]
        unit_price = Decimal(str(rng.randrange(12, 180))) + Decimal("0.50")
        line_total = (quantity * unit_price).quantize(MONEY)
        subtotal += line_total
        items.append({
            "description": ["Paper", "Milk", "Cable", "Gloves", "Labels", "Soap"][item_index % 6],
            "quantity": str(quantity),
            "unit": unit,
            "unit_price": money(unit_price),
            "line_total": money(line_total),
            "tax": "8%" if index % 2 else "10%",
            "discount": "5%" if has_discount and index % 2 else None,
        })

    tax_rate = Decimal("0.20") if european else Decimal("0.10")
    tax = (subtotal * tax_rate).quantize(MONEY)
    discount = None
    discount_amount = Decimal("0")
    if has_discount:
        if discount_percent:
            discount = "5%"
            discount_amount = (subtotal * Decimal("0.05")).quantize(MONEY)
        else:
            discount_amount = (subtotal * Decimal("0.03")).quantize(MONEY)
            discount = money(discount_amount)
    shipping = money(Decimal("25.00")) if has_shipping else None
    other_charges = money(Decimal("7.50")) if index % 6 == 0 else None
    charges = Decimal(shipping or "0") + Decimal(other_charges or "0")
    total = subtotal - discount_amount + charges if tax_inclusive else subtotal + tax - discount_amount + charges
    payments = money(total / 2) if has_payment else None
    balance = money(total - Decimal(payments)) if payments else None

    return {
        "invoice_number": f"INV-{2026:04d}-{index + 1:04d}",
        "invoice_date": f"2026-{(index % 9) + 1:02d}-{(index % 25) + 1:02d}",
        "supplier_name": supplier,
        "customer_name": customer,
        "subtotal": money(subtotal),
        "tax": money(tax),
        "discount": discount,
        "total": money(total),
        "currency": currency,
        "shipping": shipping,
        "other_charges": other_charges,
        "payments_received": payments,
        "balance_due": balance,
        "tax_inclusive": tax_inclusive,
        "line_items": items,
    }


def display_number(value: str | None, european: bool) -> str | None:
    if value is None:
        return None
    if value.endswith("%"):
        return value.replace(".", ",") if european else value
    if european:
        integer, _, fraction = value.partition(".")
        return f"{integer},{fraction}" if fraction else integer
    return value


def invoice_lines(invoice: dict, european: bool) -> list[str]:
    cur = invoice["currency"] or ""
    lines = [
        "INVOICE",
        f"Invoice Number: {invoice['invoice_number']}",
        f"Date: {invoice['invoice_date']}",
        f"Supplier: {invoice['supplier_name']}",
        f"Customer: {invoice['customer_name']}",
        "ITEM DESCRIPTION | QTY | UNIT | UNIT PRICE | LINE TOTAL | TAX | DISCOUNT",
    ]
    for item in invoice["line_items"]:
        values = [
            item["description"], item["quantity"], item["unit"],
            display_number(item["unit_price"], european),
            display_number(item["line_total"], european),
            item["tax"] or "", item["discount"] or "",
        ]
        lines.append(" | ".join(values))
    lines.extend([
        f"Subtotal: {display_number(invoice['subtotal'], european)}",
        f"Tax: {display_number(invoice['tax'], european)}",
        f"Discount: {display_number(invoice['discount'], european) or ''}",
        f"Shipping: {display_number(invoice['shipping'], european) or ''}",
        f"Other Charges: {display_number(invoice['other_charges'], european) or ''}",
        f"Total: {display_number(invoice['total'], european)} {cur}".rstrip(),
    ])
    if invoice["payments_received"] is not None:
        lines.extend([
            f"Payments Received: {display_number(invoice['payments_received'], european)}",
            f"Balance Due: {display_number(invoice['balance_due'], european)}",
        ])
    return lines


def write_pdf(path: Path, lines: list[str], two_column: bool) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    y = 55
    for line in lines:
        if two_column and line.startswith("Supplier:"):
            page.insert_text((45, y), line, fontsize=10)
            continue
        if two_column and line.startswith("Customer:"):
            page.insert_text((320, y), line, fontsize=10)
            y += 26
            continue
        page.insert_text((45, y), line, fontsize=10)
        y += 18
        if y > 790:
            page = doc.new_page(width=595, height=842)
            y = 55
    if two_column:
        page.insert_text((350, 820), "Two-column supplier/customer layout", fontsize=8)
    doc.save(path)


def write_image(path: Path, lines: list[str], rng: random.Random) -> None:
    image = Image.new("RGB", (1800, 2400), "white")
    draw = ImageDraw.Draw(image)
    y = 100
    for line in lines:
        draw.text((100, y), line, fill="black", font=font(42))
        y += 75
    image = image.rotate(rng.uniform(2, 4), expand=True, fillcolor="white")
    image = image.filter(ImageFilter.GaussianBlur(1.0))
    image.save(path, quality=72)


def write_xlsx(path: Path, invoice: dict) -> None:
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Invoice"
    sheet.append(["Invoice Register"])
    sheet.append([])
    sheet.append(["Invoice Number", "Date", "Supplier", "Customer", "Currency"])
    sheet.append([
        invoice["invoice_number"], invoice["invoice_date"], invoice["supplier_name"],
        invoice["customer_name"], invoice["currency"],
    ])
    sheet.append([])
    sheet.append(["Description", "Quantity", "Unit", "Unit Price", "Line Total", "Tax", "Discount"])
    for item in invoice["line_items"]:
        sheet.append([
            item["description"], item["quantity"], item["unit"], item["unit_price"],
            item["line_total"], item["tax"], item["discount"],
        ])
    sheet.append([])
    for label in ("subtotal", "tax", "discount", "shipping", "other_charges", "total",
                  "payments_received", "balance_due"):
        sheet.append([label.replace("_", " ").title(), invoice[label]])
    workbook.save(path)


def write_csv(path: Path, invoice: dict) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["Invoice Number", "Date", "Supplier", "Customer", "Currency"])
        writer.writerow([
            invoice["invoice_number"], invoice["invoice_date"], invoice["supplier_name"],
            invoice["customer_name"], invoice["currency"] or "",
        ])
        writer.writerow([])
        writer.writerow(["Description", "Quantity", "Unit", "Unit Price", "Line Total", "Tax", "Discount"])
        for item in invoice["line_items"]:
            writer.writerow([
                item["description"], item["quantity"], item["unit"], item["unit_price"],
                item["line_total"], item["tax"] or "", item["discount"] or "",
            ])
        writer.writerow([])
        for label in ("subtotal", "tax", "discount", "shipping", "other_charges", "total",
                      "payments_received", "balance_due"):
            writer.writerow([label.replace("_", " ").title(), invoice[label] or ""])


def make_expected_failures(directory: Path) -> list[dict]:
    corrupted = directory / "corrupted.pdf"
    corrupted.write_bytes(b"%PDF-1.7\nnot a valid PDF")
    empty = directory / "empty.pdf"
    empty.write_bytes(b"")
    password = directory / "password-protected.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Protected invoice")
    doc.save(password, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    executable = directory / "executable-renamed.pdf"
    executable.write_bytes(b"MZ\x90\x00This is not a document")
    return [
        {"filename": p.name, "path": str(Path("evaluation/extraction_dataset/expected_failures") / p.name),
         "document_type": "expected_failure"} for p in (corrupted, empty, password, executable)
    ]


def main() -> int:
    rng = random.Random(SEED)
    if OUT.exists():
        shutil.rmtree(OUT)
    valid_dir = OUT / "valid"
    failure_dir = OUT / "expected_failures"
    valid_dir.mkdir(parents=True)
    failure_dir.mkdir(parents=True)

    documents = []
    for index in range(15):
        invoice = make_invoice(rng, index)
        if index < 8:
            suffix, kind = ".pdf", "pdf"
        elif index < 12:
            suffix, kind = ".jpg", "image"
        elif index < 14:
            suffix, kind = ".xlsx", "spreadsheet"
        else:
            suffix, kind = ".csv", "spreadsheet"
        filename = f"invoice-{index + 1:02d}{suffix}"
        path = valid_dir / filename
        lines = invoice_lines(invoice, european=index % 4 == 0)
        if kind == "pdf":
            write_pdf(path, lines, two_column=index % 2 == 0)
        elif kind == "image":
            write_image(path, lines, rng)
        elif suffix == ".xlsx":
            write_xlsx(path, invoice)
        else:
            write_csv(path, invoice)
        documents.append({
            "filename": filename,
            "path": str(Path("evaluation/extraction_dataset/valid") / filename),
            "document_type": kind,
            "ground_truth": invoice,
        })

    manifest = {
        "seed": SEED,
        "valid_document_count": len(documents),
        "expected_failure_count": 4,
        "documents": documents,
        "expected_failures": make_expected_failures(failure_dir),
    }
    (OUT / "labels.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "valid_documents": len(documents),
        "expected_failures": len(manifest["expected_failures"]),
        "labels": str(OUT / "labels.json"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
