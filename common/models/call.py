# Call 관련 DTO — Call API와 Simulator가 동일 모델을 공유한다 (Dummy Model 금지 원칙).
import json
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

from common.core.constants import MESSAGE_VERSION, SOURCE_API


class Location(BaseModel):
    lat: float = Field(..., ge=-90, le=90, description="위도")
    lon: float = Field(..., ge=-180, le=180, description="경도")


class CallRequest(BaseModel):
    """택시 호출 요청 — Simulator도 이 모델을 그대로 사용한다."""

    user_id: str = Field(..., min_length=1, max_length=64)
    pickup: Location
    destination: Location
    zone_id: str | None = Field(
        default=None, max_length=32, description="수요 집계/예측 구역 ID (미지정 시 후처리 단계에서 산출)"
    )
    passenger_count: int = Field(default=1, ge=1, le=8)
    requested_at: datetime | None = Field(
        default=None, description="클라이언트 요청 시각 (미지정 시 서버 수신 시각)"
    )
    source: str = Field(default=SOURCE_API, pattern="^(api|simulator)$")

    @field_validator("requested_at")
    @classmethod
    def ensure_tz(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class CallResponse(BaseModel):
    """Call API 즉시 응답 — Worker 완료를 기다리지 않는다."""

    accepted: bool
    request_id: str
    created_at: datetime
    status: str


class CallStatusResponse(BaseModel):
    request_id: str
    status: str
    requested_at: datetime | None = None
    processed_at: datetime | None = None


class CallMessage(BaseModel):
    """SQS Message Body 스키마 (JSON). Request 전체를 보존한다."""

    request_id: str
    version: str = MESSAGE_VERSION
    timestamp: datetime  # 발행 시각 (queue_latency 산출용)
    data: CallRequest

    def to_body(self) -> dict:
        return json.loads(self.model_dump_json())

    @classmethod
    def from_body(cls, body: str) -> "CallMessage":
        return cls.model_validate_json(body)
