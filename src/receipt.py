"""Receipt-stamp date detection, separate from printed document dates."""

import re
from dataclasses import dataclass, field
from datetime import date

from .models import OCRResult


MONTHS = {name: index for index, name in enumerate(
    ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1)}
MONTH_TEXT = "JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|JUN(?:E)?|JUL(?:Y)?|AUG(?:UST)?|SEP(?:TEMBER)?|OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?"
DAY_MONTH = re.compile(rf"(?<!\d)(\d{{1,2}})\s*[-/, .]*\s*({MONTH_TEXT})\s*[-/, .]*\s*(\d{{4}})\b", re.I)
MONTH_DAY = re.compile(rf"\b({MONTH_TEXT})\s*[-/, .]*\s*(\d{{1,2}})\s*[-/, .]*\s*(\d{{4}})\b", re.I)
NUMERIC = re.compile(r"(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?!\d)")
ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
RECEIVED = re.compile(r"^\s*(?:date\s+)?(?:received|eceived|receiv[eé]d|rec[eé]ived)\b", re.I)
OTHER_STAMP = re.compile(r"\b(?:approved|not approved|rejected)\b", re.I)
DOC_DATE = re.compile(r"^\s*date\s*[:：-]\s*(.*)$", re.I)
ORG = re.compile(r"\b(ministry|department|division|branch|office|agency|authority|secretariat)\b", re.I)


@dataclass
class ReceiptFinding:
    value: date | None = None
    document_date: date | None = None
    evidence: list[str] = field(default_factory=list)
    warning: str = ""


def _date(year: str, month: int, day: str) -> date | None:
    try:
        value = date(int(year), int(month), int(day))
        return value if 1900 <= value.year <= 2100 else None
    except ValueError:
        return None


def dates_in_text(text: str) -> list[date]:
    # Join a stamped day whose digits OCR separated, e.g. "3 0 SEP 2026".
    text = re.sub(r"(?<!\d)(\d)\s+(\d)(?=\s*[-/, .]*\s*[A-Za-z]{3})", r"\1\2", text)
    text = re.sub(r"\b0CT\b", "OCT", text, flags=re.I)
    text = re.sub(r"\b5EP\b", "SEP", text, flags=re.I)
    found: list[date] = []
    for match in DAY_MONTH.finditer(text):
        value = _date(match.group(3), MONTHS[match.group(2)[:3].upper()], match.group(1))
        if value:
            found.append(value)
    for match in MONTH_DAY.finditer(text):
        value = _date(match.group(3), MONTHS[match.group(1)[:3].upper()], match.group(2))
        if value:
            found.append(value)
    for match in NUMERIC.finditer(text):
        value = _date(match.group(3), int(match.group(2)), match.group(1))  # Correspondence uses day/month/year.
        if value:
            found.append(value)
    for match in ISO.finditer(text):
        value = _date(match.group(1), int(match.group(2)), match.group(3))
        if value:
            found.append(value)
    return list(dict.fromkeys(found))


def parse_review_date(text: str) -> date | None:
    text = text.strip()
    if not text:
        return None
    values = dates_in_text(text)
    return values[0] if len(values) == 1 and (ISO.fullmatch(text) or DAY_MONTH.fullmatch(text)
                                                or MONTH_DAY.fullmatch(text) or NUMERIC.fullmatch(text)) else None


def extract_receipt_date(ocr: OCRResult) -> ReceiptFinding:
    lines = ocr.lines
    document_date = next((dates_in_text(m.group(1))[0] for line in lines
                          if (m := DOC_DATE.match(line.text)) and dates_in_text(m.group(1))), None)
    markers = []
    for i, line in enumerate(lines):
        match = RECEIVED.match(line.text)
        if match and (len(line.text[match.end():].strip()) <= 10 or dates_in_text(line.text)):
            markers.append(i)
    if markers:
        candidates: dict[date, list[str]] = {}
        for index in markers:
            marker = lines[index]
            for line in lines[index:index + 5]:
                if line is not marker and DOC_DATE.match(line.text):
                    continue
                if (marker.top is not None and line.top is not None and marker.height and
                        line.top - marker.top > marker.height * 7):
                    break
                for value in dates_in_text(line.text):
                    candidates.setdefault(value, [marker.text, line.text])
        if len(candidates) == 1:
            value, evidence = next(iter(candidates.items()))
            return ReceiptFinding(value, document_date, list(dict.fromkeys(evidence)))
        return ReceiptFinding(document_date=document_date,
                              evidence=[lines[i].text for i in markers],
                              warning="Receipt stamp date is ambiguous" if candidates else
                                      "Received stamp found, but its date could not be read")

    # Date-only stamp: require an isolated date with adjacent organization text in its OCR block.
    candidates = {}
    for index, line in enumerate(lines):
        if DOC_DATE.match(line.text) or OTHER_STAMP.search(line.text):
            continue
        value = parse_review_date(line.text)
        if value is None:
            continue
        if any(OTHER_STAMP.search(other.text) for other in lines[max(0, index - 3):index + 4]
               if other.block == line.block):
            continue
        neighbor = next((other for other in lines[max(0, index - 2):index + 3]
                         if other is not line and other.block == line.block and ORG.search(other.text)), None)
        if neighbor:
            candidates[value] = [line.text, neighbor.text]
    if len(candidates) == 1:
        value, evidence = next(iter(candidates.items()))
        return ReceiptFinding(value, document_date, evidence,
                              "Date-only stamp detected; verify Receipt Date")
    nearby_date_text = [line.text for line in lines if DOC_DATE.match(line.text)
                        or OTHER_STAMP.search(line.text) or dates_in_text(line.text)]
    return ReceiptFinding(document_date=document_date, evidence=nearby_date_text[:4],
                          warning="Could not confidently identify Receipt Date" if not candidates else
                                  "Multiple possible stamp dates; verify Receipt Date")
