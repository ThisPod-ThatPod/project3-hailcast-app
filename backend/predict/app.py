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
    get_database,
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
    get_database().init_schema()
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

# 경로 규칙(7/23 「나」안) — 프론트가 부르는 API 는 /api 아래로 모은다.
# 짝 매니페스트: manifests 브랜치 feature/predict-frontend-ingress-routing 의
# apps/predict/ingress.yaml — /api/dashboard/*, /api/scaling/*, /api/prediction/* 를 predict 로
# 보낸다. group.order 10 이라 call-api 의 /api/* catch-all(order 20)보다 먼저 평가된다.
# 이 세 접두어가 그 Ingress 의 세 규칙과 1:1 로 맞아야 한다 — 여기를 바꾸면 Ingress 도 같이.
app.include_router(prediction_router, prefix="/api")
app.include_router(scaling_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")

# health_router(/health·/ready·/live)·/metrics·/healthz 는 루트에 남긴다.
# 위 Ingress 가 예약한 건 /api/dashboard·scaling·prediction 뿐이라 이들은 ALB 리스너를 안 탄다:
#   - /healthz : Ingress 의 healthcheck-path 가 타깃그룹에 직접 (리스너 규칙 아님)
#   - /metrics : ServiceMonitor 가 파드를 직접 스크레이프
#   - /health·/ready·/live : k8s Probe·compose healthcheck 가 파드로 직접
# /api 아래로 넣으면 call-api 의 /api/* catch-all 로 잘못 흘러간다.
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


# Probe 전용 — 루트 유지. k8s Probe 와 ALB healthcheck-path 가 이 경로를 본다.
# (/metrics 도 ServiceMonitor 가 파드를 직접 긁으므로 ALB 를 안 타고 루트 그대로다)
@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
