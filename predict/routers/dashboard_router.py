# Dashboard Router — Frontend 통합 상태 조회. 위임만 수행.
from fastapi import APIRouter, Depends, Query

from common.models.dashboard import (
    DashboardSummary,
    PodForecastPoint,
    PredictionSummary,
    ScalingSummary,
    TrafficPoint,
    TrafficStatus,
    WeatherSummary,
    WorkerStatus,
)

from dependencies import get_dashboard_service, get_health_service, get_pod_forecast_service
from services.dashboard_service import DashboardService
from services.pod_forecast_service import PodForecastService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def summary(service: DashboardService = Depends(get_dashboard_service)) -> DashboardSummary:
    overall = get_health_service().health().status
    return service.summary(overall)


@router.get("/traffic", response_model=TrafficStatus)
def traffic(service: DashboardService = Depends(get_dashboard_service)) -> TrafficStatus:
    return service.traffic()


@router.get("/prediction", response_model=PredictionSummary)
def prediction(service: DashboardService = Depends(get_dashboard_service)) -> PredictionSummary:
    return service.prediction()


@router.get("/weather", response_model=WeatherSummary)
def weather(service: DashboardService = Depends(get_dashboard_service)) -> WeatherSummary:
    return service.weather()


@router.get("/scaling", response_model=ScalingSummary)
def scaling(service: DashboardService = Depends(get_dashboard_service)) -> ScalingSummary:
    return service.scaling()


@router.get("/worker", response_model=WorkerStatus)
def worker(service: DashboardService = Depends(get_dashboard_service)) -> WorkerStatus:
    return service.worker()


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
    hours_forecast: int = Query(default=5, ge=0, le=24),
    service: PodForecastService = Depends(get_pod_forecast_service),
) -> list[PodForecastPoint]:
    return service.pod_forecast(hours_history, hours_forecast)
