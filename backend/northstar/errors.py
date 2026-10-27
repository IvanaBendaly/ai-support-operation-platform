"""Shared API error responses and framework exception handlers."""

from uuid import uuid4

from fastapi.responses import JSONResponse


def error(request, status, code, message, details=None):
    request_id = getattr(request.state, "request_id", str(uuid4()))
    return JSONResponse(
        status_code=status,
        headers={"X-Request-ID": request_id},
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
                "details": details or [],
            }
        },
    )


async def invalid_request(request, exc):
    return error(
        request,
        422,
        "validation_error",
        "Check the submitted fields.",
        [{"field": ".".join(map(str, e["loc"])), "type": e["type"]} for e in exc.errors()],
    )


async def http_error(request, exc):
    return error(request, exc.status_code, "http_error", str(exc.detail))


async def domain_error(request, exc):
    return error(request, exc.status, exc.code, str(exc))
