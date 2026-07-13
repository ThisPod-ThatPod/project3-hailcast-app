# Worker 설정 — Polling/Visibility/Retry 파라미터는 전부 환경변수로 관리 (매직넘버 금지)
from functools import lru_cache

from common.core.settings import BaseAppSettings


class WorkerSettings(BaseAppSettings):
    service_name: str = "worker"

    # --- SQS 소비 파라미터 ---
    sqs_batch_size: int = 10            # 1회 수신 최대 메시지 수 (SQS 최대 10)
    sqs_long_poll_seconds: int = 20     # Long Polling 대기 (SQS 최대 20초)
    sqs_visibility_timeout: int = 30    # 처리 중 메시지 숨김 시간
    sqs_retry_count: int = 5            # 이 횟수 초과 재수신 시 FAILED 처리 (향후 DLQ 대상)
    poll_idle_interval: float = 0.0     # 빈 폴링 후 추가 대기 (Long Polling이 있어 기본 0)

    # 로컬(LocalStack) 큐 자동 생성
    sqs_auto_create_queue: bool = False
    # 로컬(LocalStack/moto) 버킷 자동 생성
    s3_auto_create_bucket: bool = False


@lru_cache
def get_settings() -> WorkerSettings:
    return WorkerSettings()
