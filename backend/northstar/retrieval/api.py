"""Administrative API. Authentication occurs before parsing any upload body."""

import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

from northstar.domain import DomainError
from northstar.retrieval.extraction import MAX_BYTES
from northstar.retrieval.models import Document
from northstar.retrieval.service import KnowledgeService, describe


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
    async with request.form(max_files=1, max_fields=3, max_part_size=8192) as form:
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
                422, "Supply policy_id and optional ISO validity timestamps."
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
    async with request.form(max_files=10, max_fields=10, max_part_size=8192) as form:
        files, identifiers = form.getlist("files"), form.getlist("policy_ids")
        if (
            not files
            or len(files) != len(identifiers)
            or any(not isinstance(f, UploadFile) for f in files)
            or any(not isinstance(p, str) for p in identifiers)
        ):
            raise HTTPException(422, "Supply matching files and policy_ids fields.")
        results = []
        for file, identifier in zip(files, identifiers, strict=True):
            data = await file.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                results.append({"policy_id": identifier, "error": "file_too_large"})
                continue
            try:
                results.append(
                    await run_in_threadpool(
                        KnowledgeService(request.app.state.sessions).ingest,
                        identifier,
                        file.filename or "",
                        data,
                    )
                )
            except DomainError as exc:
                results.append({"policy_id": identifier, "error": exc.code})
        return results


@router.post("/{document_id}/deactivate")
def deactivate_document(document_id: str, request: Request):
    with request.app.state.sessions.begin() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise DomainError("not_found", "Document does not exist.", 404)
        document.enabled = False
        return {"id": document_id, "enabled": False}
