"""Customer cases plus the authorized human-review/recovery boundary."""

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from northstar.cases.credentials import authenticated_customer
from northstar.cases.schemas import CreateCase, FollowUp, HumanOutcome, Outcome, Retry
from northstar.cases.service import CaseService
from northstar.domain import DomainError
from northstar.retrieval.api import administrator

router = APIRouter(prefix="/api/cases", tags=["Cases"])
admin_router = APIRouter(
    prefix="/api/admin/cases", tags=["Case administration"], dependencies=[Depends(administrator)]
)


async def body(request: Request, model):
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 65536:
            raise DomainError("request_too_large", "Case requests must not exceed 64 KiB.", 413)
    try:
        return model.model_validate_json(bytes(content))
    except ValidationError:
        raise DomainError(
            "invalid_case_input", "Check required fields, field lengths and allowed values.", 422
        ) from None


def service(request: Request):
    return CaseService(request.app.state.sessions)


@router.post("", status_code=201)
async def create(request: Request, customer: str = Depends(authenticated_customer)):
    data = await body(request, CreateCase)
    return await run_in_threadpool(
        service(request).create, customer, request.headers.get("idempotency-key", ""), data
    )


@router.get("")
def listing(
    request: Request,
    customer: str = Depends(authenticated_customer),
    status: str | None = None,
    category: str | None = None,
    account_id: str | None = None,
    limit: int = 25,
    offset: int = 0,
):
    return service(request).list_cases(
        customer,
        status=status,
        category=category,
        account_id=account_id,
        limit=limit,
        offset=offset,
    )


@router.get("/{case_id}")
def inspect(case_id: str, request: Request, customer: str = Depends(authenticated_customer)):
    return service(request).get(customer, case_id)


@router.post("/{case_id}/messages", status_code=201)
async def follow_up(
    case_id: str, request: Request, customer: str = Depends(authenticated_customer)
):
    data = await body(request, FollowUp)
    return await run_in_threadpool(
        service(request).follow_up,
        customer,
        case_id,
        request.headers.get("idempotency-key", ""),
        data,
    )


@router.post("/{case_id}/retry")
async def retry(case_id: str, request: Request, customer: str = Depends(authenticated_customer)):
    data = await body(request, Retry)
    return await run_in_threadpool(service(request).retry, customer, case_id, data.expected_version)


@router.get("/{case_id}/{history_kind}")
def history(
    case_id: str,
    history_kind: str,
    request: Request,
    customer: str = Depends(authenticated_customer),
    limit: int = 25,
    offset: int = 0,
):
    if history_kind not in {"messages", "events", "attempts"}:
        raise DomainError("not_found", "History endpoint not found.", 404)
    return service(request).history(customer, case_id, history_kind, limit, offset)


@admin_router.post("/recover")
def recover(request: Request):
    return {"recovered": service(request).recover_expired()}


@admin_router.post("/{case_id}/review")
async def human_review(case_id: str, request: Request):
    data = await body(request, HumanOutcome)
    outcome = Outcome.model_validate(data.model_dump(exclude={"expected_version"}))
    return await run_in_threadpool(
        service(request).human_review, case_id, data.expected_version, outcome
    )


@admin_router.get("/{case_id}")
def admin_inspect(case_id: str, request: Request):
    return service(request).get(None, case_id)


@admin_router.get("/{case_id}/{history_kind}")
def admin_history(
    case_id: str, history_kind: str, request: Request, limit: int = 25, offset: int = 0
):
    if history_kind not in {"messages", "events", "attempts"}:
        raise DomainError("not_found", "History endpoint not found.", 404)
    return service(request).history(None, case_id, history_kind, limit, offset)
