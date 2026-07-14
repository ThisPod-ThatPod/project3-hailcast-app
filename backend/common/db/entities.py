# ORM Entity — DTO(common/models)와 분리. Router 밖으로 Entity를 노출하지 않는다.
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Call(Base):
    """택시 콜 원본 레코드.

    향후 Prediction/Analytics/Feature Engineering에서 그대로 쓸 수 있도록
    좌표·시각·출처·처리 이력을 모두 보존한다.
    """

    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)

    # --- 요청 원본 (ML feature 소스) ---
    # B1(2026-07-13): 모델이 시간+날씨만 쓰고 개별 콜의 위치를 안 써서(ml/data 확인)
    # CallRequest에서 좌표/zone_id/passenger_count를 뺐다 — 여기도 맞춰서 텍스트로 정리.
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    pickup: Mapped[str] = mapped_column(String(200))
    destination: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(16), default="api")  # api | simulator
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    # --- 파이프라인 처리 이력 ---
    status: Mapped[str] = mapped_column(String(16), index=True)
    message_version: Mapped[str] = mapped_column(String(8), default="1")
    enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    receive_count: Mapped[int] = mapped_column(Integer, default=1)  # SQS 재수신 횟수(재처리 추적)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Weather(Base):
    """날씨 레코드 — 시간(observed_at) × 지역(zone_id) 기준으로 누적 저장(History).

    data_type으로 실측(current)/예보(forecast)를 구분해 같은 테이블에 저장하며,
    Prediction과는 (zone_id, observed_at) 키로 Join한다.
    """

    __tablename__ = "weather"
    __table_args__ = (
        # 동일 시간·구역·타입 중복 저장 방지 (Upsert 기준 키)
        UniqueConstraint("zone_id", "observed_at", "data_type", name="uq_weather_zone_time_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- Join 키 ---
    zone_id: Mapped[str] = mapped_column(String(32), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    data_type: Mapped[str] = mapped_column(String(16), default="current")  # current | forecast

    # --- 위치 메타 ---
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    timezone_name: Mapped[str] = mapped_column(String(32), default="UTC")

    # --- Forecast Feature (LightGBM 입력 후보) ---
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    rain_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    cloud_cover_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    weather_code: Mapped[int | None] = mapped_column(Integer, nullable=True)  # WMO code
    visibility_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    source: Mapped[str] = mapped_column(String(32), default="open-meteo")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Prediction(Base):
    """수요 예측 History — Dashboard 조회용 (zone 없음, 뉴욕 날씨 기반 글로벌 수요 하나).

    target_time으로 조회한다. 같은 target_time에 대해 여러 번 예측될 수 있으므로
    generated_at으로 최신 배치를 식별한다.
    """

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    predicted_demand: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    prediction_window_minutes: Mapped[int] = mapped_column(Integer, default=60)
    model_version: Mapped[str] = mapped_column(String(64))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PodReplicaHistory(Base):
    """시간대별(정시 버킷) 파드 수 이력 — 예측치·실측치를 함께 저장 (Dashboard 그래프용).

    BackupScheduler가 매 시간 정각 버킷에 predicted/actual을 스냅샷으로 남긴다.
    구역 구분 없이 클러스터 전체 replica 수 기준(worker Deployment 1개).
    """

    __tablename__ = "pod_replica_history"
    __table_args__ = (
        UniqueConstraint("bucket_time", name="uq_pod_replica_bucket_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    predicted_replicas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_replicas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ScalingEvent(Base):
    """Predictive Scaling 이력 — replica 변경이 실제 적용될 때마다 1건 저장 (Dashboard 조회)."""

    __tablename__ = "scaling_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    predicted_demand: Mapped[float] = mapped_column(Float)
    old_replica: Mapped[int] = mapped_column(Integer)
    new_replica: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(16), index=True)  # SCALE_UP | SCALE_DOWN
    reason: Mapped[str] = mapped_column(String(256))
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
