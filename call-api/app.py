# 7.1 콜 처리 API (FastAPI)
# Entry Point — 라우터/예외 핸들러/DI 조립만 담당. Business Logic은 services/에 있다.
import os

# common 패키지 로거가 서비스명을 읽을 수 있도록 우선 설정
os.environ.setdefault("SERVICE_NAME", "call-api")

from fastapi import FastAPI

from common.core.exception_handlers import register_exception_handlers
from common.core.logger import configure_logging, get_logger

from config import get_settings
from dependencies import get_database
from routers.call_router import router as call_router

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger("call_api")

app = FastAPI(title="HailCast Call API", version="0.1.0")
register_exception_handlers(app)
app.include_router(call_router)


@app.on_event("startup")
def on_startup() -> None:
    # 상태 조회(GET /call/{id})가 참조하는 테이블 보장 (create_all은 idempotent)
    get_database().init_schema()
    logger.info(
        "call-api started",
        extra={"event": "startup", "queue": settings.sqs_queue_name},
    )
