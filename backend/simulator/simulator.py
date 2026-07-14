# 7.3 IoT 시뮬레이터 (부하 생성)
# Entry Point — Frontend가 호출하는 Simulator API 서버. Traffic Engine은 services/에 있다.
import asyncio
import os
from contextlib import asynccontextmanager

os.environ.setdefault("SERVICE_NAME", "simulator")

from fastapi import FastAPI

from common.core.cors import register_cors
from common.core.exception_handlers import register_exception_handlers
from common.core.logger import configure_logging, get_logger

from config import get_settings
from dependencies import get_simulator_service, get_status_scheduler
from routers.simulator_router import router as simulator_router

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger("simulator")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "simulator started",
        extra={"event": "startup", "detail": {"call_api": settings.call_api_url}},
    )
    status_scheduler = get_status_scheduler()
    status_task = asyncio.create_task(status_scheduler.run_loop(), name="status-scheduler")
    yield
    status_scheduler.stop()
    status_task.cancel()
    # Pod 종료 시 Generator를 안전하게 정리
    await get_simulator_service().shutdown()


app = FastAPI(title="HailCast Simulator", version="0.1.0", lifespan=lifespan)
register_cors(app, settings.cors_allow_origins)
register_exception_handlers(app)
app.include_router(simulator_router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
