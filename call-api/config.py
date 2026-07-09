# Call API 설정 — 공통 설정 상속 (환경변수 기반)
from functools import lru_cache

from common.core.settings import BaseAppSettings


class CallApiSettings(BaseAppSettings):
    service_name: str = "call-api"
    # 로컬(LocalStack)에서 큐 자동 생성 허용 여부. 운영(EKS)에서는 False 유지.
    sqs_auto_create_queue: bool = False


@lru_cache
def get_settings() -> CallApiSettings:
    return CallApiSettings()
