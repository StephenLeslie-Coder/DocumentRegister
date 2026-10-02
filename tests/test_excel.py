import tempfile
import unittest
from pathlib import Path

from src.excel import ExcelRegister
from src.models import DocumentResult, Status


class ExcelTests(unittest.TestCase):
    def test_appends_once_and_rejects_review(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / "memo.pdf"
            pdf.write_bytes(b"first")
            register = ExcelRegister(Path(directory) / "register.xlsx")
            result = DocumentResult("memo.pdf", "Kamaya Thompson", "Hansel Ramdhan",
                                    "Procurement request", Status.SUCCESS)
            self.assertTrue(register.append(pdf, result))
            self.assertFalse(register.append(pdf, result))
            pdf.write_bytes(b"second")
            self.assertTrue(register.append(pdf, result))
            with self.assertRaises(ValueError):
                register.append(pdf, DocumentResult("memo.pdf"))


if __name__ == "__main__":
    unittest.main()
