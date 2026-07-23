# Call API 설정 — 공통 설정 상속 (환경변수 기반)
from functools import lru_cache

from common.core.settings import BaseAppSettings


class CallApiSettings(BaseAppSettings):
    service_name: str = "call-api"
    # 로컬(LocalStack)에서 큐 자동 생성 허용 여부. 운영(EKS)에서는 False 유지.
    sqs_auto_create_queue: bool = False
    # 로컬(LocalStack/moto)에서 버킷 자동 생성 허용 여부.
    s3_auto_create_bucket: bool = False
    # --- A1: 트래픽 집계 (이 파드의 콜 카운트를 FileStore shard로 내보내는 주기) ---
    # 2026-07-23: 트래픽 증가 버튼 클릭 후 화면 반영 지연 줄이려고 10→2초로 단축.
    # S3 쓰기 횟수가 5배 늘지만 지금 규모(call-api 4개 파드)에선 비용/부하 영향 미미.
    traffic_flush_interval_seconds: float = 2.0

    # --- D3: SQS 커넥션 풀 — TPS를 실제로 받아내려면 boto3 기본값(10)으로는 부족
    # (오늘 로컬 테스트에서 "Connection pool is full"로 프로세스가 죽는 것 확인함) ---
    # 2026-07-22: simulator max_tps를 200→600으로 올리면서 비례해서 같이 올림(250/200 비율 유지).
    aws_max_pool_connections: int = 750


@lru_cache
def get_settings() -> CallApiSettings:
    return CallApiSettings()
