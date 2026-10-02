import argparse
import logging
import sys
from pathlib import Path

from src.excel import ExcelRegister
from src.models import Status
from src.ocr import TesseractOCR
from src.processing import process_document


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Read correspondence fields from page one of scanned PDFs")
    parser.add_argument("input", type=Path, help="A PDF file or a directory containing PDFs")
    parser.add_argument("--register", type=Path, help="Append SUCCESS results to this Excel register")
    parser.add_argument("--tesseract", help="Path to tesseract.exe (or set TESSERACT_CMD)")
    parser.add_argument("--diagnostics", action="store_true", help="Print raw OCR evidence for development only")
    args = parser.parse_args()
    logging.basicConfig(filename="document-scanner.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    if args.input.is_file() and args.input.suffix.lower() == ".pdf":
        paths = [args.input]
    elif args.input.is_dir():
        paths = sorted(p for p in args.input.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
    else:
        parser.error("Input must be an existing PDF or directory")
    if not paths:
        parser.error("No PDF files found")

    ocr = TesseractOCR(args.tesseract)
    register = ExcelRegister(args.register) if args.register else None
    had_issue = False
    for path in paths:
        result = process_document(path, ocr)
        print(f"File: {result.file_name}\nOrigin: {result.origin or '[not found]'}"
              f"\nTo: {result.to or '[not found]'}"
              f"\nFrom: {result.from_ or '[not found]'}\nSubject: {result.subject or '[not found]'}"
              f"\nReceipt Date: {result.receipt_date.isoformat() if result.receipt_date else '[not found]'}"
              f"\nStatus: {result.status.value}")
        if args.diagnostics:
            print(f"Document Date (diagnostic): {result.document_date.isoformat() if result.document_date else '[not found]'}")
            print("Origin OCR evidence: " + repr(result.origin_evidence))
            print("Date-related OCR lines: " + repr(result.receipt_evidence))
        if result.confidence is not None:
            print(f"OCR confidence: {result.confidence:.0%}")
        for warning in result.warnings:
            print(f"Warning: {warning}")
        if register and result.status == Status.SUCCESS:
            try:
                print("Register: row added" if register.append(path, result) else "Register: duplicate skipped")
            except (OSError, ValueError) as exc:
                logging.exception("Excel write failed for %s", path.name)
                print(f"Register: could not save ({exc})")
                had_issue = True
        elif register:
            print("Register: skipped pending review")
        had_issue |= result.status != Status.SUCCESS
        print()
    return 1 if had_issue else 0


if __name__ == "__main__":
    raise SystemExit(main())
