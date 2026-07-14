# Predict(Forecast) 설정 — 주기·Horizon·모델 경로·재시도 전부 환경변수 (매직넘버 금지)
from functools import lru_cache

from common.core.constants import TRAFFIC_JSON_KEY, WEATHER_FORECAST_CSV_KEY
from common.core.settings import BaseAppSettings


class PredictSettings(BaseAppSettings):
    service_name: str = "predict"

    # --- Scheduler: weather-cron과 같은 4시간 주기, 3분 늦춰 정렬(00:03/04:03/...) ---
    # weather-cron이 그 주기의 :00에 새 예보를 먼저 갱신해둬야 predict가 최신 데이터를 쓴다.
    prediction_interval_seconds: float = 4 * 3600
    prediction_align_offset_seconds: float = 180.0

    # --- Prediction ---
    prediction_window_minutes: int = 60      # 예측 시간창 크기 (1시간 버킷)
    prediction_horizon_hours: int = 4        # 한 번 실행할 때 몇 시간 앞까지 예측할지 (주기와 동일 — 다음 실행까지 안 끊기게)

    # --- Model (S3) ---
    model_s3_prefix: str = "models"       # models/latest/{model.pkl, metadata.json}
    model_cache_dir: str = "/tmp/hailcast-models"

    # --- 날씨 입력 — weather-cron이 FileStore에 저장한 CSV를 읽는다 (직접 API 호출 안 함) ---
    weather_csv_key: str = WEATHER_FORECAST_CSV_KEY

    # --- Prediction Output (FileStore: local 또는 S3) ---
    prediction_s3_prefix: str = "predictions"   # predictions/latest.json + latest.csv + 이력
    prediction_keep_history_in_s3: bool = True

    # --- Retry ---
    forecast_retry_count: int = 3
    forecast_retry_backoff_seconds: float = 2.0

    # 로컬(LocalStack) 버킷 자동 생성
    s3_auto_create_bucket: bool = False

    # --- A1: 트래픽 집계 (call-api 각 파드의 shard를 모아 합산, 10초마다) ---
    traffic_aggregate_interval_seconds: float = 10.0

    # --- Predictive Scaling (G1) ---
    scaling_interval_seconds: float = 60.0        # Prediction Interval과 독립 주기
    scaling_cooldown_seconds: float = 300.0       # Scale Down 유예 (Scale Up은 즉시)
    scaling_demand_per_pod: float = 500.0         # 파드 1개가 감당한다고 보는 예측수요
    scaling_buffer_pods: int = 1                  # n+1 여유분 (수요 0이면 버퍼 없이 1개)
    scaling_min_replicas: int = 1
    scaling_max_replicas: int = 10
    prediction_max_age_seconds: float = 3600.0    # 이보다 오래된 예측으로는 스케일하지 않음
    scaling_retry_count: int = 3
    scaling_retry_backoff_seconds: float = 2.0

    # --- Predictive Scaling (G2 — 반응형 조정, A1의 트래픽 집계 JSON에 의존) ---
    # A1(트래픽 10초 단위 집계)이 아직 없으면 이 레이어는 자동으로 비활성(예측 기준선만 사용).
    traffic_json_key: str = TRAFFIC_JSON_KEY
    scaling_watermark_high: float = 0.8   # 현재 용량의 이 비율 이상 실측되면 +1
    scaling_watermark_low: float = 0.4    # 이 비율 이하로 내려가야 반응형 상태 해제/축소
    scaling_reactive_step: int = 1

    # --- KEDA ---
    keda_enabled: bool = False                    # false: InMemory(dry-run) Adapter (로컬/테스트)
    # 07-13 네이밍 규약에 따른 변수명 및 코드 수정 중 2. keda_namespace 값 어긋남
    keda_namespace: str = "hailcast"   # 네이밍규약서 §8 — 앱 워크로드 네임스페이스
    keda_scaledobject_name: str = "hailcast-worker-scaler"
    worker_deployment_name: str = "hailcast-worker"   # 실제 파드 수(status.readyReplicas) 조회 대상

    # --- Pod 이력 백업 (Dashboard 예측-실제 파드 그래프) ---
    backup_interval_seconds: float = 3600.0   # 정시 버킷 스냅샷 주기 (1시간)

    # --- Dashboard / Health ---
    health_queue_backlog_warning: int = 1000      # 큐 적체 경고 임계값
    # weather-cron 주기(4h)보다 넉넉히 여유를 둔 신선도 경고 임계값 (5시간)
    health_weather_max_age_seconds: float = 5 * 3600.0
    # 로컬(LocalStack) 큐 자동 생성 (health/dashboard가 큐 조회)
    sqs_auto_create_queue: bool = False


@lru_cache
def get_settings() -> PredictSettings:
    return PredictSettings()
