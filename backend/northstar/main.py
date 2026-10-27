"""Application assembly and ownership of database resources."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException

from northstar.cases.api import admin_router as cases_admin_router
from northstar.cases.api import router as cases_router
from northstar.config import Settings, load_settings
from northstar.db import make_engine, session_factory
from northstar.domain import DomainError
from northstar.errors import domain_error, http_error, invalid_request
from northstar.logging import configure_logging
from northstar.middleware import correlate
from northstar.retrieval.api import router as knowledge_router
from northstar.retrieval.search_api import router as retrieval_router
from northstar.system import expected_revision
from northstar.system import router as system_router


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
    app.state.schema_head = schema_head
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
    app.middleware("http")(correlate)
    app.add_exception_handler(RequestValidationError, invalid_request)
    app.add_exception_handler(HTTPException, http_error)
    app.add_exception_handler(DomainError, domain_error)
    app.include_router(system_router)
    app.include_router(cases_router)
    app.include_router(cases_admin_router)
    app.include_router(knowledge_router)
    app.include_router(retrieval_router)
    return app
