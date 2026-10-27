"""Process liveness and database/schema readiness."""

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from northstar.errors import error

router = APIRouter()


def expected_revision():
    config = Config()
    config.set_main_option("script_location", "northstar:migrations")
    return ScriptDirectory.from_config(config).get_current_head()


@router.get("/api/health", tags=["System"])
def health(request: Request):
    return {
        "status": "alive",
        "service": "northstar-support",
        "version": request.app.version,
        "environment": request.app.state.settings.environment,
    }


@router.get("/api/ready", tags=["System"], responses={503: {"description": "Not ready"}})
def ready(request: Request):
    schema_head = request.app.state.schema_head
    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            revisions = (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
            )
            if revisions != [schema_head]:
                return error(request, 503, "schema_not_ready", "Database migrations are required.")
    except SQLAlchemyError:
        return error(request, 503, "database_not_ready", "Database or schema is unavailable.")
    return {
        "status": "ready",
        "database": "connected",
        "schema": schema_head,
        "environment": request.app.state.settings.environment,
        "version": request.app.version,
    }
