# Call 관련 DTO — Call API와 Simulator가 동일 모델을 공유한다 (Dummy Model 금지 원칙).
#
# B1: 좌표/zone_id/passenger_count 필드는 뺐다 — ml/data(nycTaxiDataset.csv,
# nycTaxiWeather.csv, dummy_predict_input_*.csv)를 확인해보니 학습·예측 모델은 애초에
# "언제 콜이 왔는지(시간)+날씨"만 쓰고 개별 콜의 위치는 전혀 쓰지 않는다(zone 기반 설계는
# 프로젝트 초반에 걷어냄) — 콜 1건은 그 시간 버킷의 수요 카운트에 1을 더하는 이벤트일
# 뿐이다. pickup/destination은 화면 표시용 텍스트로만 남기고(ServicePage.tsx와 스키마
# 일치, C7 해결), 실제로 쓰이지 않던 정밀도/제약(위경도 범위 등)은 없앴다.
import json
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

from common.core.constants import MESSAGE_VERSION, SOURCE_API


class CallRequest(BaseModel):
    """택시 호출 요청 — Simulator/ServicePage.tsx가 그대로 사용한다."""

    user_id: str = Field(..., min_length=1, max_length=64)
    pickup: str = Field(..., min_length=1, max_length=200, description="출발지 (표시용 텍스트)")
    destination: str = Field(..., min_length=1, max_length=200, description="도착지 (표시용 텍스트)")
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
