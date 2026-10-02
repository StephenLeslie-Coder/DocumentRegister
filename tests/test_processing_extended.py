import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from src.models import OCRLine, OCRResult, Status
from src.processing import process_document


class FakeOCR:
    def __init__(self, first, second):
        self.results = [first, second]
        self.calls = 0

    def extract_text(self, _image):
        result = self.results[self.calls]
        self.calls += 1
        return result


class ExtendedProcessingTests(unittest.TestCase):
    def test_secondary_stamp_ocr_does_not_replace_correspondence_fields(self):
        first = OCRResult([OCRLine(text, 95, top=i * 70, height=40)
                           for i, text in enumerate(("PUBLIC PROCUREMENT BRANCH", "To: Jane Doe",
                                                    "From: John Brown", "Date: September 24, 2026",
                                                    "Subject: Printer request", "Dear colleague"))])
        second = OCRResult([OCRLine("RECEIVED", 85, top=100, height=40),
                            OCRLine("1 OCT 2026", 90, top=160, height=40)])
        service = FakeOCR(first, second)
        with patch("src.processing.render_first_page", return_value=Image.new("RGB", (100, 100), "white")):
            result = process_document(Path("memo.pdf"), service)
        self.assertEqual(service.calls, 2)
        self.assertEqual((result.origin, result.to, result.from_, result.subject),
                         ("Public Procurement Branch", "Jane Doe", "John Brown", "Printer request"))
        self.assertEqual(result.document_date, date(2026, 9, 24))
        self.assertEqual(result.receipt_date, date(2026, 10, 1))
        self.assertEqual(result.status, Status.SUCCESS)


if __name__ == "__main__":
    unittest.main()
