"""Detect file type from magic bytes, never from the extension.
Users rename files and attackers lie about extensions; content is the truth."""
import zipfile
from pathlib import Path

import olefile

from .errors import (CorruptedFileError, EncryptedFileError, FileTooLargeError,
                     UnsupportedFileError)

MAX_UNCOMPRESSED_XLSX = 300 * 1024 * 1024  # zip-bomb guard

_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_TEXT_EXT = {".csv", ".tsv"}


def detect_kind(path: Path) -> str:
    with path.open("rb") as f:
        head = f.read(4096)
    if not head:
        raise CorruptedFileError("File is empty")

    if b"%PDF-" in head[:1024]:  # spec allows junk before the header
        return "pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if head.startswith(b"PK\x03\x04"):
        return _check_xlsx(path)
    if head.startswith(_OLE):
        return _check_ole(path)
    if head.startswith((b"\xff\xfe", b"\xfe\xff", b"\xef\xbb\xbf")):
        return "csv" if path.suffix.lower() in _TEXT_EXT else _unsupported(path)
    if path.suffix.lower() in _TEXT_EXT:
        if b"\x00" in head:
            raise UnsupportedFileError("Binary data in a file named like CSV")
        return "csv"
    return _unsupported(path)


def _check_xlsx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            total = sum(i.file_size for i in z.infolist())
    except zipfile.BadZipFile as e:
        raise CorruptedFileError(f"Corrupted ZIP/XLSX container: {e}") from e
    if "xl/workbook.xml" not in names:
        if "word/document.xml" in names:
            raise UnsupportedFileError("Word documents (.docx) are not supported; export to PDF first")
        if "ppt/presentation.xml" in names:
            raise UnsupportedFileError("PowerPoint files are not supported; export to PDF first")
        raise UnsupportedFileError("ZIP archive that is not an Excel workbook")
    if total > MAX_UNCOMPRESSED_XLSX:
        raise FileTooLargeError("Workbook expands to an unsafe size")
    return "xlsx"


def _check_ole(path: Path) -> str:
    """Old Office formats (.xls, .doc, .ppt) and password-protected .xlsx all share
    one container signature. Look at the streams inside to tell them apart."""
    try:
        with olefile.OleFileIO(path) as ole:
            if ole.exists("EncryptedPackage"):
                raise EncryptedFileError("Workbook is password protected")
            if ole.exists("Workbook") or ole.exists("Book"):
                return "xls"
            if ole.exists("WordDocument"):
                raise UnsupportedFileError("Word documents (.doc) are not supported; export to PDF first")
            if ole.exists("PowerPoint Document"):
                raise UnsupportedFileError("PowerPoint files are not supported; export to PDF first")
    except OSError as e:  # olefile raises OSError on a damaged container
        raise CorruptedFileError(f"Corrupted Office file: {e}") from e
    raise UnsupportedFileError("Unrecognized legacy Office document")


def _unsupported(path: Path):
    raise UnsupportedFileError(f"Unsupported file type: {path.suffix or 'unknown'}")
