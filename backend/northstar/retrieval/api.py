"""Administrative API. Authentication occurs before parsing any upload body."""

import secrets
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

from northstar.domain import DomainError
from northstar.retrieval.extraction import MAX_BYTES
from northstar.retrieval.models import Document
from northstar.retrieval.service import KnowledgeService, describe, record_event


def administrator(request: Request):
    token = request.app.state.settings.admin_token
    if not token:
        raise HTTPException(503, "Document administration is not configured.")
    supplied = request.headers.get("authorization", "")
    if not secrets.compare_digest(
        supplied.encode(), ("Bearer " + token.get_secret_value()).encode()
    ):
        raise HTTPException(401, "Administrator credentials required.")


router = APIRouter(
    prefix="/api/admin/documents", tags=["Knowledge"], dependencies=[Depends(administrator)]
)


class UploadMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_id: str
    title: str = Field(min_length=1, max_length=160)
    sensitivity: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "HIGHLY_RESTRICTED"]
    valid_from: datetime | None = None
    valid_until: datetime | None = None


async def upload(request: Request, policy_id: str | None = None):
    # Stream into a bounded buffer before the multipart parser can spool unbounded files.
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BYTES + 65536:
            raise HTTPException(413, "Upload request exceeds 5 MiB plus metadata allowance.")
    request._body = bytes(body)
    # Reset stream consumption so Starlette's multipart parser reads the bounded body.
    async with request.form(max_files=1, max_fields=5, max_part_size=8192) as form:
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise HTTPException(422, "A multipart file is required.")
        try:
            metadata = UploadMetadata.model_validate(
                {
                    **{k: v for k, v in form.items() if k != "file"},
                    **({"policy_id": policy_id} if policy_id else {}),
                }
            )
        except ValidationError:
            raise HTTPException(
                422, "Supply policy_id, title, sensitivity and optional ISO validity timestamps."
            ) from None
        data = await file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "File exceeds 5 MiB.")
        result = await run_in_threadpool(
            KnowledgeService(request.app.state.sessions).ingest,
            metadata.policy_id,
            file.filename or "",
            data,
            metadata.valid_from,
            metadata.valid_until,
            policy_id is not None,
            defer=True,
            title=metadata.title,
            sensitivity=metadata.sensitivity,
        )
        return result


@router.post("")
async def create(request: Request):
    return await upload(request)


@router.post("/policies/{policy_id}/versions")
async def replace(policy_id: str, request: Request):
    return await upload(request, policy_id)


@router.get("")
def listing(request: Request, offset: int = 0, limit: int = 25):
    if offset < 0 or not 1 <= limit <= 100:
        raise HTTPException(422, "Invalid pagination.")
    with request.app.state.sessions() as session:
        return [
            describe(session, d)
            for d in session.scalars(
                select(Document)
                .order_by(Document.policy_id, Document.version)
                .offset(offset)
                .limit(limit)
            )
        ]


@router.get("/{document_id}")
def inspect_document(document_id: str, request: Request):
    with request.app.state.sessions() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise DomainError("not_found", "Document does not exist.", 404)
        if (
            document.sensitivity in {"CONFIDENTIAL", "HIGHLY_RESTRICTED"}
            and not request.app.state.settings.storage.restricted_environment_approved
        ):
            raise HTTPException(403, "Restricted preview environment is not approved.")
        if document.publication_status == "DELETED":
            raise HTTPException(404, "Document does not exist.")
        return describe(session, document, include_sections=True)


@router.post("/policies/{policy_id}/deactivate")
def deactivate(policy_id: str, request: Request):
    return KnowledgeService(request.app.state.sessions).deactivate(policy_id)


@router.post("/batch")
async def batch(request: Request):
    """Up to ten independent uploads; matching policy_ids and files in form order."""
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 2 * MAX_BYTES + 65536:
            raise HTTPException(413, "Batch request exceeds 10 MiB.")
    request._body = bytes(body)
    async with request.form(max_files=10, max_fields=30, max_part_size=8192) as form:
        files, identifiers = form.getlist("files"), form.getlist("policy_ids")
        titles, sensitivities = form.getlist("titles"), form.getlist("sensitivities")
        if (
            not files
            or len(files) != len(identifiers)
            or len(files) != len(titles)
            or len(files) != len(sensitivities)
            or any(k not in {"files", "policy_ids", "titles", "sensitivities"} for k in form)
            or any(not isinstance(f, UploadFile) for f in files)
            or any(not isinstance(p, str) for p in identifiers)
        ):
            raise HTTPException(422, "Supply matching files, policy_ids, titles and sensitivities.")
        results = []
        for file, identifier, title, sensitivity in zip(
            files, identifiers, titles, sensitivities, strict=True
        ):
            data = await file.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                results.append({"policy_id": identifier, "error": "file_too_large"})
                continue
            try:
                metadata = UploadMetadata(
                    policy_id=identifier, title=title, sensitivity=sensitivity
                )
                results.append(
                    await run_in_threadpool(
                        KnowledgeService(request.app.state.sessions).ingest,
                        identifier,
                        file.filename or "",
                        data,
                        defer=True,
                        title=metadata.title,
                        sensitivity=metadata.sensitivity,
                    )
                )
            except DomainError as exc:
                results.append({"policy_id": identifier, "error": exc.code})
            except ValidationError:
                results.append({"policy_id": identifier, "error": "invalid_metadata"})
        return results


@router.post("/{document_id}/deactivate")
def deactivate_document(document_id: str, request: Request):
    with request.app.state.sessions.begin() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise DomainError("not_found", "Document does not exist.", 404)
        document.enabled = False
        record_event(session, document_id, "deactivated", "administrator")
        return {"id": document_id, "enabled": False}


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["APPROVED", "REJECTED", "CHANGES_REQUESTED", "DELETED"]
    reason: str = Field(min_length=1, max_length=500)


class CorrectedSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=1_000_000)


class VerificationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["ACCEPT", "CORRECT", "REJECT", "REPROCESS"]
    reason: str = Field(min_length=1, max_length=500)
    revision: int = Field(ge=0)
    corrections: list[CorrectedSection] | None = Field(default=None, max_length=1000)


@router.post("/{document_id}/verification")
def verify_extraction(document_id: str, body: VerificationDecision, request: Request):
    from northstar.retrieval.extraction_review import verify

    return verify(
        request.app.state.sessions,
        document_id,
        body.decision,
        body.reason,
        body.revision,
        [s.model_dump() for s in body.corrections] if body.corrections else None,
    )


@router.get("/{document_id}/original")
def original(document_id: str, request: Request):
    from starlette.responses import Response

    from northstar.storage import store_for

    with request.app.state.sessions() as session:
        document = session.get(Document, document_id)
        if document is None or document.publication_status == "DELETED":
            raise HTTPException(404, "Document does not exist.")
        if (
            document.sensitivity in {"CONFIDENTIAL", "HIGHLY_RESTRICTED"}
            and not request.app.state.settings.storage.restricted_environment_approved
        ):
            raise HTTPException(403, "Restricted environment is not approved.")
        data = store_for(request.app.state.sessions).get(
            document.storage_key, document.original_hash
        )
        safe_type = (
            document.media_type
            if document.media_type in {"application/pdf", "text/plain", "text/markdown"}
            else "application/octet-stream"
        )
        return Response(
            data,
            media_type=safe_type,
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "sandbox; default-src 'none'",
                "Content-Disposition": "attachment",
            },
        )


@router.post("/{document_id}/decision")
def decide(document_id: str, body: Decision, request: Request):
    return KnowledgeService(request.app.state.sessions).decide(
        document_id, body.decision, body.reason
    )


class ClassificationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sensitivity: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "HIGHLY_RESTRICTED"]
    title: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=1, max_length=500)


@router.post("/{document_id}/classification")
def classify_legacy(document_id: str, body: ClassificationUpdate, request: Request):
    with request.app.state.sessions.begin() as session:
        document = session.get(Document, document_id, with_for_update=True)
        if document is None:
            raise DomainError("not_found", "Document does not exist.", 404)
        if document.sensitivity != "UNCLASSIFIED" or document.publication_status == "DELETED":
            raise DomainError(
                "immutable_classification",
                "Only unclassified legacy records can be classified.",
                409,
            )
        if (
            body.sensitivity in {"CONFIDENTIAL", "HIGHLY_RESTRICTED"}
            and not request.app.state.settings.storage.restricted_environment_approved
        ):
            raise HTTPException(403, "Restricted storage environment is not approved.")
        if not body.title.strip() or not body.reason.strip():
            raise HTTPException(422, "Title and reason cannot be blank.")
        document.sensitivity, document.title = body.sensitivity, body.title.strip()
        document.review_status = "PENDING"
        record_event(session, document_id, "classified", "administrator", body.reason.strip())
        return {"id": document_id, "sensitivity": document.sensitivity}
