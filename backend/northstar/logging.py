import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record):
        # Deliberately whitelist fields; never serialize request bodies, headers,
        # arbitrary exception messages, or database URLs into public logs.
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for field in ("request_id", "method", "status", "duration_ms", "error_category"):
            if hasattr(record, field):
                entry[field] = getattr(record, field)
        return json.dumps(entry)


def configure_logging(level: str):
    logger = logging.getLogger("northstar")
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
