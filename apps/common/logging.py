import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

OBSERVABILITY_LOGGER_NAME = "tsms.observability"


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in _STANDARD_LOG_RECORD_KEYS:
                continue
            payload[key] = _json_safe(value)
        return json.dumps(payload, sort_keys=True)


def log_auth_failure(
    *,
    code: str,
    message: str,
    status: int,
    actor_email: str | None = None,
    path: str | None = None,
) -> None:
    logging.getLogger(OBSERVABILITY_LOGGER_NAME).warning(
        "auth_failure",
        extra={
            "event": "auth_failure",
            "code": code,
            "status": status,
            "actor_email": actor_email or "",
            "path": path or "",
            "failure_message": message,
        },
    )


def log_workflow_conflict(
    *,
    code: str,
    message: str,
    actor_email: str,
    entity_name: str,
    entity_id: int | None = None,
) -> None:
    logging.getLogger(OBSERVABILITY_LOGGER_NAME).warning(
        "workflow_conflict",
        extra={
            "event": "workflow_conflict",
            "code": code,
            "actor_email": actor_email,
            "entity_name": entity_name,
            "entity_id": entity_id,
            "failure_message": message,
        },
    )


def log_report_export(
    *,
    report_code: str,
    actor_email: str,
    row_count: int,
    filters: str,
    channel: str,
) -> None:
    logging.getLogger(OBSERVABILITY_LOGGER_NAME).info(
        "report_export",
        extra={
            "event": "report_export",
            "report_code": report_code,
            "actor_email": actor_email,
            "row_count": row_count,
            "filters": filters,
            "channel": channel,
        },
    )


def _json_safe(value: object) -> object:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


_STANDARD_LOG_RECORD_KEYS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}
