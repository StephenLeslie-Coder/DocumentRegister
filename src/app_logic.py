"""Desktop workflow rules, independent of Tkinter."""

import json
import logging
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .excel import ExcelRegister
from .config import APP_DIR_NAME
from .models import DocumentResult, Status
from .ocr import OCRService
from .processing import process_document


log = logging.getLogger(__name__)


class DisplayStatus(str, Enum):
    READY = "Ready"
    PROCESSING = "Processing"
    PROCESSED = "Processed"
    NEEDS_REVIEW = "Needs Review"
    ALREADY_PROCESSED = "Already Processed"
    FAILED = "Failed"


@dataclass
class ProcessOutcome:
    status: DisplayStatus
    result: DocumentResult | None = None
    message: str = ""


def discover_pdfs(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"),
                  key=lambda p: p.name.casefold())


@dataclass
class AppSettings:
    document_folder: str = ""
    register_path: str = ""


class SettingsStore:
    def __init__(self, path: Path | None = None):
        if path is None:
            base = Path(os.getenv("APPDATA") or Path.home() / ".config")
            path = base / APP_DIR_NAME / "settings.json"
        self.path = path

    def load(self) -> AppSettings:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return AppSettings(
                document_folder=data.get("document_folder", "") if isinstance(data.get("document_folder"), str) else "",
                register_path=data.get("register_path", "") if isinstance(data.get("register_path"), str) else "",
            )
        except (OSError, ValueError, TypeError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps({"document_folder": settings.document_folder,
                                    "register_path": settings.register_path}, indent=2), encoding="utf-8")
        temp.replace(self.path)


def process_one(pdf_path: Path, register: ExcelRegister, ocr: OCRService) -> ProcessOutcome:
    if not register.path.is_file():
        return ProcessOutcome(DisplayStatus.FAILED, message="The selected Excel register was not found. Choose or create a register.")
    try:
        if register.contains(pdf_path):
            return ProcessOutcome(DisplayStatus.ALREADY_PROCESSED)
    except Exception:
        log.exception("Could not read register while checking %s", pdf_path.name)
        return ProcessOutcome(DisplayStatus.FAILED, message="Unable to read the Excel register. Check that it is available and has the expected columns.")
    result = process_document(pdf_path, ocr)
    if result.status == Status.FAILED:
        return ProcessOutcome(DisplayStatus.FAILED, result,
                              "Unable to process this PDF. Check that it opens normally, then try again.")
    if result.status == Status.NEEDS_REVIEW:
        return ProcessOutcome(DisplayStatus.NEEDS_REVIEW, result)
    try:
        created = register.append(pdf_path, result)
        return ProcessOutcome(DisplayStatus.PROCESSED if created else DisplayStatus.ALREADY_PROCESSED, result)
    except Exception:
        log.exception("Could not write register for %s", pdf_path.name)
        return ProcessOutcome(DisplayStatus.FAILED, result,
                              "Unable to write to the Excel register. Close it in Excel and try again.")


def approve_and_save(pdf_path: Path, register: ExcelRegister, to: str, from_: str, subject: str) -> bool:
    fields = {"To": re.sub(r"\s+", " ", to).strip(),
              "From": re.sub(r"\s+", " ", from_).strip(),
              "Subject": re.sub(r"\s+", " ", subject).strip()}
    missing = [name for name, value in fields.items() if not value]
    if missing:
        raise ValueError("Please fill in: " + ", ".join(missing))
    result = DocumentResult(pdf_path.name, fields["To"], fields["From"], fields["Subject"], Status.SUCCESS)
    return register.append(pdf_path, result)
