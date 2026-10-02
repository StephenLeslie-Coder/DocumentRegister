"""In-memory page preview sizing; rendering remains in src.pdf."""

from PIL import Image


def fit_preview(image: Image.Image, bounds: tuple[int, int]) -> Image.Image:
    width, height = bounds
    if width < 1 or height < 1:
        raise ValueError("Preview bounds must be positive")
    scale = min(width / image.width, height / image.height, 1.0)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)
