import logging
from pathlib import Path

from PIL import ImageEnhance, ImageOps

from .extraction import CorrespondenceFieldExtractor
from .models import DocumentResult, Status
from .ocr import OCRService
from .origin import extract_origin
from .pdf import preprocess, render_first_page
from .receipt import extract_receipt_date


log = logging.getLogger(__name__)


def process_document(path: Path, ocr_service: OCRService) -> DocumentResult:
    log.info("Processing %s", path.name)
    try:
        image = render_first_page(path)
        log.info("Rendered first page of %s", path.name)
        ocr = ocr_service.extract_text(preprocess(image))
        log.info("OCR completed for %s", path.name)
        result = CorrespondenceFieldExtractor().extract(ocr, path.name)
        origin = extract_origin(ocr)
        result.origin = origin.value
        result.origin_evidence = origin.evidence
        if origin.warning:
            result.warnings.append(origin.warning)

        receipt = extract_receipt_date(ocr)
        printed_date = receipt.document_date
        if receipt.value is None:
            # A separate, high-contrast pass helps read faint stamps without changing
            # the OCR used for To, From, Subject, or Origin.
            try:
                stamp_image = ImageOps.autocontrast(ImageEnhance.Contrast(preprocess(image)).enhance(1.8))
                alternate = extract_receipt_date(ocr_service.extract_text(stamp_image))
                if alternate.value is not None:
                    receipt = alternate
            except Exception:
                log.exception("Secondary stamp OCR failed for %s", path.name)
        result.receipt_date = receipt.value
        result.document_date = printed_date or receipt.document_date
        result.receipt_evidence = receipt.evidence
        if receipt.warning:
            result.warnings.append(receipt.warning)
        result.status = (Status.SUCCESS if result.status == Status.SUCCESS and result.origin
                         and result.receipt_date and not result.warnings else Status.NEEDS_REVIEW)
        log.info("Fields extracted for %s", path.name)
        if result.status == Status.NEEDS_REVIEW:
            log.info("Document requires review: %s", path.name)
        return result
    except Exception as exc:
        log.exception("Processing failed for %s", path.name)
        return DocumentResult(path.name, status=Status.FAILED, warnings=[f"Processing failed: {type(exc).__name__}: {exc}"])
