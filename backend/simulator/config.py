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

    # --- B-1 (2026-07-24): k6가 call-api를 직접 안 때리고 simulator를 거쳐가게 변경 ---
    # k6는 이 파드 안에서 서브프로세스로 뜨므로 항상 이 앱 자신(localhost:8001)으로 보낸다.
    # 포트는 Dockerfile EXPOSE/CMD·k8s Service와 동일하게 고정값(8001)이라 여기서도 고정값으로 둔다.
    # (call_api_url은 그대로 둔다 — relay 엔드포인트가 실제 call-api로 전달할 때 그 값을 쓴다.)
    relay_url: str = "http://localhost:8001/simulator/_relay"
    relay_timeout_seconds: float = 5.0

    # --- Status (A2) ---
    status_write_interval_seconds: float = 2.0   # FileStore(simulator/status.json) 갱신 주기

    # --- S3 (LocalStack/moto 전용 — 운영은 IaC가 버킷 소유) ---
    s3_auto_create_bucket: bool = False


@lru_cache
def get_settings() -> SimulatorSettings:
    return SimulatorSettings()
