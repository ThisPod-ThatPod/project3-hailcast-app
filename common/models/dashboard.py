# Dashboard DTO — Frontend 통합 상태 조회 응답
from datetime import datetime

from pydantic import BaseModel


class TrafficStatus(BaseModel):
    """GET /dashboard/traffic — Simulator 상태 (Simulator API 프록시)."""

    available: bool                      # Simulator 서비스 도달 가능 여부
    running: bool | None = None
    current_tps: float | None = None
    generated_requests: int | None = None
    success: int | None = None
    fail: int | None = None
    uptime_seconds: float | None = None


class PredictionSummary(BaseModel):
    """GET /dashboard/prediction — 최신 예측 요약."""

    available: bool
    total_predicted_demand: float | None = None
    generated_at: datetime | None = None
    model_version: str | None = None
    prediction_window_minutes: int | None = None
    horizon_steps: int | None = None


class WeatherSummary(BaseModel):
    """GET /dashboard/weather — 현재 날씨 요약."""

    available: bool
    latest_observed_at: datetime | None = None
    zones: int = 0
    avg_temperature_c: float | None = None
    avg_humidity_pct: float | None = None
    raining_zones: int = 0


class ScalingSummary(BaseModel):
    """GET /dashboard/scaling — 현재 replica·최근 스케일링."""

    current_replicas: int | None = None
    keda_enabled: bool
    last_action: str | None = None
    last_predicted_demand: float | None = None
    last_scaling_at: datetime | None = None
    cooldown_remaining_seconds: float = 0.0


class WorkerStatus(BaseModel):
    """GET /dashboard/worker — Worker 처리량·Queue 상태."""

    queue_backlog: int | None = None          # ApproximateNumberOfMessages
    queue_in_flight: int | None = None        # NotVisible
    processed_total: int = 0                  # DONE 누적
    processed_last_5min: int = 0
    failed_total: int = 0
    avg_process_latency_ms: float | None = None   # enqueued→processed 평균 (최근 5분)


class TrafficPoint(BaseModel):
    """GET /dashboard/traffic-history — 시간 버킷별 call-api 수신 요청 수 1개 점.

    Call.enqueued_at(= call-api가 접수해 SQS에 발행한 시각) 기준 집계라 call-api/worker
    파드가 몇 개든, 트래픽이 simulator든 k6든 출처와 무관하게 DB에서 그대로 잡힌다.
    """

    timestamp: datetime
    requests: int


class PodForecastPoint(BaseModel):
    """GET /dashboard/pod-forecast — 시간대별 예측 파드 수 vs 실제 파드 수 1개 점.

    과거(bucket_time < 현재 정시)는 PodReplicaHistory 백업 이력에서, 현재·미래는
    실시간 예측 파일(S3 predictions/latest.json)에서 값을 채운다. actual은 과거·현재만
    존재하고 미래는 항상 None이다.
    """

    timestamp: datetime
    predicted: int | None = None
    actual: int | None = None


class DashboardSummary(BaseModel):
    """GET /dashboard/summary — 시스템 전체 상태."""

    timestamp: datetime
    health: str                               # healthy | warning | unhealthy
    traffic: TrafficStatus
    prediction: PredictionSummary
    weather: WeatherSummary
    scaling: ScalingSummary
    worker: WorkerStatus
    total_calls: int


class ComponentHealth(BaseModel):
    name: str
    status: str                               # healthy | warning | unhealthy
    detail: str | None = None


class HealthResponse(BaseModel):
    """GET /health — 컴포넌트별 상태."""

    status: str                               # 전체 = 컴포넌트 중 최악
    components: list[ComponentHealth]
    checked_at: datetime
