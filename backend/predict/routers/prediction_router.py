# Prediction Router — Dashboard/Grafana 조회용. 위임만 수행.
from fastapi import APIRouter, HTTPException

from common.models.prediction import PredictionDocument, PredictionStatusResponse

from config import get_settings
from dependencies import get_file_store, get_forecast_scheduler

router = APIRouter(prefix="/prediction", tags=["prediction"])


@router.get("/latest", response_model=PredictionDocument)
def latest() -> PredictionDocument:
    settings = get_settings()
    body = get_file_store().read_json(f"{settings.prediction_s3_prefix}/latest.json")
    if body is None:
        raise HTTPException(status_code=404, detail="no prediction generated yet")
    return PredictionDocument.model_validate(body)


@router.get("/status", response_model=PredictionStatusResponse)
def status() -> PredictionStatusResponse:
    scheduler = get_forecast_scheduler()
    settings = get_settings()
    body = get_file_store().read_json(f"{settings.prediction_s3_prefix}/latest.json")
    document = PredictionDocument.model_validate(body) if body else None
    return PredictionStatusResponse(
        scheduler_running=scheduler.is_running,
        interval_seconds=scheduler.interval_seconds,
        model_version=document.model_version if document else None,
        latest_generated_at=document.generated_at if document else None,
        total_predictions_stored=len(document.predictions) if document else 0,
        last_run_at=scheduler.last_run_at,
        last_success_at=scheduler.last_success_at,
        last_error=scheduler.last_error,
        run_count=scheduler.run_count,
        failure_count=scheduler.failure_count,
    )
