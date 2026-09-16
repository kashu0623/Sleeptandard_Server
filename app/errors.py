from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        **extra: Any,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.extra = extra


def error_response(status_code: int, code: str, message: str, **extra: Any) -> JSONResponse:
    content: dict[str, Any] = {"code": code, "message": message}
    content.update(extra)
    return JSONResponse(status_code=status_code, content=content)


def raise_app_error(status_code: int, code: str, message: str, **extra: Any) -> None:
    raise AppError(status_code=status_code, code=code, message=message, **extra)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, **exc.extra)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_ERROR",
            "Request validation failed",
            errors=exc.errors(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        message = str(exc.detail) if exc.detail else "HTTP error"
        return error_response(exc.status_code, "HTTP_ERROR", message)
