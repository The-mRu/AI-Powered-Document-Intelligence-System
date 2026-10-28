"""Plain dataclasses: the contract between the pipelines and the rest of the app
(Celery task -> DB rows). No DB or framework imports here on purpose."""
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Method = Literal["text_layer", "ocr", "spreadsheet", "failed"]


@dataclass
class PageResult:
    page_no: int
    text: str = ""
    method: Method = "text_layer"
    confidence: float | None = None  # mean OCR word confidence 0-100; None if not OCR
    label: str | None = None  # sheet name for spreadsheets
    error: str | None = None
    duration_ms: int = 0


@dataclass
class SheetData:
    name: str
    header_row: int | None  # 1-based row number in the original sheet; None = no header found
    columns: list[str]
    rows: list[dict[str, Any]]
    total_rows: int
    truncated: bool = False


@dataclass
class ProcessedDocument:
    kind: str
    pages: list[PageResult]
    sheets: list[SheetData] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def failed_pages(self) -> list[PageResult]:
        return [p for p in self.pages if p.error]

    @property
    def status(self) -> str:
        if not self.pages or len(self.failed_pages) == len(self.pages):
            return "failed"
        return "partial" if self.failed_pages else "completed"

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status
        return d
