import logging
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from northstar.config import Settings, load_settings
from northstar.db import make_engine, session_factory
from northstar.logging import configure_logging


def expected_revision():
    config = Config()
    config.set_main_option("script_location", "northstar:migrations")
    return ScriptDirectory.from_config(config).get_current_head()


def create_app(settings: Settings | None = None, engine=None):
    settings = settings or load_settings()
    schema_head = expected_revision()
    configure_logging(settings.log_level)
    owns_engine = engine is None
    engine = engine or make_engine(settings)

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if owns_engine:
                engine.dispose()

    app = FastAPI(title="Northstar Cloud Support Operations", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = session_factory(engine)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "Idempotency-Key"],
        expose_headers=["X-Request-ID"],
    )
    logger = logging.getLogger("northstar")

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

    @app.middleware("http")
    async def correlate(request: Request, call_next):
        request.state.request_id = str(uuid4())
        start = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.error(
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

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return error(
            request,
            422,
            "validation_error",
            "Check the submitted fields.",
            [{"field": ".".join(map(str, e["loc"])), "type": e["type"]} for e in exc.errors()],
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(request, exc.status_code, "http_error", str(exc.detail))

    @app.get("/api/health", tags=["System"])
    def health():
        return {
            "status": "alive",
            "service": "northstar-support",
            "version": app.version,
            "environment": settings.environment,
        }

    @app.get("/api/ready", tags=["System"], responses={503: {"description": "Not ready"}})
    def ready(request: Request):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                revisions = (
                    connection.execute(text("SELECT version_num FROM alembic_version"))
                    .scalars()
                    .all()
                )
                if revisions != [schema_head]:
                    return error(
                        request, 503, "schema_not_ready", "Database migrations are required."
                    )
        except SQLAlchemyError:
            return error(request, 503, "database_not_ready", "Database or schema is unavailable.")
        return {
            "status": "ready",
            "database": "connected",
            "schema": schema_head,
            "environment": settings.environment,
            "version": app.version,
        }

    return app
