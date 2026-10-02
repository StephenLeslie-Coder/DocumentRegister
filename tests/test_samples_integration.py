"""Real-PDF integration checks; skipped when local Tesseract is unavailable."""

import unittest
from datetime import date
from pathlib import Path

import pytesseract

from src.models import Status
from src.ocr import TesseractOCR
from src.processing import process_document


SAMPLES = Path(__file__).resolve().parent.parent / "samples"
SAMPLE_NAMES = (
    "doc00247920261002115945.pdf",
    "doc00248020261002120109.pdf",
)


class SampleIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr = TesseractOCR()
        try:
            pytesseract.get_tesseract_version()
        except pytesseract.TesseractNotFoundError:
            raise unittest.SkipTest("Local Tesseract is not installed")

    def test_real_scans_have_reviewable_fields(self):
        for name in SAMPLE_NAMES:
            with self.subTest(name=name):
                path = SAMPLES / name
                self.assertTrue(path.is_file())
                result = process_document(path, self.ocr)
                self.assertEqual(result.status, Status.NEEDS_REVIEW)
                self.assertTrue(result.to)
                self.assertTrue(result.from_)
                self.assertTrue(result.subject)
                self.assertTrue(result.warnings)
                self.assertTrue(result.origin)
                self.assertTrue(result.origin_evidence)
                self.assertEqual(result.document_date, date(2026, 10, 1) if name == SAMPLE_NAMES[0]
                                 else date(2026, 9, 24))
                self.assertEqual(result.receipt_date, None if name == SAMPLE_NAMES[0]
                                 else date(2026, 9, 30))


if __name__ == "__main__":
    unittest.main()
