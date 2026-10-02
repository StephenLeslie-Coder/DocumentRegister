import unittest

from src.models import OCRLine, OCRResult
from src.origin import extract_origin


def ocr(*texts):
    return OCRResult([OCRLine(text, 90, top=i * 70, height=45) for i, text in enumerate(texts)])


class OriginTests(unittest.TestCase):
    def test_ministry_only(self):
        found = extract_origin(ocr("MINISTRY OF FINANCE AND PUBLIC SERVICE", "MEMORANDUM", "To: Jane Doe"))
        self.assertEqual(found.value, "Ministry of Finance and Public Service")

    def test_branch_takes_precedence_over_ministry(self):
        found = extract_origin(ocr("MINISTRY OF FINANCE AND PUBLIC SERVICE", "PUBLIC PROCUREMENT BRANCH",
                                   "To: Jane Doe"))
        self.assertEqual(found.value, "Public Procurement Branch")

    def test_office_takes_precedence_over_ministry(self):
        found = extract_origin(ocr("Ministry of Finance and Public Service",
                                   "Office of the Permanent Secretary", "To: Jane Doe"))
        self.assertEqual(found.value, "Office of the Permanent Secretary")

    def test_division_in_letterhead(self):
        found = extract_origin(ocr("Human Resource Management Division", "From: John Doe"))
        self.assertEqual(found.value, "Human Resource Management Division")

    def test_body_sender_refines_letterhead_with_desk_context(self):
        found = extract_origin(ocr("Ministry of Water, Environment and Climate Change",
                                   "From the desk of the Director of Information and Communication Technology",
                                   "To: Jane Doe", "From: John Doe", "Subject: Procurement",
                                   "The Information and Communication Technology (ICT) Branch respectfully requests approval"))
        self.assertEqual(found.value, "Information and Communication Technology (ICT) Branch")

    def test_no_identifiable_origin(self):
        found = extract_origin(ocr("INTERNAL MEMORANDUM", "To: Jane Doe", "From: John Doe"))
        self.assertEqual(found.value, "")
        self.assertIn("Origin", found.warning)

    def test_ocr_noise_and_stamp_organization_excluded(self):
        found = extract_origin(ocr("MINlSTRY OF WATER", "Public Procurement Branch", "To: Jane Doe",
                                   "RECEIVED", "CORPORATE SERVICES DIVISION"))
        self.assertEqual(found.value, "Public Procurement Branch")

    def test_low_confidence_header_not_accepted(self):
        found = extract_origin(OCRResult([OCRLine("MINISTRY OF FINANCE", 20), OCRLine("To: Jane Doe", 95)]))
        self.assertFalse(found.value)


if __name__ == "__main__":
    unittest.main()
