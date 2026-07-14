# Scaling DTO — Decision Engine 입출력 및 Dashboard 조회 응답
from datetime import datetime

from pydantic import BaseModel, Field


class ScalingSignals(BaseModel):
    """Decision Engine 입력 — 향후 CPU/Queue Length/Memory/Worker Delay 등을 추가하는 확장 지점."""

    predicted_demand: float = Field(..., ge=0)
    # Future Extension (지시서 예약): 값이 채워지면 Decision Engine 규칙에서 함께 사용
    queue_length: float | None = None
    cpu_utilization: float | None = None
    memory_utilization: float | None = None
    worker_delay_seconds: float | None = None


class ScalingDecision(BaseModel):
    """Decision Engine 출력."""

    desired_replicas: int = Field(..., ge=0)
    matched_rule: str          # 어떤 규칙에 걸렸는지 (예: "demand<300 -> 5")
    reason: str


class ScalingHistoryItem(BaseModel):
    predicted_demand: float
    old_replica: int
    new_replica: int
    action: str                # SCALE_UP | SCALE_DOWN
    reason: str
    model_version: str | None = None
    created_at: datetime


class ScalingStatusResponse(BaseModel):
    """GET /scaling/status — Dashboard용."""

    scheduler_running: bool
    interval_seconds: float
    keda_enabled: bool
    scaledobject: str
    namespace: str
    current_replicas: int | None = None
    last_predicted_demand: float | None = None
    last_decision: str | None = None
    cooldown_seconds: float
    cooldown_remaining_seconds: float
    last_scaling_at: datetime | None = None
    last_run_at: datetime | None = None
    last_error: str | None = None
    run_count: int
    failure_count: int


class ScalingCurrentResponse(BaseModel):
    """GET /scaling/current — 현재 replica와 최근 예측값."""

    current_replicas: int
    predicted_demand: float | None = None
    desired_replicas: int | None = None
    generated_at: datetime | None = None
