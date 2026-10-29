"""Optional B5 LlamaExtract v2 integration. Never a whole-document accuracy score."""

import json
import math
import re
import time


def external_allowed(settings, sensitivity):
    # Closed enumeration: unknown and Highly Restricted can never reach this API.
    return bool(
        {
            "PUBLIC": settings.external_public_allowed,
            "INTERNAL": settings.external_internal_allowed,
            "CONFIDENTIAL": settings.external_confidential_exception,
        }.get(sensitivity, False)
    )


def evaluate_fields(payload, schema, floor):
    values = payload.get("extract_result") or {}
    metadata = (
        (payload.get("extract_metadata") or {})
        .get("field_metadata", {})
        .get("document_metadata", {})
    )
    checks = []
    # Initial supported scope: flat explicitly named scalar fields. Nested schemas fail closed.
    for name, definition in schema.get("properties", {}).items():
        entry = metadata.get(name, {})
        score, citations = entry.get("confidence"), entry.get("citation", [])
        supported = definition.get("type") in {"string", "number", "integer", "boolean"}
        grounded = bool(citations) and all(
            isinstance(c, dict)
            and isinstance(c.get("page"), int)
            and c["page"] > 0
            and isinstance(c.get("matching_text"), str)
            and c["matching_text"].strip()
            for c in citations
        )
        valid_score = type(score) in {int, float} and math.isfinite(score) and 0 <= score <= 1
        acceptable = (
            supported
            and name in values
            and values[name] is not None
            and grounded
            and valid_score
            and floor is not None
            and score >= floor
        )
        checks.append(
            {
                "field": name,
                "value": values.get(name),
                "confidence": score if valid_score else None,
                "citations": citations,
                "status": "PASS" if acceptable else "HUMAN_REQUIRED",
            }
        )
    return {
        "status": "ACCEPTABLE"
        if checks and all(c["status"] == "PASS" for c in checks)
        else "HUMAN_REQUIRED",
        "provider": "llamaextract",
        "job_id": payload.get("id"),
        "fields": checks,
        "schema": schema,
        "confidence_floor": floor,
        "scope": (
            "Configured fields only; citations are provider evidence, not visual verification."
        ),
    }


def extract_fields(settings, sensitivity, filename, data):
    if not settings.field_schema:
        return {"status": "SKIPPED", "reason": "schema_not_configured"}
    if not external_allowed(settings, sensitivity):
        return {
            "status": "SKIPPED",
            "reason": "external_processing_prohibited",
            "requires_human": True,
        }
    if not settings.llamaextract_api_key or not settings.llamaextract_project_id:
        return {"status": "HUMAN_REQUIRED", "reason": "llamaextract_not_configured"}
    # Invoked only inside the bounded extraction subprocess. Never follows redirects/proxies.
    import httpx2 as httpx

    deadline = time.monotonic() + 45
    try:
        with httpx.Client(
            base_url="https://api.cloud.llamaindex.ai",
            timeout=10,
            follow_redirects=False,
            trust_env=False,
            headers={"Authorization": "Bearer " + settings.llamaextract_api_key.get_secret_value()},
        ) as client:

            def request(method, path, **kwargs):
                with client.stream(method, path, **kwargs) as response:
                    response.raise_for_status()
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 2_000_000 or time.monotonic() > deadline:
                            raise ValueError("response_limit")
                    return json.loads(raw)

            uploaded = request(
                "POST",
                "/api/v1/beta/files",
                data={"purpose": "extract"},
                files={"file": (filename, data, "application/octet-stream")},
            )
            params = {"project_id": settings.llamaextract_project_id}
            job = request(
                "POST",
                "/api/v2/extract",
                params=params,
                json={
                    "file_input": uploaded["id"],
                    "configuration": {
                        "tier": "agentic",
                        "version": "2.5",
                        "extraction_target": "per_doc",
                        "data_schema": settings.field_schema,
                        "cite_sources": True,
                        "confidence_scores": True,
                    },
                },
            )
            job_id = job["id"]
            if not re.fullmatch(r"ext-[A-Za-z0-9-]+", job_id):
                raise ValueError("invalid_job")
            while time.monotonic() < deadline:
                job = request(
                    "GET",
                    f"/api/v2/extract/{job_id}",
                    params={**params, "expand": "extract_metadata"},
                )
                if job["status"] == "COMPLETED":
                    return evaluate_fields(
                        job, settings.field_schema, settings.field_confidence_floor
                    )
                if job["status"] in {"FAILED", "CANCELLED"}:
                    break
                time.sleep(1)
    except Exception:
        pass
    # Never retain remote error bodies, which can contain document content or credentials.
    return {"status": "HUMAN_REQUIRED", "reason": "llamaextract_failed_or_timed_out"}
