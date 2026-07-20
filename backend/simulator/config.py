# Simulator 설정 — Traffic 파라미터는 전부 환경변수 (매직넘버 금지)
from functools import lru_cache

from common.core.settings import BaseAppSettings


class SimulatorSettings(BaseAppSettings):
    service_name: str = "simulator"

    # --- 대상 ---
    call_api_url: str = "http://localhost:8000"   # 실제 Call API (Dummy API 금지)

    # --- Traffic 제어 (k6 서브프로세스, simulator/k6/call_load.js) ---
    # D1: 버튼 한 번 클릭 = TPS ±200. step과 max가 같아서 한 클릭으로 바로 상한(보호된
    # 안전 용량)까지 켜지는 on/off에 가까운 동작이 된다 — call-api의 커넥션 풀도
    # 이 상한을 실제로 받아낼 수 있게 같이 키워둠(D3, common/aws/client_factory.py).
    traffic_step: float = 200.0      # increase/decrease 1회당 TPS 증감폭
    min_tps: float = 0.0             # 하한 (0 이하로 내려가지 않음, 0이면 k6 정지)
    max_tps: float = 200.0           # 상한 (Call API/로컬 환경 보호)
    k6_binary: str = "k6"            # PATH에 있는 k6 실행 파일명/경로

    # --- Status (A2) ---
    status_write_interval_seconds: float = 2.0   # FileStore(simulator/status.json) 갱신 주기

    # --- S3 (LocalStack/moto 전용 — 운영은 IaC가 버킷 소유) ---
    s3_auto_create_bucket: bool = False


@lru_cache
def get_settings() -> SimulatorSettings:
    return SimulatorSettings()
