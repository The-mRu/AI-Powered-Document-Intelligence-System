import pymupdf
import pytest

from app.pipelines import (CorruptedFileError, EncryptedFileError, FileTooLargeError,
                           UnsupportedFileError, process_file)
from app.pipelines import router


def norm(s: str) -> str:
    return "".join(s.split()).upper()


# ---------- PDF ----------
def test_digital_pdf_uses_text_layer_not_ocr(digital_pdf):
    doc = process_file(digital_pdf)
    assert doc.status == "completed" and len(doc.pages) == 3
    assert all(p.method == "text_layer" for p in doc.pages)
    assert "INV-2024-0042" in doc.full_text


def test_scanned_pdf_falls_back_to_ocr(scanned_pdf):
    doc = process_file(scanned_pdf)
    assert doc.pages[0].method == "ocr"
    assert "INV-2024-0042" in norm(doc.full_text)
    assert doc.pages[0].confidence and doc.pages[0].confidence > 60


def test_mixed_pdf_routes_each_page_independently(mixed_pdf):
    doc = process_file(mixed_pdf)
    assert [p.method for p in doc.pages] == ["text_layer", "ocr"]


def test_progress_callback_fires_per_page(digital_pdf):
    seen = []
    process_file(digital_pdf, on_page=seen.append)
    assert [p.page_no for p in seen] == [1, 2, 3]


def test_many_page_pdf_streams(tmp_path):
    d = pymupdf.open()
    for i in range(300):
        d.new_page().insert_text((72, 100), f"Page {i} " + "lorem ipsum dolor sit amet " * 3, fontsize=10)
    p = tmp_path / "big.pdf"
    d.save(p)
    doc = process_file(p)
    assert len(doc.pages) == 300 and doc.status == "completed"


def test_encrypted_pdf_rejected_with_clear_error(tmp_path):
    d = pymupdf.open()
    d.new_page().insert_text((72, 100), "secret")
    p = tmp_path / "locked.pdf"
    d.save(p, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    with pytest.raises(EncryptedFileError):
        process_file(p)


def test_corrupted_pdf_raises_corrupted(tmp_path):
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"%PDF-1.7\n1 0 obj << /Garbage >> endobj\nnot a real pdf at all")
    with pytest.raises(CorruptedFileError):
        process_file(p)


def test_truncated_pdf_is_corrupted_or_partial(tmp_path, digital_pdf):
    p = tmp_path / "trunc.pdf"
    p.write_bytes(digital_pdf.read_bytes()[:400])
    try:
        doc = process_file(p)
        assert doc.status in ("partial", "failed")
    except CorruptedFileError:
        pass


# ---------- Images ----------
def test_clean_png(png_path):
    doc = process_file(png_path)
    assert doc.kind == "png" and "INV-2024-0042" in norm(doc.full_text)


def test_poor_quality_jpg_still_extracts_key_fields(poor_quality_jpg):
    # rotated 3 deg + blur + noise + JPEG q35
    doc = process_file(poor_quality_jpg)
    text = norm(doc.full_text)
    assert "INV-2024-0042" in text and "1150.00" in text
    assert doc.pages[0].confidence > 80


def test_upside_down_scan_is_auto_rotated(upside_down_png):
    assert "INVOICE" in norm(process_file(upside_down_png).full_text)


def test_multipage_tiff_yields_one_result_per_frame(multi_tiff):
    doc = process_file(multi_tiff)
    assert len(doc.pages) == 2 and "INV-2024-0099" in norm(doc.pages[1].text)


def test_corrupted_image_raises(tmp_path):
    p = tmp_path / "bad.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
    with pytest.raises(CorruptedFileError):
        process_file(p)


def test_renamed_file_detected_by_content(png_path, tmp_path):
    fake = tmp_path / "invoice.pdf"
    fake.write_bytes(png_path.read_bytes())
    doc = process_file(fake)
    assert doc.kind == "png" and any("does not match" in w for w in doc.warnings)


# ---------- Spreadsheets ----------
def test_xlsx_multiple_sheets_header_detection_and_leading_zeros(multi_sheet_xlsx):
    doc = process_file(multi_sheet_xlsx)
    names = [s.name for s in doc.sheets]
    assert names == ["Invoices", "Lines"]  # empty sheet skipped, warned
    inv = doc.sheets[0]
    assert inv.header_row == 3 and inv.columns == ["Invoice No", "Date", "Supplier", "Total"]
    assert inv.rows[0]["Invoice No"] == "00123"  # leading zeros preserved
    assert any("empty" in w for w in doc.warnings)
    assert all(p.method == "spreadsheet" for p in doc.pages)


def test_csv_semicolon_and_cp1252_encoding(semicolon_csv):
    doc = process_file(semicolon_csv)
    s = doc.sheets[0]
    assert s.columns == ["Rechnung", "Lieferant", "Betrag"]
    assert s.rows[0]["Lieferant"] == "Müller GmbH" and s.rows[0]["Betrag"] == "1150,50"
    assert any("cp1252" in w for w in doc.warnings)


def test_empty_csv_and_empty_file(tmp_path):
    for name in ("a.csv", "b.pdf"):
        p = tmp_path / name
        p.write_bytes(b"")
        with pytest.raises(CorruptedFileError):
            process_file(p)


def test_corrupted_xlsx(tmp_path):
    p = tmp_path / "bad.xlsx"
    p.write_bytes(b"PK\x03\x04" + b"garbage" * 20)
    with pytest.raises(CorruptedFileError):
        process_file(p)


def test_fake_xls_is_not_silently_accepted(tmp_path):
    p = tmp_path / "bad.xls"
    p.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 200)
    with pytest.raises((CorruptedFileError, UnsupportedFileError, EncryptedFileError)):
        process_file(p)


# ---------- Guards ----------
def test_unsupported_type(tmp_path):
    p = tmp_path / "notes.exe"
    p.write_bytes(b"MZ\x90\x00" + b"\x00" * 100)
    with pytest.raises(UnsupportedFileError):
        process_file(p)


def test_oversize_file_rejected(tmp_path, monkeypatch, digital_pdf):
    monkeypatch.setattr(router, "MAX_FILE_BYTES", 100)
    with pytest.raises(FileTooLargeError):
        process_file(digital_pdf)


# ---------- Real .xls and legacy Office containers ----------
def test_real_xls_is_parsed(real_xls):
    doc = process_file(real_xls)
    assert doc.kind == "xls"
    inv = doc.sheets[0]
    assert inv.header_row == 3 and inv.columns == ["Invoice No", "Date", "Supplier", "Total"]
    assert inv.rows[0]["Invoice No"] == "00123" and inv.rows[1]["Total"] == 99.5


@pytest.mark.parametrize("stream,exc", [("WordDocument", UnsupportedFileError),
                                        ("PowerPoint Document", UnsupportedFileError),
                                        ("EncryptedPackage", EncryptedFileError)])
def test_legacy_office_containers_get_accurate_errors(tmp_path, monkeypatch, stream, exc):
    from app.pipelines import detect

    class FakeOle:
        def __init__(self, *_): pass
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def exists(self, name): return name == stream

    monkeypatch.setattr(detect.olefile, "OleFileIO", FakeOle)
    p = tmp_path / "x.doc"
    p.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100)
    with pytest.raises(exc):
        process_file(p)


def test_docx_gets_helpful_message(tmp_path):
    import zipfile
    p = tmp_path / "a.docx"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("word/document.xml", "<x/>")
    with pytest.raises(UnsupportedFileError, match="export to PDF"):
        process_file(p)
