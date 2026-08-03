# 7.3 IoT 시뮬레이터 (부하 생성)
# Entry Point — Frontend가 호출하는 Simulator API 서버. Traffic Engine은 services/에 있다.
import asyncio
import os
from contextlib import asynccontextmanager

os.environ.setdefault("SERVICE_NAME", "simulator")

from fastapi import Depends, FastAPI, Request, Response

from common.core.cors import register_cors
from common.core.exception_handlers import register_exception_handlers
from common.core.logger import configure_logging, get_logger

from config import get_settings
from dependencies import get_simulator_service, get_status_scheduler
from routers.simulator_router import router as simulator_router
from services.simulator_service import SimulatorService

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
# 경로 규칙(7/23 「나」안) — 프론트가 부르는 API 는 /api 아래로 모은다. 접두어를 여기서 붙인다.
# ⚠️ manifests 브랜치 feature/predict-frontend-ingress-routing 에는 simulator 규칙이 없다
#    (그 PR 범위는 predict + call-api, frontend/* 는 이후 별도 PR). 그래서 EKS 에서
#    /api/simulator/* 는 call-api 의 /api/* catch-all 로 들어가 call-api 404(JSON)로 떨어진다.
#    이는 「나」안이 의도한 실패 모드다 — 규칙이 없으면 프론트 HTML 이 아니라 읽히는 404 JSON 이 온다.
#    simulator 를 외부로 여는 규칙(①: 프론트 부하 버튼용)은 별도 매니페스트 작업으로 붙는다.
#    접두어를 지금 맞춰 두면 그 규칙이 붙는 순간 코드 변경 없이 그대로 동작한다.
app.include_router(simulator_router, prefix="/api")


# [B-1, 2026-07-24] k6(같은 파드의 서브프로세스) 전용 내부 엔드포인트 — 정식 6개 계약과 별개.
# ⚠️ 일부러 라우터(prefix="/api/simulator") 밖, 앱 루트에 둔다.
#    ①(simulator 외부 개방)로 매니페스트가 /api/simulator/* 를 열면 그 catch-all 에 _relay 까지
#    딸려 열린다 — 인증 없이 call-api→SQS 로 부하를 밀어넣는 입구가 외부에 뚫린다. 루트(/_relay)로
#    빼두면 어떤 /api/simulator/* 규칙에도 안 걸려 '구조적으로' 외부에서 도달할 수 없다(「나」안).
#    k6 는 같은 파드에서 localhost:8001/_relay 로만 부르므로 ALB 를 안 타 문제없다
#    (config.py::relay_url · k6/call_load.js::TARGET_URL 이 이 경로와 짝이다).
@app.post("/_relay", include_in_schema=False)
async def relay(request: Request, service: SimulatorService = Depends(get_simulator_service)) -> Response:
    body = await request.body()
    status_code, content = await service.relay_call(body)
    return Response(content=content, status_code=status_code, media_type="application/json")


# Probe 전용 — 루트 유지. k8s Probe 와 ALB healthcheck-path 가 이 경로를 본다.
@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
