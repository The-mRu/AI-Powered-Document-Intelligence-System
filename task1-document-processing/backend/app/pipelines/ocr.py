"""OCR with an escalation strategy: cheap pass first, heavy pass only when needed.

Why: aggressive binarisation helps bad scans but can destroy clean ones, and a
second Tesseract run doubles latency. So we measure confidence and escalate.
"""
from collections import OrderedDict

import cv2
import numpy as np
import pytesseract
from PIL import Image

OCR_TIMEOUT_S = 90
GOOD_CONFIDENCE = 70.0


def to_gray(img: Image.Image) -> np.ndarray:
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.alpha_composite(img.convert("RGBA"))
        img = bg.convert("RGB")
    return np.array(img.convert("L"))


def ocr_image(img: Image.Image, lang: str = "eng") -> tuple[str, float | None]:
    """Returns (text, mean_confidence). Raises on Tesseract timeout/crash."""
    gray = _fix_orientation(to_gray(img))
    light = _light(gray)
    text, conf = _run(light, lang, psm=3)
    if conf is not None and conf >= GOOD_CONFIDENCE:
        return text, conf

    strong = _strong(gray)
    text2, conf2 = _run(strong, lang, psm=6)
    if (conf2 or 0) > (conf or 0) or (conf is None and text2):
        return text2, conf2
    return text, conf


def _run(arr: np.ndarray, lang: str, psm: int) -> tuple[str, float | None]:
    d = pytesseract.image_to_data(
        arr, lang=lang, config=f"--oem 1 --psm {psm}",
        output_type=pytesseract.Output.DICT, timeout=OCR_TIMEOUT_S,
    )
    lines: "OrderedDict[tuple, list[str]]" = OrderedDict()
    confs: list[float] = []
    for i, word in enumerate(d["text"]):
        word = word.strip()
        c = float(d["conf"][i])
        if not word or c < 0:
            continue
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        lines.setdefault(key, []).append(word)
        confs.append(c)
    out, prev_block = [], None
    for (block, _, _), words in lines.items():
        if prev_block is not None and block != prev_block:
            out.append("")  # blank line between layout blocks
        out.append(" ".join(words))
        prev_block = block
    return "\n".join(out).strip(), (float(np.mean(confs)) if confs else None)


def _fix_orientation(gray: np.ndarray) -> np.ndarray:
    """Fix 90/180/270 rotated scans using Tesseract OSD. Best-effort: OSD fails
    on pages with little text, in which case we leave the image alone."""
    try:
        osd = pytesseract.image_to_osd(gray, output_type=pytesseract.Output.DICT, timeout=30)
        rot, conf = int(osd["rotate"]), float(osd["orientation_conf"])
    except Exception:
        return gray
    if conf < 1.5 or rot == 0:
        return gray
    code = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}.get(rot)
    return cv2.rotate(gray, code) if code is not None else gray


def _deskew(gray: np.ndarray) -> np.ndarray:
    """Projection-profile deskew: the correct angle makes text lines sharpest
    (largest row-sum variation). Convention-free, unlike minAreaRect."""
    h, w = gray.shape
    s = 800 / max(h, w) if max(h, w) > 800 else 1.0
    small = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    _, bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    sh, sw = bw.shape

    def score(angle: float) -> float:
        m = cv2.getRotationMatrix2D((sw / 2, sh / 2), angle, 1.0)
        rot = cv2.warpAffine(bw, m, (sw, sh), flags=cv2.INTER_NEAREST)
        prof = rot.sum(axis=1, dtype=np.float64)
        return float(np.sum(np.diff(prof) ** 2))

    base = score(0.0)
    if base == 0:  # blank page
        return gray
    best_angle, best = 0.0, base
    for a in np.arange(-10, 10.01, 0.5):
        sc = score(float(a))
        if sc > best:
            best_angle, best = float(a), sc
    if abs(best_angle) < 0.3 or best < base * 1.05:
        return gray
    m = cv2.getRotationMatrix2D((w / 2, h / 2), best_angle, 1.0)
    return cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=255)


def _light(gray: np.ndarray) -> np.ndarray:
    if min(gray.shape) < 1000:  # tiny phone thumbnails: letters too small for Tesseract
        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    return _deskew(gray)


def _strong(gray: np.ndarray) -> np.ndarray:
    if max(gray.shape) < 2000:
        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = _deskew(cv2.medianBlur(gray, 3))
    block = max(31, min(gray.shape) // 30) | 1  # must be odd
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 12
    )
