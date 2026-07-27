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
    # 필요해져서 변경). 그 시점엔 k6가 call-api를 직결해서 simulator 자신은 CPU를 거의
    # 안 썼고, call-api 쪽(replica/CPU·커넥션 풀)만 이 상한에 맞춰 검증했었다.
    #
    # 2026-07-27 (600→300→250 하향): B-1(k6→simulator relay)로 바뀌면서 simulator 자신도
    # relay 요청마다 httpx 클라이언트 오버헤드(실측 ~5.83ms/건)를 쓰게 됨 — CPU limit은
    # 2코어 그대로인데(Karpenter NodePool이 2vCPU 인스턴스만 프로비저닝하게 돼있어서
    # instance-cpu 제약을 안 바꾸면 limit만 올려도 실효 없음 — 노드 자체가 더 못 줌.
    # NodePool 변경은 매니페스트/배포팀 소관이라 이번엔 앱 쪽 값만 낮추는 걸로 완화함).
    # 600 TPS는 ~70~90초, 300 TPS는 ~150초 지속하면 liveness probe 실패 → 파드 재시작 →
    # 메모리 상태(트래픽 설정) 초기화되는 것 실측 확인함(트래픽이 감소 버튼 없이 저절로
    # 죽는 것처럼 보이던 원인). 250 TPS(≈1.46코어 필요, 2코어 예산의 73%)로 한 단계 더
    # 낮춰서 재현 여부 재검증 중 — CPU 증설(NodePool 포함)은 별도로 진행 여부 결정.
    # (docs/2026-07-27-findings.md 참고 — call-api/worker 쪽 실제 처리 능력 문제가
    # 아니라 simulator의 relay 오버헤드 문제라 call-api 쪽 설정은 그대로 둔다.)
    traffic_step: float = 200.0      # increase/decrease 1회당 TPS 증감폭
    min_tps: float = 0.0             # 하한 (0 이하로 내려가지 않음, 0이면 k6 정지)
    max_tps: float = 250.0           # 상한 (simulator relay의 CPU 예산에 맞춤, 노드 2vCPU 고정 전제)
    k6_binary: str = "k6"            # PATH에 있는 k6 실행 파일명/경로

    # --- B-1 (2026-07-24): k6가 call-api를 직접 안 때리고 simulator를 거쳐가게 변경 ---
    # k6는 이 파드 안에서 서브프로세스로 뜨므로 항상 이 앱 자신(localhost:8001)으로 보낸다.
    # 포트는 Dockerfile EXPOSE/CMD·k8s Service와 동일하게 고정값(8001)이라 여기서도 고정값으로 둔다.
    # (call_api_url은 그대로 둔다 — relay 엔드포인트가 실제 call-api로 전달할 때 그 값을 쓴다.)
    # _relay는 라우터(/api/simulator) 밖, 앱 루트(/_relay)에 있다 — ①로 /api/simulator/*가 외부에
    # 열려도 인증 없는 relay가 딸려 열리지 않게 구조적으로 격리(simulator.py의 relay 핸들러 주석 참고).
    # k6는 같은 파드 localhost로만 부르므로 ALB를 안 탄다.
    relay_url: str = "http://localhost:8001/_relay"
    relay_timeout_seconds: float = 5.0

    # --- Status (A2) ---
    status_write_interval_seconds: float = 2.0   # FileStore(simulator/status.json) 갱신 주기

    # --- S3 (LocalStack/moto 전용 — 운영은 IaC가 버킷 소유) ---
    s3_auto_create_bucket: bool = False


@lru_cache
def get_settings() -> SimulatorSettings:
    return SimulatorSettings()
