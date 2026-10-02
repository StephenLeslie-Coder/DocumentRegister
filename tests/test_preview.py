import unittest

from PIL import Image

from src.preview import fit_preview


class PreviewTests(unittest.TestCase):
    def test_preserves_aspect_ratio_and_fits_bounds(self):
        page = Image.new("RGB", (600, 900), "white")
        preview = fit_preview(page, (300, 300))
        self.assertEqual(preview.size, (200, 300))
        self.assertEqual(page.size, (600, 900))

    def test_does_not_enlarge_small_source(self):
        page = Image.new("RGB", (100, 150), "white")
        self.assertEqual(fit_preview(page, (500, 500)).size, (100, 150))


if __name__ == "__main__":
    unittest.main()
