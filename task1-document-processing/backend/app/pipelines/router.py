"""Single entry point used by the Celery task."""
from pathlib import Path
from typing import Callable

from .detect import detect_kind
from .errors import FileTooLargeError, CorruptedFileError
from .image import iter_image_pages
from .models import PageResult, ProcessedDocument
from .pdf import iter_pdf_pages
from .spreadsheet import process_spreadsheet

MAX_FILE_BYTES = 50 * 1024 * 1024

EXT_TO_KIND = {".pdf": "pdf", ".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png",
               ".tif": "tiff", ".tiff": "tiff", ".xlsx": "xlsx", ".xls": "xls",
               ".csv": "csv", ".tsv": "csv"}


def process_file(path, *, original_name: str | None = None,
                 on_page: Callable[[PageResult], None] | None = None) -> ProcessedDocument:
    """Detect type, run the right pipeline, return a ProcessedDocument.

    `on_page` fires after every page/sheet so the worker can save progress
    incrementally. Raises ProcessingError subclasses only for whole-file
    problems (corrupt, encrypted, unsupported); page-level problems are
    recorded on the PageResult instead.
    """
    path = Path(path)
    if not path.is_file():
        raise CorruptedFileError("File not found")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise FileTooLargeError(f"File exceeds {MAX_FILE_BYTES // 1024 // 1024} MB")

    kind = detect_kind(path)
    warnings = []
    ext = Path(original_name or path.name).suffix.lower()
    if ext in EXT_TO_KIND and EXT_TO_KIND[ext] != kind:
        warnings.append(f"Extension '{ext}' does not match content; processed as {kind}")

    if kind in ("pdf", "jpeg", "png", "tiff"):
        pages_iter = iter_pdf_pages(path) if kind == "pdf" else iter_image_pages(path)
        pages = []
        for p in pages_iter:
            pages.append(p)
            if on_page:
                on_page(p)
        doc = ProcessedDocument(kind, pages)
    else:
        doc = process_spreadsheet(path, kind)
        if on_page:
            for p in doc.pages:
                on_page(p)

    doc.warnings = warnings + doc.warnings
    return doc
