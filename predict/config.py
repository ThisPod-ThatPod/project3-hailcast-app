# Predict(Forecast) 설정 — 주기·Horizon·모델 경로·재시도 전부 환경변수 (매직넘버 금지)
from functools import lru_cache

from common.core.settings import BaseAppSettings


class PredictSettings(BaseAppSettings):
    service_name: str = "predict"

    # --- Scheduler ---
    prediction_interval_seconds: float = 1800.0   # 30분 (30분/1시간/2시간 등 환경변수로 조정)

    # --- Prediction ---
    prediction_window_minutes: int = 60   # 예측 시간창 크기
    prediction_horizon_steps: int = 3     # 몇 개의 시간창을 예측할지 (60분 × 3 = 3시간)

    # --- Model (S3) ---
    model_s3_prefix: str = "models"       # models/latest/{model.txt, metadata.json}
    model_cache_dir: str = "/tmp/hailcast-models"

    # --- Prediction Output (S3) ---
    prediction_s3_prefix: str = "predictions"   # predictions/latest.json + 이력
    prediction_keep_history_in_s3: bool = True

    # --- Retry ---
    forecast_retry_count: int = 3
    forecast_retry_backoff_seconds: float = 2.0

    # --- 조회 API ---
    prediction_history_default_limit: int = 100
    prediction_history_max_limit: int = 1000

    # 로컬(LocalStack) 버킷 자동 생성
    s3_auto_create_bucket: bool = False

    # --- Predictive Scaling ---
    scaling_interval_seconds: float = 60.0        # Prediction Interval과 독립 주기
    scaling_cooldown_seconds: float = 300.0       # Scale Down 유예 (Scale Up은 즉시)
    # 규칙: "임계값:replica" — predicted_demand < 임계값 → replica, 전부 초과 시 max
    scaling_rules: str = "20:1,50:2,100:3,300:5,500:10"
    scaling_min_replicas: int = 1
    scaling_max_replicas: int = 10
    prediction_max_age_seconds: float = 3600.0    # 이보다 오래된 예측으로는 스케일하지 않음
    scaling_retry_count: int = 3
    scaling_retry_backoff_seconds: float = 2.0
    scaling_history_default_limit: int = 50
    # --- KEDA ---
    keda_enabled: bool = False                    # false: InMemory(dry-run) Adapter (로컬/테스트)
    keda_namespace: str = "default"
    keda_scaledobject_name: str = "hailcast-worker-scaler"

    # --- Dashboard / Health ---
    simulator_url: str = "http://localhost:8001"  # Traffic 위젯 프록시 대상
    dashboard_proxy_timeout_seconds: float = 2.0
    health_queue_backlog_warning: int = 1000      # 큐 적체 경고 임계값
    health_weather_max_age_seconds: float = 1800.0  # 날씨 신선도 경고 임계값
    # 로컬(LocalStack) 큐 자동 생성 (health/dashboard가 큐 조회)
    sqs_auto_create_queue: bool = False


@lru_cache
def get_settings() -> PredictSettings:
    return PredictSettings()
