import logging
from pathlib import Path

from .extraction import CorrespondenceFieldExtractor
from .models import DocumentResult, Status
from .ocr import OCRService
from .pdf import preprocess, render_first_page


log = logging.getLogger(__name__)


def process_document(path: Path, ocr_service: OCRService) -> DocumentResult:
    log.info("Processing %s", path.name)
    try:
        image = render_first_page(path)
        log.info("Rendered first page of %s", path.name)
        ocr = ocr_service.extract_text(preprocess(image))
        log.info("OCR completed for %s", path.name)
        result = CorrespondenceFieldExtractor().extract(ocr, path.name)
        log.info("Fields extracted for %s", path.name)
        if result.status == Status.NEEDS_REVIEW:
            log.info("Document requires review: %s", path.name)
        return result
    except Exception as exc:
        log.exception("Processing failed for %s", path.name)
        return DocumentResult(path.name, status=Status.FAILED, warnings=[f"Processing failed: {type(exc).__name__}: {exc}"])
