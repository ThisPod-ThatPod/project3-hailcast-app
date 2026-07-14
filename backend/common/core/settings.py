# 환경변수 기반 공통 설정 — 각 서비스 config.py가 이 클래스를 상속한다
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "hailcast"
    log_level: str = "INFO"

    # --- AWS ---
    aws_region: str = "ap-northeast-2"
    # LocalStack 등 로컬 개발용 엔드포인트. 미설정(None)이면 실제 AWS 사용(EKS에서는 IRSA).
    aws_endpoint_url: str | None = None

    # --- SQS ---
    sqs_queue_name: str = "hailcast-dev-call-queue"
    sqs_queue_url: str | None = None  # 지정 시 GetQueueUrl 조회 생략

    # --- S3 (모델 아티팩트 / prediction.json / JSON 상태 동기화) ---
    s3_bucket: str = "hailcast-dev-model-artifacts"

    # --- CORS (프론트가 다른 origin/포트에서 호출) ---
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- JSON/CSV 상태 저장소 (DB 대체) ---
    # local: json_store_local_dir 밑 파일로 저장 (단일 프로세스 로컬 테스트 전용).
    # s3: s3_bucket에 저장 (여러 파드가 떠도 공유되는 유일한 진실원천).
    json_store_backend: str = "local"
    json_store_local_dir: str = "./local_store"


@lru_cache
def get_base_settings() -> BaseAppSettings:
    return BaseAppSettings()
