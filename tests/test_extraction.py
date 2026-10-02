import unittest
from pathlib import Path

from src.extraction import CorrespondenceFieldExtractor
from src.models import OCRLine, OCRResult, Status


FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> OCRResult:
    return OCRResult([OCRLine(text=line) for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines()])


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.extractor = CorrespondenceFieldExtractor()

    def test_standard_layout_ignores_titles(self):
        result = self.extractor.extract(fixture("standard.txt"), "memo.pdf")
        self.assertEqual((result.to, result.from_, result.subject),
                         ("Ms. Kamaya Thompson", "Mr. Hansel Ramdhan",
                          "Request for Procurement of Printer for Mr. Omar Alcock"))
        self.assertEqual(result.status, Status.SUCCESS)

    def test_spacing_wrapped_subject_ocr_typo_and_changed_order(self):
        result = self.extractor.extract(fixture("spacing.txt"), "memo.pdf")
        self.assertEqual(result.status, Status.SUCCESS)
        self.assertEqual(result.to, "Kamaya Thompson")
        self.assertEqual(result.from_, "Hansel Ramdhan")
        self.assertEqual(result.subject, "Request for Procurement of Printer for Mr. Omar Alcock")

    def test_missing_field_requires_review(self):
        result = self.extractor.extract(fixture("missing.txt"), "memo.pdf")
        self.assertEqual(result.status, Status.NEEDS_REVIEW)
        self.assertEqual(result.subject, "")
        self.assertTrue(any("Subject" in warning for warning in result.warnings))

    def test_unrelated_body_text_does_not_count_as_label(self):
        result = self.extractor.extract(OCRResult([OCRLine("To whom it may concern"),
            OCRLine("From our office we write"), OCRLine("The subject of this letter")]), "memo.pdf")
        self.assertEqual(result.status, Status.NEEDS_REVIEW)
        self.assertEqual((result.to, result.from_, result.subject), ("", "", ""))

    def test_low_confidence_requires_review(self):
        result = self.extractor.extract(OCRResult([
            OCRLine("To: Kamaya Thompson", 90), OCRLine("From: Hansel Ramdhan", 45),
            OCRLine("Subject: Procurement request", 90)]), "memo.pdf")
        self.assertEqual(result.status, Status.NEEDS_REVIEW)

    def test_duplicate_labels_require_review(self):
        result = self.extractor.extract(OCRResult([
            OCRLine("To: Kamaya Thompson"), OCRLine("To: Another Person"),
            OCRLine("From: Hansel Ramdhan"), OCRLine("Subject: Procurement request")]), "memo.pdf")
        self.assertEqual(result.status, Status.NEEDS_REVIEW)
        self.assertEqual(result.to, "")

    def test_subject_stops_before_separate_body_paragraph(self):
        result = self.extractor.extract(OCRResult([
            OCRLine("To: Kamaya Thompson", top=100, height=50),
            OCRLine("From: Hansel Ramdhan", top=200, height=50),
            OCRLine("Subject: Printer procurement", top=300, height=50),
            OCRLine("for the branch", top=360, height=50),
            OCRLine("The branch respectfully requests approval", top=490, height=50),
        ]), "memo.pdf")
        self.assertEqual(result.subject, "Printer procurement for the branch")
        self.assertEqual(result.status, Status.SUCCESS)

    def test_overlapping_date_and_signature_noise_require_review(self):
        result = self.extractor.extract(OCRResult([
            OCRLine('To: Ms. Kamaya Thompson 1 - OCT 2026"'),
            OCRLine("From: Rushelle Abrahams-Stewart (Mrs.) Ao Ss?"),
            OCRLine("Subject: Flexible Work Arrangement")
        ]), "memo.pdf")
        self.assertEqual(result.to, "Ms. Kamaya Thompson")
        self.assertEqual(result.from_, "Rushelle Abrahams-Stewart (Mrs.)")
        self.assertEqual(result.status, Status.NEEDS_REVIEW)

    def test_job_title_without_name_is_not_accepted(self):
        result = self.extractor.extract(OCRResult([
            OCRLine("To:"), OCRLine("Permanent Secretary"),
            OCRLine("From: Hansel Ramdhan"), OCRLine("Subject: Printer procurement")
        ]), "memo.pdf")
        self.assertEqual(result.to, "")
        self.assertEqual(result.status, Status.NEEDS_REVIEW)


if __name__ == "__main__":
    unittest.main()
