# Health Router — K8s Probe 및 모니터링용 (health / ready / live)
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from common.models.dashboard import HealthResponse

from dependencies import get_health_service

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return get_health_service().health()


@router.get("/ready")
def ready() -> JSONResponse:
    ok, checks = get_health_service().ready()
    return JSONResponse(status_code=200 if ok else 503, content={"ready": ok, "checks": checks})


@router.get("/live")
def live() -> dict:
    # 이 핸들러가 응답한다는 것 자체가 이벤트 루프 생존의 증거
    return {"live": True}
