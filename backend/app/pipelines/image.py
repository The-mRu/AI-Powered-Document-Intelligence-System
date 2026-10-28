"""Image pipeline: JPG / PNG / multi-frame TIFF -> OCR, one result per frame."""
import time
from typing import Iterator

from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

from .errors import CorruptedFileError
from .models import PageResult
from .ocr import ocr_image

Image.MAX_IMAGE_PIXELS = 120_000_000  # raises DecompressionBombError above 2x this


def iter_image_pages(path) -> Iterator[PageResult]:
    try:
        img = Image.open(path)
        img.verify()  # cheap integrity check (headers/CRCs)
        img = Image.open(path)  # verify() invalidates the handle; reopen
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as e:
        raise CorruptedFileError(f"Cannot read image: {e}") from e

    with img:
        for i, frame in enumerate(ImageSequence.Iterator(img)):
            yield _process_frame(frame, i + 1)


def _process_frame(frame: Image.Image, page_no: int) -> PageResult:
    start = time.perf_counter()
    try:
        frame = ImageOps.exif_transpose(frame.copy())  # phone photos carry rotation in EXIF
        text, conf = ocr_image(frame)
        method, err = "ocr", None
    except Exception as e:  # truncated data, OCR timeout, ...
        text, conf, method, err = "", None, "failed", f"{type(e).__name__}: {e}"
    return PageResult(page_no, text, method, conf, error=err,
                      duration_ms=int((time.perf_counter() - start) * 1000))
