# ECR Push 및 이미지 태그 자동 푸시 확인을 위해
# 임의로 추가한 주석입니다.
# 추후 삭제하셔도 상관 없습니다.
# 07-23 테스트용 추가 주석입니다.

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
from dependencies import get_database, get_traffic_flush_scheduler
from routers.call_router import router as call_router

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger("call_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_database().init_schema()
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

# 경로 규칙(7/23 「나」안) — 외부에 노출되는 API 는 전부 /api 아래로 모은다.
# 짝 매니페스트: manifests 브랜치 feature/predict-frontend-ingress-routing
#   - apps/call-api/ingress.yaml : path /api/*   (group.order 20, catch-all)  → 이 서비스
#   - apps/predict/ingress.yaml  : /api/dashboard·scaling·prediction (order 10) → predict
# call-api 는 catch-all 이라, 예약 경로(predict 3개)에 안 걸린 /api/* 를 전부 받는다.
# 접두어를 여기서 한 번에 붙이므로 라우터 파일은 서비스 경로만 알면 된다.
# ⚠️ 배포 순서: 이 접두어 이동이 담긴 이미지가 배포되기 전에 위 Ingress 만 먼저 sync 되면
#    앱이 아직 /api 를 몰라 모든 /api/* 가 404 다. 앱 이미지 태그 갱신 → 그 뒤 Ingress sync.
app.include_router(call_router, prefix="/api")


# Probe 전용 — 라우터 밖(루트)에 둔다. k8s Probe 와 Ingress 의 healthcheck-path(/healthz)가
# 둘 다 루트를 본다. /api 아래로 들어가면(=/api/healthz) probe 가 404 → 파드 CrashLoop.
@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
