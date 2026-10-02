"""Conservative organizational-origin detection from OCR lines."""

import re
from dataclasses import dataclass, field

from .models import OCRLine, OCRResult


ORG_KIND = re.compile(r"\b(branch|division|department|office|agency|authority|unit|secretariat|ministry|bureau|commission|council)\b", re.I)
SPECIFIC = re.compile(r"\b(branch|division|department|office|agency|authority|unit|secretariat|bureau|commission|council)\b", re.I)
MEMO_FIELD = re.compile(r"^\s*(to|from|frorn|subject|subjecl|thru|through|date)\s*[:：-]", re.I)
STAMP = re.compile(r"\b(received|eceived|approved|not approved|urgent|stamp)\b", re.I)
SENDER_SENTENCE = re.compile(
    r"^\s*(?:the\s+)?(.{5,100}?\b(?:branch|division|department|office|agency|authority|unit|secretariat))\s+"
    r"(?:respectfully\s+)?(?:requests?|submits?|writes?|seeks?|advises?|recommends?)\b", re.I)


@dataclass
class OriginFinding:
    value: str = ""
    evidence: list[str] = field(default_factory=list)
    warning: str = ""


def _clean(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" -:|,.\t")
    value = re.sub(r"\bM[i1l]N[i1l]STR[YV]\b", "Ministry", value, flags=re.I)
    if value.isupper() or sum(c.isupper() for c in value if c.isalpha()) > len(value) * .6:
        value = value.title()
        value = re.sub(r"\b(Of|And|The)\b", lambda m: m.group().lower(), value)
    return value


def _candidate(line: OCRLine) -> str:
    value = _clean(line.text)
    if (not 8 <= len(value) <= 110 or MEMO_FIELD.match(value) or STAMP.search(value)
            or not ORG_KIND.search(value) or (line.confidence is not None and line.confidence < 55)):
        return ""
    # A descriptive job title is not the issuing organization.
    if re.match(r"^(from the desk|director|permanent secretary)\b", value, re.I):
        return ""
    return value


def extract_origin(ocr: OCRResult) -> OriginFinding:
    lines = ocr.lines
    first_field = next((i for i, line in enumerate(lines) if MEMO_FIELD.match(line.text)), len(lines))
    header = [(line, _candidate(line)) for line in lines[:first_field]]
    header = [(line, value) for line, value in header if value]
    specific = [(line, value) for line, value in header if SPECIFIC.search(value)]
    if specific:
        line, value = specific[-1]
        return OriginFinding(value, [line.text])

    # A sender naming its own branch in the opening sentence can refine a ministry letterhead.
    subject_index = next((i for i, line in enumerate(lines) if re.match(r"^\s*subject\s*[:：-]", line.text, re.I)), -1)
    if subject_index >= 0:
        for line in lines[subject_index + 1:subject_index + 4]:
            match = SENDER_SENTENCE.match(line.text)
            if not match or (line.confidence is not None and line.confidence < 65):
                continue
            value = _clean(match.group(1))
            # A matching organizational desk line supports the body's sender claim.
            desk = next((earlier.text for earlier in lines[:first_field]
                         if "desk" in earlier.text.lower() and
                         any(word.lower() in earlier.text.lower() for word in re.findall(r"[A-Za-z]{5,}", value)[:5])), "")
            if desk or header:
                return OriginFinding(value, [line.text, desk or header[0][0].text])
            return OriginFinding(value, [line.text], "Origin appears only in body text; verify the issuing organization")

    if header:
        line, value = header[-1]
        return OriginFinding(value, [line.text])
    return OriginFinding(warning="Could not confidently identify Origin")
