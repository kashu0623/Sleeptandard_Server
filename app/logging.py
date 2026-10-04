import json
import logging
import re
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import Settings


request_id_context: ContextVar[str | None] = ContextVar(
    "request_id",
    default=None,
)

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_STRUCTURED_FIELDS = {
    "method",
    "route",
    "status_code",
    "duration_ms",
    "error_code",
    "retryable",
    "user_id",
    "device_id",
    "sleep_session_id",
    "upload_id",
    "upload_status",
    "attempt_count",
    "size_bytes",
    "uploaded_bytes",
    "part_number",
    "duration_sec",
}


class JsonLogFormatter(logging.Formatter):
    def __init__(self, *, service: str, environment: str) -> None:
        super().__init__()
        self.service = service
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service,
            "environment": self.environment,
            "logger": record.name,
            "event": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or request_id_context.get()
        if request_id is not None:
            payload["request_id"] = request_id
        for field in _STRUCTURED_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonLogFormatter(
            service=settings.log_service_name,
            environment=settings.app_env,
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    for logger_name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True


def _request_id(value: str | None) -> str:
    if value is not None and _REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return str(uuid.uuid4())


def _route(scope: Scope) -> str:
    route = scope.get("route")
    return getattr(route, "path", scope.get("path", "unknown"))


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp, *, log_health_requests: bool = False) -> None:
        self.app = app
        self.log_health_requests = log_health_requests
        self.logger = logging.getLogger("sleeptandard.request")

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        supplied_request_id = headers.get(b"x-request-id")
        request_id = _request_id(
            supplied_request_id.decode("ascii", errors="ignore")
            if supplied_request_id is not None
            else None
        )
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_context.set(request_id)
        started_at = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal response_started, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            self.logger.exception(
                "request.unhandled_error",
                extra={
                    "method": scope.get("method"),
                    "route": _route(scope),
                    "status_code": 500,
                    "duration_ms": duration_ms,
                },
            )
            if response_started:
                raise
            response = JSONResponse(
                status_code=500,
                content={
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "Internal server error",
                },
                headers={"X-Request-ID": request_id},
            )
            await response(scope, receive, send)
            status_code = 500
        finally:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            path = scope.get("path", "")
            should_log = self.log_health_requests or path not in {"/health", "/health/db"}
            if should_log or status_code >= 400:
                level = (
                    logging.ERROR
                    if status_code >= 500
                    else logging.WARNING
                    if status_code >= 400
                    else logging.INFO
                )
                self.logger.log(
                    level,
                    "request.completed",
                    extra={
                        "method": scope.get("method"),
                        "route": _route(scope),
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                    },
                )
            request_id_context.reset(token)
