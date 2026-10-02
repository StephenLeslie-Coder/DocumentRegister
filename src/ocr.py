import os
import sys
from abc import ABC, abstractmethod
from collections import OrderedDict
from pathlib import Path

import pytesseract
from PIL import Image

from .models import OCRLine, OCRResult


class OCRService(ABC):
    @abstractmethod
    def extract_text(self, image: Image.Image) -> OCRResult:
        raise NotImplementedError


class TesseractOCR(OCRService):
    def __init__(self, executable: str | None = None):
        selected = executable or os.getenv("TESSERACT_CMD")
        self.tessdata_dir: Path | None = None
        if not selected and getattr(sys, "frozen", False):
            bundled = Path(sys._MEIPASS) / "tesseract"
            if (bundled / "tesseract.exe").is_file():
                selected = str(bundled / "tesseract.exe")
                self.tessdata_dir = bundled / "tessdata"
        if not selected and os.name == "nt":
            for root in (os.getenv("ProgramFiles"), os.getenv("ProgramFiles(x86)")):
                if root:
                    candidate = Path(root) / "Tesseract-OCR" / "tesseract.exe"
                    if candidate.is_file():
                        selected = str(candidate)
                        break
        if selected:
            pytesseract.pytesseract.tesseract_cmd = str(Path(selected))
        if self.tessdata_dir:
            os.environ["TESSDATA_PREFIX"] = str(self.tessdata_dir)

    def extract_text(self, image: Image.Image) -> OCRResult:
        data = pytesseract.image_to_data(
            image, lang="eng", config="--psm 3", output_type=pytesseract.Output.DICT
        )
        groups = OrderedDict()
        for i, word in enumerate(data["text"]):
            word = word.strip()
            if not word:
                continue
            key = (data["page_num"][i], data["block_num"][i],
                   data["par_num"][i], data["line_num"][i])
            group = groups.setdefault(key, {"words": [], "scores": [], "top": [], "bottom": []})
            group["words"].append(word)
            score = float(data["conf"][i])
            if score >= 0:
                group["scores"].append(score)
            group["top"].append(int(data["top"][i]))
            group["bottom"].append(int(data["top"][i]) + int(data["height"][i]))
        lines = []
        for key, group in groups.items():
            top = min(group["top"])
            lines.append(OCRLine(
                text=" ".join(group["words"]),
                confidence=sum(group["scores"]) / len(group["scores"]) if group["scores"] else None,
                top=top, height=max(group["bottom"]) - top, block=key[1],
            ))
        lines.sort(key=lambda line: line.top if line.top is not None else 0)
        return OCRResult(lines)
