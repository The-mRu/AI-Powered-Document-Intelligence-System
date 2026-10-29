"""Result types for Task 3. JSON-friendly on purpose: these get stored in the DB
(validation_errors table) and returned by the API unchanged."""
from dataclasses import dataclass
from dataclasses import field as dc_field  # 'field' is also an Issue attribute name
from typing import Any, Literal

Severity = Literal["error", "warning", "info"]


@dataclass
class Issue:
    rule: str
    severity: Severity  # error = wrong/missing; warning = suspicious; info = FYI, no action
    message: str
    field: str | None = None
    details: dict[str, Any] = dc_field(default_factory=dict)


@dataclass
class ValidationReport:
    issues: list[Issue] = dc_field(default_factory=list)

    @property
    def needs_manual_review(self) -> bool:
        return any(i.severity in ("error", "warning") for i in self.issues)

    @property
    def status(self) -> str:
        return "needs_review" if self.needs_manual_review else "passed"

    @property
    def reasons(self) -> list[str]:
        return [i.message for i in self.issues if i.severity in ("error", "warning")]

    def to_dict(self) -> dict:
        count = lambda s: sum(i.severity == s for i in self.issues)  # noqa: E731
        return {
            "status": self.status,
            "needs_manual_review": self.needs_manual_review,
            "reasons": self.reasons,
            "counts": {"error": count("error"), "warning": count("warning"), "info": count("info")},
            "issues": [{"rule": i.rule, "severity": i.severity, "field": i.field,
                        "message": i.message, "details": i.details} for i in self.issues],
        }
