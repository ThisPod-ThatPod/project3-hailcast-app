# Dashboard Router — Frontend 통합 상태 조회. 위임만 수행.
from fastapi import APIRouter, Depends

from common.models.dashboard import (
    DashboardSummary,
    PredictionSummary,
    ScalingSummary,
    TrafficStatus,
    WeatherSummary,
    WorkerStatus,
)

from dependencies import get_dashboard_service, get_health_service
from services.dashboard_service import DashboardService

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
