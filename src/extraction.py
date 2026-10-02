"""Semantic label extraction from OCR lines; no PDF or OCR engine dependency."""

import re

from .models import DocumentResult, OCRLine, OCRResult, Status


LABEL = re.compile(r"^\s*(to|from|frorn|subject|subjecl)\s*[:：\-–]\s*(.*)$", re.I)
ISOLATED_LABEL = re.compile(r"^\s*(to|from|frorn|subject|subjecl)\s*$", re.I)
BODY_START = re.compile(
    r"^(dear\b|re\s*:|reference\s*:|date\s*:|salutation\s*:|"
    r"i\s+(?:am|write|refer)|we\s+(?:are|write|refer)|"
    r"this\s+(?:letter|memorandum|memo)|please\b)", re.I
)
NAME_WORD = re.compile(r"[A-Za-z][A-Za-z.'’-]*")
JOB_TITLE = re.compile(r"^(permanent secretary|director|senior director|chief|manager|officer|head|deputy|assistant|acting)\b", re.I)
INLINE_DATE = re.compile(r"\s+\d{1,2}\s*[-/]?\s*[A-Za-z]{3,9}\s+\d{4}\b.*$", re.I)
TRAILING_AFTER_SUFFIX = re.compile(r"(\((?:Mr|Mrs|Ms|Dr)\.?\))\s+.+$", re.I)


def _label(text: str) -> tuple[str, str] | None:
    match = LABEL.match(text) or ISOLATED_LABEL.match(text)
    if not match:
        return None
    name = match.group(1).lower()
    name = {"frorn": "from", "subjecl": "subject"}.get(name, name)
    return name, match.group(2).strip() if match.lastindex == 2 else ""


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" \t:;-–")


def _next_value(lines: list[OCRLine], start: int) -> tuple[str, OCRLine | None]:
    for line in lines[start + 1:]:
        if _label(line.text):
            break
        value = _clean(line.text)
        if value:
            return value, line
    return "", None


def _subject(lines: list[OCRLine], start: int, inline: str) -> tuple[str, list[OCRLine], bool]:
    pieces = [_clean(inline)] if _clean(inline) else []
    used = [lines[start]] if pieces else []
    previous = lines[start]
    truncated = False
    for line in lines[start + 1:]:
        value = _clean(line.text)
        if _label(line.text) or not value or BODY_START.match(value):
            break
        if previous.top is not None and line.top is not None and previous.height:
            if line.top - previous.top > max(previous.height * 1.8, 90):
                break
        if len(pieces) >= 4:
            truncated = True
            break
        pieces.append(value)
        used.append(line)
        previous = line
    return " ".join(pieces), used, truncated


class CorrespondenceFieldExtractor:
    def extract(self, ocr: OCRResult, file_name: str) -> DocumentResult:
        result = DocumentResult(file_name=file_name)
        matches: dict[str, list[tuple[int, str]]] = {"to": [], "from": [], "subject": []}
        for i, line in enumerate(ocr.lines):
            found = _label(line.text)
            if found:
                matches[found[0]].append((i, found[1]))

        used: list[OCRLine] = []
        for field in ("to", "from"):
            candidates = matches[field]
            if len(candidates) != 1:
                result.warnings.append(f"Could not confidently identify {field.title()}: "
                                       + ("missing label" if not candidates else "multiple labels"))
                continue
            index, inline = candidates[0]
            value = _clean(inline)
            source = ocr.lines[index]
            if not value:
                value, source = _next_value(ocr.lines, index)
            if INLINE_DATE.search(value):
                value = INLINE_DATE.sub("", value).strip(" \"'|,;:-")
                result.warnings.append(f"{field.title()} line overlaps a date; verify the name")
            if TRAILING_AFTER_SUFFIX.search(value):
                value = TRAILING_AFTER_SUFFIX.sub(r"\1", value)
                result.warnings.append(f"{field.title()} line contains text after a name suffix; verify the name")
            value = value.strip(" \"'|,;:-")
            if len(NAME_WORD.findall(value)) < 2 or BODY_START.match(value) or JOB_TITLE.match(value):
                result.warnings.append(f"Could not confidently identify {field.title()}: name unclear")
                continue
            setattr(result, "from_" if field == "from" else field, value)
            used.extend([ocr.lines[index], source] if source is not ocr.lines[index] else [source])

        candidates = matches["subject"]
        if len(candidates) != 1:
            result.warnings.append("Could not confidently identify Subject: "
                                   + ("missing label" if not candidates else "multiple labels"))
        else:
            index, inline = candidates[0]
            value, subject_lines, truncated = _subject(ocr.lines, index, inline)
            if not value or not re.search(r"[A-Za-z]", value):
                result.warnings.append("Could not confidently identify Subject: empty value")
            else:
                result.subject = value
                used.extend(subject_lines)
            if truncated:
                result.warnings.append("Subject may continue beyond four lines")

        scores = [line.confidence for line in used if line and line.confidence is not None]
        result.confidence = min(scores) / 100 if scores else None
        if result.confidence is not None and result.confidence < 0.60:
            result.warnings.append("Low OCR confidence in an extracted field")
        result.status = Status.SUCCESS if all((result.to, result.from_, result.subject)) and not result.warnings else Status.NEEDS_REVIEW
        return result
