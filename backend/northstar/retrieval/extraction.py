"""Conservative text extraction: no OCR or layout reconstruction."""

import re
import unicodedata
from io import BytesIO
from pathlib import PurePosixPath

from pypdf import PdfReader

MAX_BYTES = 5 * 1024 * 1024
MAX_TEXT = 1_000_000
MEDIA = {".md": "text/markdown", ".txt": "text/plain", ".pdf": "application/pdf"}


class IngestionError(ValueError):
    pass


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    if any(unicodedata.category(c) == "Cc" and c not in "\n\t" for c in text):
        raise IngestionError("unreadable_text")
    return "\n".join(line.rstrip() for line in text.splitlines())


def extract(filename: str, data: bytes) -> tuple[str, str, list[tuple[str, str]], list[str]]:
    suffix = PurePosixPath(filename.lower()).suffix
    if suffix not in MEDIA:
        raise IngestionError("unsupported_file_type")
    if not data:
        raise IngestionError("empty_document")
    if len(data) > MAX_BYTES:
        raise IngestionError("file_too_large")
    warnings = []
    if suffix == ".pdf":
        try:
            reader = PdfReader(BytesIO(data), strict=True)
            if reader.is_encrypted:
                raise IngestionError("encrypted_pdf")
            if len(reader.pages) > 200:
                raise IngestionError("too_many_pages")
            units = []
            for number, page in enumerate(reader.pages, 1):
                stream = page.get_contents()
                if stream and len(stream.get_data()) > MAX_BYTES:
                    raise IngestionError("pdf_page_too_large")
                value = normalize(page.extract_text() or "")
                if not value:
                    warnings.append(f"page_{number}_has_no_text")
                units.append((f"page:{number}", value))
                if sum(len(t) for _, t in units) > MAX_TEXT:
                    raise IngestionError("extracted_text_too_large")
        except IngestionError:
            raise
        except Exception:
            raise IngestionError("corrupt_pdf") from None
    else:
        try:
            value = normalize(data.decode("utf-8-sig"))
        except UnicodeDecodeError:
            raise IngestionError("text_must_be_utf8") from None
        units = []
        start, lines, heading = 1, [], ""
        for number, line in enumerate(value.splitlines(), 1):
            if suffix == ".md" and re.match(r"^#{1,6}\s+", line):
                if lines:
                    units.append((f"line:{start};heading:{heading}"[:480], "\n".join(lines)))
                start, lines, heading = number, [], line.lstrip("# ")
            lines.append(line)
        if lines:
            units.append((f"line:{start};heading:{heading}"[:480], "\n".join(lines)))
    text = "\n\n".join(t for _, t in units)
    if not text or not any(c.isalnum() for c in text):
        raise IngestionError("empty_or_unreadable_text")
    if len(text) > MAX_TEXT:
        raise IngestionError("extracted_text_too_large")
    if text.count("\ufffd") / len(text) > 0.02:
        raise IngestionError("unreadable_text")
    if len(text) < 80 or "\ufffd" in text:
        warnings.append("review_extraction_quality")
    sections = []
    for source, value in units:
        # Retain all characters, including whitespace and policy punctuation.
        for offset in range(0, len(value), 2000):
            chunk = value[offset : offset + 2000]
            if chunk.strip():
                sections.append((f"{source};offset:{offset}", chunk))
    return MEDIA[suffix], text, sections, warnings
