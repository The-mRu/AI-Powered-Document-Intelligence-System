"""PDF pipeline: per-page routing between the text layer and OCR.

A 1000-page PDF is a *generator* of PageResults, so the caller can persist each
page as it finishes (progress bar, partial results, bounded memory). One bad
page never kills the document.
"""
import re
import time
from typing import Iterator

import pymupdf as fitz  # PyMuPDF
from PIL import Image

from .errors import CorruptedFileError, EncryptedFileError
from .models import PageResult
from .ocr import ocr_image

MIN_TEXT_CHARS = 25  # below this a page has no usable text layer
OCR_DPI = 300
MAX_RENDER_PIXELS = 40_000_000  # protects RAM on huge page boxes (posters/maps)


def iter_pdf_pages(path) -> Iterator[PageResult]:
    try:
        doc = fitz.open(path)
    except Exception as e:  # PyMuPDF raises FileDataError / RuntimeError
        raise CorruptedFileError(f"Cannot open PDF: {e}") from e
    with doc:
        if doc.needs_pass:
            raise EncryptedFileError("PDF is password protected")
        if doc.page_count == 0:
            raise CorruptedFileError("PDF has no pages")
        for idx in range(doc.page_count):
            yield _process_page(doc, idx)


def _needs_ocr(page: "fitz.Page", text: str) -> bool:
    chars = len(re.sub(r"\s+", "", text))
    if chars < MIN_TEXT_CHARS:
        return True
    # A scan stamped with a tiny text layer (page number, Bates stamp) still has
    # almost no real text: a big image covering the page + little text => OCR it.
    area = abs(page.rect) or 1
    covered = 0.0
    try:
        for info in page.get_image_info():
            covered += abs(fitz.Rect(info["bbox"]) & page.rect)
    except Exception:
        pass
    return covered / area > 0.85 and chars < 300


def _render(page: "fitz.Page") -> Image.Image:
    dpi = OCR_DPI
    w_in, h_in = page.rect.width / 72, page.rect.height / 72
    if w_in * h_in * dpi * dpi > MAX_RENDER_PIXELS:
        dpi = int((MAX_RENDER_PIXELS / (w_in * h_in)) ** 0.5)
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
    return Image.frombytes("L", (pix.width, pix.height), pix.samples)


def _process_page(doc: "fitz.Document", idx: int) -> PageResult:
    start, page_no = time.perf_counter(), idx + 1
    ms = lambda: int((time.perf_counter() - start) * 1000)  # noqa: E731
    try:
        page = doc.load_page(idx)
        text = page.get_text("text", sort=True).strip()
        if not _needs_ocr(page, text):
            return PageResult(page_no, text, "text_layer", duration_ms=ms())
        ocr_text, conf = ocr_image(_render(page))
        return PageResult(page_no, ocr_text, "ocr", conf, duration_ms=ms())
    except Exception as e:
        return PageResult(page_no, "", "failed", error=f"{type(e).__name__}: {e}", duration_ms=ms())
