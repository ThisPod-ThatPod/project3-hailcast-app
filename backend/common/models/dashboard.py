# Dashboard DTO — Frontend 통합 상태 조회 응답
from datetime import datetime

from pydantic import BaseModel


class DashboardStats(BaseModel):
    """GET /dashboard/summary — 대시보드 상단 통계 3칸 (H1).

    노드 수는 K8s API 접근이 필요해 아직 데이터 소스가 없다(C8, 보류) — null로 내려간다.
    """

    pods: int | None = None
    traffic: int = 0
    nodes: int | None = None


class TrafficPoint(BaseModel):
    """GET /dashboard/traffic-history — 시간 버킷별 call-api 수신 요청 수 1개 점.

    A1의 트래픽 shard 집계(dashboard/traffic-history.json, 10초 버킷 원본)에서 요청
    범위(minutes/bucket_seconds)에 맞게 다시 묶어서 내려간다.
    """

    timestamp: datetime
    requests: int


class PodForecastPoint(BaseModel):
    """GET /dashboard/pod-forecast — 시간대별 예측 파드 수 vs 실제 파드 수 1개 점.

    과거(bucket_time < 현재 정시)는 dashboard/pod-history.json(BackupScheduler가 매시
    정각 스냅샷) 이력에서, 현재·미래는 실시간 예측 파일(predictions/latest.json)에서
    값을 채운다. actual은 과거·현재만 존재하고 미래는 항상 None이다.
    """

    timestamp: datetime
    predicted: int | None = None
    actual: int | None = None


class ComponentHealth(BaseModel):
    name: str
    status: str                               # healthy | warning | unhealthy
    detail: str | None = None


class HealthResponse(BaseModel):
    """GET /health — 컴포넌트별 상태."""

    status: str                               # 전체 = 컴포넌트 중 최악
    components: list[ComponentHealth]
    checked_at: datetime
