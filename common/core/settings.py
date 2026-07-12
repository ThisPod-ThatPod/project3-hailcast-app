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

    # --- S3 (모델 아티팩트 / prediction.json) ---
    s3_bucket: str = "hailcast-dev-model-artifacts"

    # --- Database (RDS/PostgreSQL) ---
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "hailcast"
    db_user: str = "hailcast"
    db_password: str = "hailcast"
    # 지정 시 개별 db_* 값 대신 이 URL을 그대로 사용 (테스트에서 sqlite 등)
    db_url: str | None = None

    @property
    def database_url(self) -> str:
        if self.db_url:
            return self.db_url
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_base_settings() -> BaseAppSettings:
    return BaseAppSettings()
