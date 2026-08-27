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
from fastapi.responses import PlainTextResponse

from common.core.cors import register_cors
from common.core.exception_handlers import register_exception_handlers
from common.core.logger import configure_logging, get_logger
from common.core.metrics import metrics

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


# Prometheus 스크레이프 대상 — 라우터 밖(루트)에 둔다.
# /api 아래로 넣으면 call-api 의 /api/* catch-all Ingress 규칙을 타서 ALB 를 거치게 된다.
# ServiceMonitor 는 파드 IP 로 직접 긁으므로 ALB 를 안 타는 루트가 맞다(predict 와 동일 배치).
#
# predict/app.py 의 핸들러에서 counter 루프만 가져왔다. 나머지 두 블록을 뺀 이유:
#   · observations 루프 — call-api 에는 metrics.observe() 계측이 아예 없다(카운터 2종뿐).
#     빈 루프라 출력도 안 나오고, predict 쪽 TYPE 이름 불일치 버그를 옮겨올 필요도 없다.
#   · hailcast_queue_size 게이지 — call-api 에도 SQS 어댑터가 있어 그대로 동작해버린다.
#     predict 가 이미 내보내는 지표라 같은 큐를 두 서비스가 중복 보고하게 되고,
#     배포팀 알림이 참조 중인 hailcast_queue_size{service="predict"} 와 섞인다.
#
# 노출 지표(2종, 둘 다 call_service.accept_call 에서 증가):
#   hailcast_request_total        — 콜 접수량 (validation 통과 후 서비스 로직 진입 기준)
#   hailcast_queue_publish_total  — SQS 발행 성공량
# ⚠️ 카운터는 파드별이고 call-api 는 replicas 4 다. PromQL 에서 sum by(...) 로 합쳐야 한다.
@app.get("/metrics", response_class=PlainTextResponse)
def metrics_endpoint() -> str:
    """인메모리 Stub 지표를 Prometheus text exposition 형식으로 출력.

    향후 prometheus_client 로 교체하더라도 경로(/metrics)와 지표 이름은 유지한다.
    """
    snapshot = metrics.snapshot()
    lines = []
    for name, value in snapshot["counters"].items():
        lines.append(f"# TYPE hailcast_{name} counter")
        lines.append(f"hailcast_{name} {value}")
    return "\n".join(lines) + "\n"


# Probe 전용 — 라우터 밖(루트)에 둔다. k8s Probe 와 Ingress 의 healthcheck-path(/healthz)가
# 둘 다 루트를 본다. /api 아래로 들어가면(=/api/healthz) probe 가 404 → 파드 CrashLoop.
@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
