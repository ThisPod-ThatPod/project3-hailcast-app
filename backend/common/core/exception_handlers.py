# FastAPI 공통 Exception Handler — 모든 API 서비스(app.py)에서 register_exception_handlers(app) 1회 호출
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from common.core.exceptions import AppError
from common.core.logger import get_logger

logger = get_logger("exception")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        # 지시서: 잘못된 요청은 Service에 도달하기 전에 즉시 400
        return JSONResponse(
            status_code=400,
            content={"error": "VALIDATION_ERROR", "detail": exc.errors()},
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        logger.error(
            exc.message,
            extra={"event": "app_error", "detail": {"code": exc.code, **exc.detail}},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        logger.exception("unhandled error", extra={"event": "unhandled_error"})
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_ERROR", "message": "internal server error"},
        )
