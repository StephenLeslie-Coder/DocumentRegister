"""Append reviewed success results; identity lives in a hidden seventh column."""

import hashlib
import logging
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from .models import DocumentResult, Status


HEADERS = ["File Name", "To", "From", "Subject", "Processed Date", "Status", "Document Key"]
log = logging.getLogger(__name__)


def document_key(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"{path.name.casefold()}:{digest.hexdigest()}"


def _safe(value: str) -> str:
    # Prevent spreadsheet formula interpretation of text from an untrusted PDF.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


class ExcelRegister:
    def __init__(self, path: Path):
        self.path = path

    @staticmethod
    def _new_book():
        book = Workbook()
        sheet = book.active
        sheet.title = "Register"
        sheet.append(HEADERS)
        sheet.column_dimensions["G"].hidden = True
        for column, width in {"A": 30, "B": 32, "C": 32, "D": 64, "E": 22, "F": 18}.items():
            sheet.column_dimensions[column].width = width
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = "A1:F1"
        return book

    @staticmethod
    def _check_headers(sheet) -> None:
        if [sheet.cell(1, c).value for c in range(1, 8)] != HEADERS:
            raise ValueError("Register has an unexpected header; refusing to modify it")

    def create(self) -> None:
        if self.path.exists():
            raise FileExistsError(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        book = self._new_book()
        try:
            book.save(self.path)
        finally:
            book.close()

    def validate(self) -> None:
        book = load_workbook(self.path, read_only=True)
        try:
            self._check_headers(book.active)
        finally:
            book.close()

    def contains(self, pdf_path: Path) -> bool:
        if not self.path.exists():
            return False
        key = document_key(pdf_path)
        book = load_workbook(self.path, read_only=True)
        try:
            sheet = book.active
            self._check_headers(sheet)
            return any(row[0] == key for row in sheet.iter_rows(min_row=2, min_col=7, max_col=7, values_only=True))
        finally:
            book.close()

    def append(self, pdf_path: Path, result: DocumentResult) -> bool:
        if result.status != Status.SUCCESS:
            raise ValueError("Only reviewed SUCCESS results can be added to the register")
        if not all((result.to, result.from_, result.subject)):
            raise ValueError("All three fields are required")
        key = document_key(pdf_path)
        if self.path.exists():
            book = load_workbook(self.path)
        else:
            book = self._new_book()
        try:
            sheet = book.active
            self._check_headers(sheet)
            if any(sheet.cell(row, 7).value == key for row in range(2, sheet.max_row + 1)):
                return False
            sheet.append([_safe(result.file_name), _safe(result.to), _safe(result.from_),
                          _safe(result.subject), datetime.now(), result.status.value, key])
            self.path.parent.mkdir(parents=True, exist_ok=True)
            book.save(self.path)
            log.info("Excel row created for %s", pdf_path.name)
            return True
        finally:
            book.close()
