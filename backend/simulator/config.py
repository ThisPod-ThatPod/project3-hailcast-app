# Simulator 설정 — Traffic 파라미터는 전부 환경변수 (매직넘버 금지)
from functools import lru_cache

from common.core.settings import BaseAppSettings


class SimulatorSettings(BaseAppSettings):
    service_name: str = "simulator"

    # --- 대상 ---
    call_api_url: str = "http://localhost:8000"   # 실제 Call API (Dummy API 금지)

    # --- Traffic 제어 (k6 서브프로세스, simulator/k6/call_load.js) ---
    # 2026-07-22: 버튼을 누른 만큼 200→400→600으로 누적되게 max_tps를 traffic_step의
    # 3배로 늘림(원래 D1은 step==max로 on/off 토글이었는데, 여러 단계로 올려보는 테스트가
    # 필요해져서 변경). call-api의 replica/CPU·커넥션 풀(D3, common/aws/client_factory.py,
    # call-api/config.py::aws_max_pool_connections)도 이 상한에 맞춰 같이 올려뒀다 —
    # 여기 값만 혼자 올리면 call-api가 못 버티고 죽는다(2026-07-22 실제 crash 확인함).
    traffic_step: float = 200.0      # increase/decrease 1회당 TPS 증감폭
    min_tps: float = 0.0             # 하한 (0 이하로 내려가지 않음, 0이면 k6 정지)
    max_tps: float = 600.0           # 상한 (call-api 증설 용량에 맞춤)
    k6_binary: str = "k6"            # PATH에 있는 k6 실행 파일명/경로

    # --- Status (A2) ---
    status_write_interval_seconds: float = 2.0   # FileStore(simulator/status.json) 갱신 주기

    # --- S3 (LocalStack/moto 전용 — 운영은 IaC가 버킷 소유) ---
    s3_auto_create_bucket: bool = False


@lru_cache
def get_settings() -> SimulatorSettings:
    return SimulatorSettings()
