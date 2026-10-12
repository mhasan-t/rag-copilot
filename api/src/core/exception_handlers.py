from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from src.core.exceptions import AppError
from src.core.logging import logger


def _error_response(
    status_code: int, code: str, message: str, details: Any = None, headers: dict[str, str] | None = None
) -> JSONResponse:
    """Every error response has the shape {"error": {"code", "message", "details"}}."""
    content = {"error": {"code": code, "message": message, "details": details}}
    return JSONResponse(status_code=status_code, content=jsonable_encoder(content), headers=headers)


async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    log = logger.error if exc.status_code >= 500 else logger.warning
    log(
        exc.message,
        extra={"error_code": exc.code, "details": exc.details, "method": request.method, "path": request.url.path},
    )
    return _error_response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)


async def _handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    logger.warning(exc.detail, extra={"status_code": exc.status_code, "path": request.url.path})
    return _error_response(exc.status_code, "http_error", str(exc.detail))


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning("request validation failed", extra={"path": request.url.path, "errors": exc.errors()})
    return _error_response(422, "validation_error", "Request validation failed", exc.errors())


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled error", exc_info=exc, extra={"method": request.method, "path": request.url.path})
    return _error_response(500, "internal_error", "Internal server error")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(HTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
