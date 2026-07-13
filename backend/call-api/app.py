# 7.1 콜 처리 API (FastAPI)
# Entry Point — 라우터/예외 핸들러/DI 조립만 담당. Business Logic은 services/에 있다.
import asyncio
import os
from contextlib import asynccontextmanager

# common 패키지 로거가 서비스명을 읽을 수 있도록 우선 설정
os.environ.setdefault("SERVICE_NAME", "call-api")

from fastapi import FastAPI

from common.core.cors import register_cors
from common.core.exception_handlers import register_exception_handlers
from common.core.logger import configure_logging, get_logger

from config import get_settings
from dependencies import get_traffic_flush_scheduler
from routers.call_router import router as call_router

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger("call_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = get_traffic_flush_scheduler()
    task = asyncio.create_task(scheduler.run_loop(), name="traffic-flush-scheduler")
    logger.info(
        "call-api started",
        extra={"event": "startup", "queue": settings.sqs_queue_name},
    )
    yield
    scheduler.stop()
    task.cancel()


app = FastAPI(title="HailCast Call API", version="0.1.0", lifespan=lifespan)
register_cors(app, settings.cors_allow_origins)
register_exception_handlers(app)
app.include_router(call_router)
