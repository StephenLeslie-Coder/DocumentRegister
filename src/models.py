from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    SUCCESS = "SUCCESS"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


@dataclass(frozen=True)
class OCRLine:
    text: str
    confidence: float | None = None  # 0..100
    top: int | None = None
    height: int | None = None
    block: int | None = None


@dataclass(frozen=True)
class OCRResult:
    lines: list[OCRLine]

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


@dataclass
class DocumentResult:
    file_name: str
    to: str = ""
    from_: str = ""
    subject: str = ""
    status: Status = Status.NEEDS_REVIEW
    warnings: list[str] = field(default_factory=list)
    confidence: float | None = None  # 0..1; conservative field/OCR estimate

