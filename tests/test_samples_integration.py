"""Real-PDF integration checks; skipped when local Tesseract is unavailable."""

import unittest
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


if __name__ == "__main__":
    unittest.main()
