# 8.3 예측 서비스 (FastAPI + /metrics)
# Entry Point — Forecast Scheduler(백그라운드) + Prediction 조회 API + /metrics
import asyncio
import os
from contextlib import asynccontextmanager

os.environ.setdefault("SERVICE_NAME", "predict")

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from common.core.cors import register_cors
from common.core.exception_handlers import register_exception_handlers
from common.core.logger import configure_logging, get_logger
from common.core.metrics import metrics

from config import get_settings
from dependencies import (
    get_backup_scheduler,
    get_forecast_scheduler,
    get_scaling_scheduler,
    get_traffic_scheduler,
)
from routers.dashboard_router import router as dashboard_router
from routers.health_router import router as health_router
from routers.prediction_router import router as prediction_router
from routers.scaling_router import router as scaling_router

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger("predict")


@asynccontextmanager
async def lifespan(app: FastAPI):
    schedulers = [
        get_forecast_scheduler(),
        get_scaling_scheduler(),
        get_backup_scheduler(),
        get_traffic_scheduler(),
    ]
    tasks = [
        asyncio.create_task(s.run_loop(), name=s.name) for s in schedulers
    ]
    logger.info(
        "predict started",
        extra={
            "event": "startup",
            "detail": {
                "prediction_interval": settings.prediction_interval_seconds,
                "scaling_interval": settings.scaling_interval_seconds,
                "keda_enabled": settings.keda_enabled,
            },
        },
    )
    yield
    for scheduler in schedulers:
        scheduler.stop()
    for task in tasks:
        task.cancel()


app = FastAPI(title="HailCast Predict", version="0.1.0", lifespan=lifespan)
register_cors(app, settings.cors_allow_origins)
register_exception_handlers(app)
app.include_router(prediction_router)
app.include_router(scaling_router)
app.include_router(dashboard_router)
app.include_router(health_router)


@app.get("/metrics", response_class=PlainTextResponse)
def metrics_endpoint() -> str:
    """Prometheus 노출 Stub — 인메모리 지표를 text exposition 형식으로 출력.

    향후 prometheus_client로 교체 시에도 경로(/metrics)와 지표 이름은 유지된다.
    """
    snapshot = metrics.snapshot()
    lines = []
    for name, value in snapshot["counters"].items():
        lines.append(f"# TYPE hailcast_{name} counter")
        lines.append(f"hailcast_{name} {value}")
    for name, summary in snapshot["observations"].items():
        lines.append(f"# TYPE hailcast_{name} gauge")
        lines.append(f"hailcast_{name}_avg {summary['avg']}")
        lines.append(f"hailcast_{name}_count {summary['count']}")
    # 실시간 게이지 (best-effort — 수집 실패해도 /metrics는 응답한다)
    try:
        from dependencies import get_sqs_adapter

        backlog = int(
            get_sqs_adapter().queue_attributes().get("ApproximateNumberOfMessages", 0)
        )
        lines.append("# TYPE hailcast_queue_size gauge")
        lines.append(f"hailcast_queue_size {backlog}")
    except Exception:
        pass
    return "\n".join(lines) + "\n"


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
