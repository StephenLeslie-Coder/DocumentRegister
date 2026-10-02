from pathlib import Path

import pymupdf
from PIL import Image


def render_first_page(path: Path, dpi: int = 300) -> Image.Image:
    with pymupdf.open(path) as document:
        if not document.page_count:
            raise ValueError("PDF has no pages")
        pixmap = document[0].get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def preprocess(image: Image.Image) -> Image.Image:
    # Grayscale preserves faint print better than an irreversible binary threshold.
    return image.convert("L")
