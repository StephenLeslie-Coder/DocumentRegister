import unittest
from datetime import date

from src.models import OCRLine, OCRResult
from src.receipt import dates_in_text, extract_receipt_date, parse_review_date


def ocr(*texts):
    return OCRResult([OCRLine(text, 90, top=i * 60, height=40, block=1 if i < 2 else 2)
                      for i, text in enumerate(texts)])


class ReceiptTests(unittest.TestCase):
    def test_supported_stamped_formats(self):
        for text in ("1 OCT 2026", "01 OCT 2026", "1 - OCT 2026", "OCT 01 2026",
                     "01/10/2026", "3 0 SEP 2026"):
            with self.subTest(text=text):
                expected = date(2026, 9, 30) if "SEP" in text else date(2026, 10, 1)
                self.assertEqual(extract_receipt_date(ocr("RECEIVED", text)).value, expected)

    def test_printed_date_is_not_receipt_date(self):
        found = extract_receipt_date(ocr("Date: September 24, 2026", "Subject: A request",
                                         "ECEIVED _", "CORPORATE SERVICES DIVISION", "30 SEP 2026"))
        self.assertEqual(found.document_date, date(2026, 9, 24))
        self.assertEqual(found.value, date(2026, 9, 30))

    def test_critical_document_date_and_different_stamp_date(self):
        found = extract_receipt_date(ocr("Date: September 24, 2026", "RECEIVED", "1 OCT 2026"))
        self.assertEqual(found.document_date, date(2026, 9, 24))
        self.assertEqual(found.value, date(2026, 10, 1))

    def test_missing_received_stamp_does_not_use_document_date(self):
        found = extract_receipt_date(ocr("Date: September 24, 2026", "Subject: A request"))
        self.assertIsNone(found.value)
        self.assertIn("Receipt Date", found.warning)

    def test_approved_stamp_does_not_count_as_received(self):
        found = extract_receipt_date(ocr("To: Jane Doe 1 - OCT 2026", "APPROVED",
                                         "MINISTRY OF WATER", "Date: October 01, 2026"))
        self.assertIsNone(found.value)

    def test_word_received_in_body_is_not_a_stamp(self):
        found = extract_receipt_date(ocr("The quotations received are summarized below:",
                                         "Date: October 01, 2026"))
        self.assertIsNone(found.value)
        self.assertNotIn("The quotations received are summarized below:", found.evidence)
        self.assertIsNone(extract_receipt_date(ocr("Received your letter today", "1 OCT 2026")).value)

    def test_noisy_ocr_around_stamp(self):
        found = extract_receipt_date(ocr("ECEIVED _", "CORPORATE SERVICES DIVISION",
                                         "3 0 SEP 2026", "MINISTRY OF WATER"))
        self.assertEqual(found.value, date(2026, 9, 30))

    def test_date_only_stamp_with_organizational_context_requires_review(self):
        lines = OCRResult([OCRLine("Date: September 24, 2026", 95, block=1),
                           OCRLine("30 SEP 2026", 90, block=5),
                           OCRLine("CORPORATE SERVICES DIVISION", 90, block=5)])
        found = extract_receipt_date(lines)
        self.assertEqual(found.value, date(2026, 9, 30))
        self.assertTrue(found.warning)

    def test_multiple_stamp_dates_are_ambiguous(self):
        found = extract_receipt_date(ocr("RECEIVED", "1 OCT 2026", "2 OCT 2026"))
        self.assertIsNone(found.value)
        self.assertIn("ambiguous", found.warning)

    def test_review_entry_normalization_and_invalid_date(self):
        self.assertEqual(parse_review_date("01-Oct-2026"), date(2026, 10, 1))
        self.assertEqual(parse_review_date("2026-10-01"), date(2026, 10, 1))
        self.assertIsNone(parse_review_date("31-Feb-2026"))
        self.assertIsNone(parse_review_date("Oct 2026"))


if __name__ == "__main__":
    unittest.main()
