# 상태 조회 DTO — Simulator Status API 응답 (향후 Dashboard에서도 재사용)
from datetime import datetime

from pydantic import BaseModel


class SimulatorStatus(BaseModel):
    """GET /simulator/status 응답 — Frontend 폴링용."""

    running: bool
    status: str                     # IDLE | RUNNING | STOPPING
    traffic_mode: str               # CONSTANT (향후 SCENARIO/BURST/PEAK 추가)
    current_tps: float
    task_id: str | None = None

    # 통계
    generated_requests: int
    success: int
    fail: int
    queue_publish: int              # Call API가 202(큐 적재 성공)를 반환한 수
    average_tps: float
    uptime_seconds: float
    started_at: datetime | None = None
    last_request_at: datetime | None = None
