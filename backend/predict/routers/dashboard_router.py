# Dashboard Router — Frontend 통합 상태 조회. 위임만 수행.
#
# /dashboard/traffic, /prediction, /weather, /scaling, /worker는 DB 기반 구현이었고
# 프론트에서 쓰는 곳이 없어(H 재설계 시 확인) 복원하지 않음 — 필요해지면 각자
# /prediction/status, /scaling/status에 이미 있는 걸 프론트가 직접 부르면 된다.
from fastapi import APIRouter, Depends, Query

from common.models.dashboard import DashboardStats, PodForecastPoint, TrafficPoint

from dependencies import get_dashboard_service, get_pod_forecast_service
from services.dashboard_service import DashboardService
from services.pod_forecast_service import PodForecastService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardStats)
def summary(service: DashboardService = Depends(get_dashboard_service)) -> DashboardStats:
    return service.stats()


@router.get("/traffic-history", response_model=list[TrafficPoint])
def traffic_history(
    minutes: int = Query(default=10, ge=1, le=180),
    bucket_seconds: int = Query(default=10, ge=1, le=3600),
    service: DashboardService = Depends(get_dashboard_service),
) -> list[TrafficPoint]:
    return service.traffic_history(minutes, bucket_seconds)


@router.get("/pod-forecast", response_model=list[PodForecastPoint])
def pod_forecast(
    hours_history: int = Query(default=24, ge=0, le=168),
    hours_forecast: int = Query(default=4, ge=0, le=24),
    service: PodForecastService = Depends(get_pod_forecast_service),
) -> list[PodForecastPoint]:
    return service.pod_forecast(hours_history, hours_forecast)
