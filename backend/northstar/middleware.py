"""Request correlation, timing and the unexpected-error boundary."""

import logging
from time import perf_counter
from uuid import uuid4

from fastapi import Request

from northstar.errors import error

logger = logging.getLogger("northstar")


async def correlate(request: Request, call_next):
    request.state.request_id = str(uuid4())
    start = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed",
            extra={"request_id": request.state.request_id, "error_category": "internal_error"},
        )
        response = error(request, 500, "internal_error", "The request could not be completed.")
    response.headers["X-Request-ID"] = request.state.request_id
    logger.info(
        "request_completed",
        extra={
            "request_id": request.state.request_id,
            "method": request.method,
            "status": response.status_code,
            "duration_ms": round((perf_counter() - start) * 1000, 2),
        },
    )
    return response
