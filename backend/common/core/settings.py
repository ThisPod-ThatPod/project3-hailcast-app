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
    # 07-13 네이밍 규약에 따른 변수명 및 코드 수정 중 A-1. SQS Queue 이름에 dev 누락
    sqs_queue_name: str = "hailcast-dev-call-queue"
    sqs_queue_url: str | None = None  # 지정 시 GetQueueUrl 조회 생략

    # --- S3 (모델 아티팩트 / prediction.json / JSON 상태 동기화) ---
    # 07-13 네이밍 규약에 따른 변수명 및 코드 수정 중 A-4. S3 버킷 기본값 규약 정렬
    # (실제 버킷은 랜덤 접미사 포함 — 운영에서는 S3_BUCKET env로 주입, 규약 §5-2)
    s3_bucket: str = "hailcast-dev-model-artifacts"

    # --- CORS (프론트가 다른 origin/포트에서 호출) ---
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- JSON/CSV 상태 저장소 (DB 대체) ---
    # local: json_store_local_dir 밑 파일로 저장 (단일 프로세스 로컬 테스트 전용).
    # s3: s3_bucket에 저장 (여러 파드가 떠도 공유되는 유일한 진실원천).
    json_store_backend: str = "local"
    json_store_local_dir: str = "./local_store"

    # --- RDS(PostgreSQL) — call-api/worker의 Call 기록용 (C9, 2026-07-16) ---
    # 운영에서는 ESO가 Secrets Manager 값을 K8s Secret으로 주입, 코드는 환경변수만 읽는다.
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "hailcast"
    db_username: str = "hailcast"
    db_password: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.db_username}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_base_settings() -> BaseAppSettings:
    return BaseAppSettings()
