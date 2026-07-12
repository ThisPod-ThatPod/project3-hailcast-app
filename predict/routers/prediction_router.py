# Prediction Router — Frontend/Dashboard/Grafana 조회용. 위임만 수행.
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from common.models.prediction import PredictionDocument, PredictionItem, PredictionStatusResponse

from config import get_settings
from dependencies import get_db_session, get_forecast_scheduler
from repositories.prediction_repository import PredictionRepository

router = APIRouter(prefix="/prediction", tags=["prediction"])


@router.get("/latest", response_model=PredictionDocument)
def latest(session: Session = Depends(get_db_session)) -> PredictionDocument:
    repo = PredictionRepository(session)
    generated_at = repo.latest_generated_at()
    if generated_at is None:
        raise HTTPException(status_code=404, detail="no prediction generated yet")
    batch = repo.get_batch(generated_at)
    first_target = min(p.target_time for p in batch)
    return PredictionDocument(
        generated_at=generated_at,
        model_version=batch[0].model_version,
        prediction_window_minutes=batch[0].prediction_window_minutes,
        horizon_steps=len({p.target_time for p in batch}),
        total_predicted_demand=round(
            sum(p.predicted_demand for p in batch if p.target_time == first_target), 2
        ),
        predictions=[
            PredictionItem(
                target_time=p.target_time,
                predicted_demand=p.predicted_demand,
                confidence=p.confidence,
            )
            for p in batch
        ],
    )


@router.get("/history", response_model=list[PredictionItem])
def history(
    limit: int = Query(default=None, ge=1),
    session: Session = Depends(get_db_session),
) -> list[PredictionItem]:
    settings = get_settings()
    rows = PredictionRepository(session).get_history(
        limit=min(limit or settings.prediction_history_default_limit, settings.prediction_history_max_limit),
    )
    return [
        PredictionItem(
            target_time=p.target_time,
            predicted_demand=p.predicted_demand,
            confidence=p.confidence,
        )
        for p in rows
    ]


@router.get("/status", response_model=PredictionStatusResponse)
def status(session: Session = Depends(get_db_session)) -> PredictionStatusResponse:
    scheduler = get_forecast_scheduler()
    total, model_version = PredictionRepository(session).stats()
    return PredictionStatusResponse(
        scheduler_running=scheduler.is_running,
        interval_seconds=scheduler.interval_seconds,
        model_version=model_version,
        latest_generated_at=PredictionRepository(session).latest_generated_at(),
        total_predictions_stored=total,
        last_run_at=scheduler.last_run_at,
        last_success_at=scheduler.last_success_at,
        last_error=scheduler.last_error,
        run_count=scheduler.run_count,
        failure_count=scheduler.failure_count,
    )
