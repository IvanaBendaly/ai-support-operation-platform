"""B1–B4: local extraction, evidence-based quality checks and a limited DPP rubric.

The rubric checks internal consistency, not visual fidelity or full DPP conformance.
Missing diagnostics and unsupported visual checks are explicitly NOT_EVALUATED.
"""

import math
from dataclasses import asdict
from importlib.metadata import version
from pathlib import PurePosixPath

from northstar.config import ExtractionSettings
from northstar.retrieval.extraction import MAX_TEXT, IngestionError, extract, normalize


def rule(name, status, detail, source=""):
    return {"rule": name, "status": status, "detail": detail, "source": source}


def quality(content, metadata, settings):
    checks = []
    if not content or not any(c.isalnum() for c in content):
        checks.append(rule("nonempty_text", "FAIL", "No readable text was extracted."))
    else:
        checks.append(rule("nonempty_text", "PASS", "Readable text exists."))
    checks.append(
        rule(
            "text_integrity",
            "FAIL" if "\ufffd" in content else "PASS",
            "Replacement characters require inspection.",
        )
    )
    checks.append(
        rule(
            "minimum_content",
            "PASS" if len(content) >= settings.minimum_characters else "FAIL",
            f"Configured minimum: {settings.minimum_characters} characters.",
        )
    )
    count = metadata.get("page_count")
    pages = {p for e in metadata.get("elements", []) if e["text"].strip() for p in e["pages"]}
    if count:
        missing = sorted(set(range(1, count + 1)) - pages)
        checks.append(
            rule(
                "page_coverage",
                "FAIL" if missing else "PASS",
                f"Pages without extracted text: {missing}. Blank pages need human confirmation.",
            )
        )
    if metadata.get("parser") == "docling":
        reports = {
            "document": metadata.get("confidence", {}),
            **metadata.get("page_confidence", {}),
        }
        for scope, scores in reports.items():
            for name in ("parse_score", "layout_score", "ocr_score", "table_score"):
                score = scores.get(name)
                status = "NOT_EVALUATED"
                if (
                    isinstance(score, (int, float))
                    and math.isfinite(score)
                    and settings.confidence_floor is not None
                ):
                    status = "PASS" if score >= settings.confidence_floor else "FAIL"
                checks.append(
                    rule(
                        name,
                        status,
                        f"Score: {score}; evaluated floor: {settings.confidence_floor}",
                        scope,
                    )
                )
    for warning in metadata.get("warnings", []):
        checks.append(rule("parser_warning", "FAIL", warning))
    failed = not content or len(content) > MAX_TEXT
    return {
        "outcome": "FAILED"
        if failed
        else "UNCERTAIN"
        if any(c["status"] != "PASS" for c in checks)
        else "ACCEPTABLE",
        "checks": checks,
    }


def dpp(metadata):
    elements = metadata.get("elements", [])
    local_text = metadata.get("parser") == "python"
    orders = [e["order"] for e in elements]
    checks = [
        rule(
            "order_sequence",
            "PASS" if orders == list(range(1, len(elements) + 1)) else "FAIL",
            "Internal element ordering only; DPP §5.9 visual reading order is separate.",
        ),
        rule(
            "source_references",
            "PASS" if elements and all(e["source"] for e in elements) else "FAIL",
            "Source references retained; DPP §2.3 traceability subset.",
        ),
        rule(
            "visual_reading_order",
            "NOT_EVALUATED",
            "Not applicable to native text."
            if local_text
            else "Compare with the original page (DPP §5.9).",
        ),
        rule(
            "forms_and_visual_fidelity",
            "NOT_EVALUATED",
            "Native text has no visual source."
            if local_text
            else "Human verification required (DPP §10).",
        ),
    ]
    for e in elements:
        kind = e["kind"]
        if kind in {"heading", "section_header", "title"}:
            checks.append(
                rule(
                    "heading_content",
                    "PASS" if e["text"].strip() else "FAIL",
                    "Heading text retained; hierarchy requires source comparison (§4.5).",
                    e["source"],
                )
            )
        if kind == "list_item":
            checks.append(
                rule(
                    "list_content",
                    "PASS" if e["text"].strip() else "FAIL",
                    "Item text retained; nesting/markers need source comparison (§8.1).",
                    e["source"],
                )
            )
        if kind == "table":
            table = e.get("table", {})
            rows = table.get("rows")
            valid = (
                bool(table.get("table_cells"))
                if rows is None
                else bool(rows) and len({len(r) for r in rows}) == 1
            )
            checks.append(
                rule(
                    "table_shape",
                    "PASS" if valid else "FAIL",
                    "Internal table shape only; spans and header fidelity need human "
                    "comparison (§9.4.2).",
                    e["source"],
                )
            )
    return {
        "rubric": "northstar-dpp-subset-v1",
        "reference": "DPP working draft 0.1",
        "checks": checks,
        "requires_human": not local_text or any(c["status"] == "FAIL" for c in checks),
    }


def liteparse(data):
    from liteparse import LiteParse

    # No remote OCR server, URL input, model download or automatic cloud fallback.
    parsed = LiteParse(
        ocr_enabled=False, max_pages=200, extract_blocks=True, extract_form_fields=True, quiet=True
    ).parse(data)
    elements, sections = [], []
    for page in parsed.pages:
        source = f"page:{page.page_num}"
        for offset in range(0, len(page.text), 2000):
            sections.append(
                (f"{source};offset:{offset}", normalize(page.text[offset : offset + 2000]))
            )
        for block in page.blocks or []:
            value = block.text or "\n".join(block.lines or [])
            table = asdict(block) if block.kind == "table" else None
            if table:
                value = "\n".join(
                    " | ".join(c["text"] for c in row)
                    for row in ([table["header"]] if table["header"] else [])
                    + (table["rows"] or [])
                )
            elements.append(
                {
                    "kind": block.kind,
                    "text": normalize(value),
                    "source": source,
                    "pages": [page.page_num],
                    "order": len(elements) + 1,
                    "references": [asdict(block.bbox)] if block.bbox else [],
                    "table": table,
                }
            )
        if not page.blocks:
            elements.append(
                {
                    "kind": "text",
                    "text": normalize(page.text),
                    "source": source,
                    "pages": [page.page_num],
                    "order": len(elements) + 1,
                    "references": [],
                }
            )
    content = normalize("\n\n".join(p.text for p in parsed.pages))
    if not any(c.isalnum() for c in content):
        raise IngestionError("empty_or_unreadable_text")
    if len(content) > MAX_TEXT:
        raise IngestionError("extracted_text_too_large")
    return ("application/pdf", content, sections, []), {
        "parser": "liteparse",
        "parser_version": version("liteparse"),
        "page_count": parsed.total_pages,
        "confidence": {},
        "elements": elements,
        "warnings": [],
        "ocr": "disabled; scanned pages require human verification",
        "forms": [asdict(f) for p in parsed.pages for f in p.form_fields or []],
    }


def pipeline(filename, data, settings=None):
    settings = settings or ExtractionSettings()
    attempts = []

    def attempt(parser):
        metadata = {"parser": parser, "elements": [], "warnings": []}
        result, error = None, None
        try:
            if parser == "liteparse":
                result, metadata = liteparse(data)
            else:
                result = extract(filename, data, metadata)
        except IngestionError as exc:
            error = str(exc)
        except Exception:
            error = "parser_failed"
        assessment = quality(result[1] if result else "", metadata, settings)
        attempts.append(
            {"metadata": metadata, "quality": assessment, "result": result, "error": error}
        )
        return len(attempts) - 1

    suffix = PurePosixPath(filename.lower()).suffix
    selected = attempt("docling" if suffix in {".pdf", ".docx"} else "python")
    if (
        attempts[0]["quality"]["outcome"] != "ACCEPTABLE"
        and suffix == ".pdf"
        and settings.liteparse_enabled
    ):
        fallback = attempt("liteparse")
        if attempts[fallback]["quality"]["outcome"] == "ACCEPTABLE":
            selected = fallback
        elif (
            attempts[0]["result"] is None
            and attempts[fallback]["result"] is not None
            and attempts[fallback]["quality"]["outcome"] != "FAILED"
        ):
            # A candidate for human inspection, explicitly not an accepted result.
            selected = fallback
    candidate = attempts[selected]
    structural = dpp(candidate["metadata"])
    verified = candidate["quality"]["outcome"] == "ACCEPTABLE" and not structural["requires_human"]
    return {
        "attempts": attempts,
        "selected": selected,
        "dpp": structural,
        "status": "VERIFIED" if verified else "HUMAN_REQUIRED",
        "result": candidate["result"],
        "error": candidate["error"],
        "field_assessment": {"status": "SKIPPED", "reason": "schema_not_configured"},
    }
