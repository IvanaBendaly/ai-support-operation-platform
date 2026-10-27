import re
import unicodedata
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

MAX_BYTES = 5 * 1024 * 1024
MAX_TEXT = 1_000_000
MEDIA = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class IngestionError(ValueError):
    pass


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    if any(unicodedata.category(c) == "Cc" and c not in "\n\t" for c in text):
        raise IngestionError("unreadable_text")
    return "\n".join(line.rstrip() for line in text.splitlines())


def validate_file(filename: str, data: bytes) -> str:
    suffix = PurePosixPath(filename.lower()).suffix
    if suffix not in MEDIA:
        raise IngestionError("unsupported_file_type")
    if not data:
        raise IngestionError("empty_document")
    if len(data) > MAX_BYTES:
        raise IngestionError("file_too_large")
    return MEDIA[suffix]


def structured_units(filename: str, data: bytes):
    from docling.backend.docling_parse_backend import ThreadedDoclingParseDocumentBackend
    from docling.backend.msword_backend import MsWordDocumentBackend
    from docling.datamodel.backend_options import ThreadedDoclingParseBackendOptions
    from docling.datamodel.base_models import ConversionStatus, InputFormat
    from docling.datamodel.document import InputDocument
    from docling.datamodel.pipeline_options import ConvertPipelineOptions, NativePdfPipelineOptions
    from docling.datamodel.settings import DocumentLimits
    from docling.pipeline.native_pdf_pipeline import NativePdfPipeline
    from docling.pipeline.simple_pipeline import SimplePipeline
    from docling_core.types.doc import TableItem, TextItem

    suffix = PurePosixPath(filename.lower()).suffix
    if suffix == ".docx":
        try:
            with ZipFile(BytesIO(data)) as archive:
                entries = archive.infolist()
                if len(entries) > 2000 or sum(i.file_size for i in entries) > 25 * 1024 * 1024:
                    raise IngestionError("docx_expanded_size_limit")
                if "word/document.xml" not in archive.namelist():
                    raise IngestionError("corrupt_docx")
        except (BadZipFile, OSError):
            raise IngestionError("corrupt_docx") from None
    try:
        # Instantiate only the required pipelines: the top-level converter imports
        # optional ASR/ML dependencies even when converting native text documents.
        is_pdf = suffix == ".pdf"
        incoming = InputDocument(
            path_or_stream=BytesIO(data),
            filename=filename,
            format=InputFormat.PDF if is_pdf else InputFormat.DOCX,
            backend=ThreadedDoclingParseDocumentBackend if is_pdf else MsWordDocumentBackend,
            limits=DocumentLimits(max_num_pages=200, max_file_size=MAX_BYTES),
            backend_options=ThreadedDoclingParseBackendOptions(
                parser_threads=1, render_pages=False, include_bitmap_images=False
            )
            if is_pdf
            else None,
        )
        if not incoming.valid:
            raise IngestionError("corrupt_pdf" if is_pdf else "corrupt_docx")
        pipeline = (
            NativePdfPipeline(
                NativePdfPipelineOptions(
                    parser_threads=1, generate_page_images=False, generate_picture_images=False
                )
            )
            if is_pdf
            else SimplePipeline(ConvertPipelineOptions())
        )
        result = pipeline.execute(incoming, raises_on_error=False)
        if result.status != ConversionStatus.SUCCESS:
            raise IngestionError("corrupt_pdf" if suffix == ".pdf" else "corrupt_docx")
        units, heading, total = [], "", 0
        for item, _ in result.document.iterate_items():
            if isinstance(item, TableItem):
                value = item.export_to_markdown(doc=result.document)
            elif isinstance(item, TextItem):
                value = item.text
                if item.label.value in {"section_header", "title"}:
                    heading = value
            else:
                continue
            value = normalize(value)
            total += len(value)
            if total > MAX_TEXT:
                raise IngestionError("extracted_text_too_large")
            pages = sorted({p.page_no for p in item.prov})
            page_ref = ";".join(f"page:{page}" for page in pages)
            source = f"{page_ref};item:{item.self_ref};heading:{heading}"[:470]
            units.append((source, value))
        return units
    except IngestionError:
        raise
    except Exception:
        raise IngestionError("corrupt_pdf" if suffix == ".pdf" else "corrupt_docx") from None


def extract(filename: str, data: bytes) -> tuple[str, str, list[tuple[str, str]], list[str]]:
    media = validate_file(filename, data)
    suffix = PurePosixPath(filename.lower()).suffix
    warnings = []
    if suffix in {".pdf", ".docx"}:
        units = structured_units(filename, data)
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
    return media, text, sections, warnings
