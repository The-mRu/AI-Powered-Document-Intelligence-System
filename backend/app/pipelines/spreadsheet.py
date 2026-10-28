"""Spreadsheet pipeline: XLSX / XLS / CSV -> structured rows + searchable text.

Key decisions:
* Everything is read as raw objects (dtype=object / csv strings). Letting pandas
  guess types turns invoice number "00123" into 123 and corrupts data silently.
* Header row is detected, not assumed: real files have title rows above it.
* Each sheet becomes one PageResult (text, for search/LLM) AND one SheetData
  (structured rows, for deterministic parsing and cross-verification).
"""
import codecs
import csv
import io
import math
import time
from collections import Counter
from datetime import date, datetime, time as dtime
from pathlib import Path

import numpy as np
import pandas as pd

from .errors import CorruptedFileError, EncryptedFileError
from .models import PageResult, ProcessedDocument, SheetData

MAX_ROWS = 200_000
MAX_TEXT_ROWS = 2_000


def process_spreadsheet(path: Path, kind: str) -> ProcessedDocument:
    doc = ProcessedDocument(kind=kind, pages=[])
    if kind == "csv":
        raw_sheets, doc.warnings = _read_csv(path)
    else:
        raw_sheets = _read_workbook(path, kind)

    for i, (name, raw) in enumerate(raw_sheets, start=1):
        start = time.perf_counter()
        if isinstance(raw, Exception):
            doc.pages.append(PageResult(i, "", "failed", label=name,
                                        error=f"{type(raw).__name__}: {raw}"))
            continue
        sheet = _build_sheet(name, raw)
        if sheet is None:
            doc.warnings.append(f"Sheet '{name}' is empty")
            continue
        if sheet.truncated:
            doc.warnings.append(f"Sheet '{name}' truncated to {MAX_ROWS} rows")
        doc.sheets.append(sheet)
        doc.pages.append(PageResult(i, _to_text(sheet), "spreadsheet", label=name,
                                    duration_ms=int((time.perf_counter() - start) * 1000)))
    return doc


def _read_workbook(path: Path, kind: str) -> list[tuple[str, "pd.DataFrame | Exception"]]:
    try:
        xls = pd.ExcelFile(path, engine="openpyxl" if kind == "xlsx" else "xlrd")
    except Exception as e:
        if "encrypt" in str(e).lower() or "password" in str(e).lower():
            raise EncryptedFileError("Workbook is password protected") from e
        raise CorruptedFileError(f"Cannot open workbook: {e}") from e
    out = []
    for name in xls.sheet_names:
        try:
            out.append((name, xls.parse(name, header=None, dtype=object)))
        except Exception as e:  # one broken sheet must not lose the others
            out.append((name, e))
    return out


def _decode(raw: bytes) -> tuple[str, str]:
    if raw.startswith(codecs.BOM_UTF8):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16"), "utf-16"
    for enc in ("utf-8", "cp1252"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1"), "latin-1"  # never fails


def _guess_delimiter(text: str) -> str:
    lines = [ln for ln in text.splitlines()[:40] if ln.strip()]
    best, best_score = ",", 0.0
    for cand in (",", ";", "\t", "|"):
        counts = [len(r) for r in csv.reader(lines, delimiter=cand) if r]
        if not counts:
            continue
        mode, freq = Counter(counts).most_common(1)[0]
        score = (mode - 1) * (freq / len(counts))  # many columns, consistently
        if score > best_score:
            best, best_score = cand, score
    return best


def _read_csv(path: Path):
    raw = path.read_bytes()
    if not raw.strip():
        raise CorruptedFileError("CSV file is empty")
    text, enc = _decode(raw)
    warnings = [] if enc in ("utf-8", "utf-8-sig") else [f"CSV decoded as {enc}, not UTF-8"]
    try:
        rows = list(csv.reader(io.StringIO(text), delimiter=_guess_delimiter(text)))
    except csv.Error as e:
        raise CorruptedFileError(f"Malformed CSV: {e}") from e
    width = max((len(r) for r in rows), default=0)
    if width == 0:
        raise CorruptedFileError("CSV has no data")
    padded = [[(c if c != "" else None) for c in r] + [None] * (width - len(r)) for r in rows]
    return [("csv", pd.DataFrame(padded, dtype=object))], warnings


def _clean(v):
    if isinstance(v, np.generic):
        v = v.item()
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, (datetime, date, dtime, pd.Timestamp)):
        return None if v is pd.NaT else v.isoformat()
    if isinstance(v, str):
        return v.strip() or None
    return v


def _build_sheet(name: str, raw: pd.DataFrame) -> SheetData | None:
    raw = raw.dropna(how="all").dropna(axis=1, how="all")
    if raw.empty:
        return None
    excel_rows = [int(i) + 1 for i in raw.index]  # original 1-based row numbers
    raw = raw.reset_index(drop=True)

    counts = raw.notna().sum(axis=1)
    threshold = 0.6 * counts.max()
    pos = next(i for i, c in enumerate(counts) if c >= threshold)  # skips title rows

    header_cells = [_clean(v) for v in raw.iloc[pos]]
    non_null = [c for c in header_cells if c is not None]
    looks_like_header = bool(non_null) and sum(isinstance(c, str) for c in non_null) / len(non_null) >= 0.6

    if looks_like_header:
        names, seen = [], Counter()
        for j, c in enumerate(header_cells):
            n = str(c) if c is not None else f"col_{j + 1}"
            seen[n] += 1
            names.append(n if seen[n] == 1 else f"{n}_{seen[n]}")
        body, header_row = raw.iloc[pos + 1:], excel_rows[pos]
    else:
        names, body, header_row = [f"col_{j + 1}" for j in range(raw.shape[1])], raw.iloc[pos:], None

    total = len(body)
    body = body.iloc[:MAX_ROWS]
    rows = [{n: _clean(v) for n, v in zip(names, r)} for r in body.itertuples(index=False, name=None)]
    return SheetData(name, header_row, names, rows, total, truncated=total > MAX_ROWS)


def _to_text(sheet: SheetData) -> str:
    lines = [f"[Sheet: {sheet.name}]", "\t".join(sheet.columns)]
    for r in sheet.rows[:MAX_TEXT_ROWS]:
        lines.append("\t".join("" if v is None else str(v) for v in r.values()))
    if len(sheet.rows) > MAX_TEXT_ROWS:
        lines.append(f"... ({len(sheet.rows) - MAX_TEXT_ROWS} more rows in structured data)")
    return "\n".join(lines)
