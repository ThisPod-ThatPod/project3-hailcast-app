# Prediction DTO — prediction.json 스키마와 조회 API 응답. KEDA/Dashboard/Grafana 공용.
from datetime import datetime

from pydantic import BaseModel, Field


class PredictionItem(BaseModel):
    """시간창 1건의 예측 (zone 없음 — 뉴욕 날씨 기반 글로벌 수요 하나)."""

    target_time: datetime           # 이 시각부터 window 동안의 수요 예측
    predicted_demand: float = Field(..., ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)


class PredictionDocument(BaseModel):
    """prediction.json 스키마 — S3 predictions/latest.json 으로 업로드된다.

    KEDA는 predicted_taxi_demand(스칼라)를, Dashboard/Grafana는 predictions(상세)를 사용한다.
    """

    generated_at: datetime
    model_version: str
    prediction_window_minutes: int
    horizon_steps: int              # 몇 개의 시간창을 예측했는지
    # 07-13 네이밍 규약에 따른 변수명 및 코드 수정 중 1. 예측 지표 이름 불일치
    # total_predicted_demand: float   # 첫 번째 시간창의 예측값 (KEDA 스케일 기준값)
    predicted_taxi_demand: float    # 첫 번째 시간창의 예측값 (KEDA 스케일 기준값)
    predictions: list[PredictionItem]


class PredictionStatusResponse(BaseModel):
    """GET /prediction/status — Dashboard용 파이프라인 상태."""

    scheduler_running: bool
    interval_seconds: float
    model_version: str | None = None
    latest_generated_at: datetime | None = None
    total_predictions_stored: int
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    run_count: int
    failure_count: int
