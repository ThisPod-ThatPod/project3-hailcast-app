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
    # 2026-07-27: B-1(k6→simulator relay)로 바뀌면서 simulator 자신도 relay 요청마다 httpx
    # 클라이언트 오버헤드(실측 ~5.83ms/건)를 쓰게 됨 — 600 TPS면 초당 ~3.5코어 필요한데
    # CPU limit은 2코어(Karpenter NodePool이 2vCPU 인스턴스만 프로비저닝)라 liveness probe가
    # 간헐적으로 실패 → 파드 재시작 → 메모리 상태(트래픽 설정) 초기화되는 것 실측 확인함
    # (트래픽이 감소 버튼 없이 저절로 죽는 것처럼 보이던 원인). 300→250까지 낮춰봤지만
    # 그러면 worker(반응형 KEDA 스케일링 데모)가 트래픽을 여유 있게 다 처리해버려서 큐가
    # 안 쌓이고, 반응형 스케일업 자체를 시연할 수 없는 것도 실측 확인함(TooFewReplicas —
    # 반응형이 계산한 값이 예측형 minReplicaCount보다 항상 낮아서 안 드러남).
    # 반응형 스케일링 시연이 더 중요하다고 판단해서 600으로 원복 — CPU/NodePool 증설
    # (6~8코어급 인스턴스 필요, 4코어로는 여전히 빠듯함)을 배포팀과 별도로 진행하기로 함.
    # (docs/2026-07-27-findings.md 참고 — call-api/worker 쪽 실제 처리 능력 문제가
    # 아니라 simulator의 relay 오버헤드 문제라 call-api 쪽 설정은 그대로 둔다.)
    # 2026-07-27: 통합 점검 중 클릭 한두 번으로 빠르게 부하를 키워 스케일업을 보고 싶다는
    # 요청으로 200→500 상향(600 상한 기준: 1클릭=500, 2클릭=600에서 캡).
    traffic_step: float = 500.0      # increase/decrease 1회당 TPS 증감폭
    min_tps: float = 0.0             # 하한 (0 이하로 내려가지 않음, 0이면 k6 정지)
    max_tps: float = 600.0           # 상한 (반응형 스케일링 시연에 필요 — CPU/NodePool 증설 필요, 별도 진행)
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

    # --- Burst (2026-07-28) ---
    # "SQS 메시지 유입" 버튼(콜 1건만 보냄, 사실상 안 쓰임)을 대체 — 예측형 baseline이
    # 이미 높을 때는 지속형 TPS(상한 600)로는 큐가 안 쌓여서 반응형(KEDA)을 못 보여준다는
    # 걸 실측 확인함(docs/2026-07-28-todo.md). 지속형 대신 순간적으로 N건을 몰아 쏴서
    # 큐를 즉시 채우는 방식으로 반응형 스케일링을 확실히 트리거한다.
    # ⚠️ burst도 relay_call() 경로를 그대로 써서 요청당 httpx 오버헤드(~5.83ms)가 그대로
    # 든다 — "순간적이라 CPU 부담이 적다"는 착각 주의, 총 CPU 비용은 지속형과 동일하고
    # 오히려 짧은 시간에 몰려서 더 세게 튄다.
    # 실측(2026-07-28): 2000건 → worker(baseline 3)가 그새 다 처리해서 큐가 0으로 빠짐,
    # 반응형 안 뜸. 5000건 → 큐 최대 1223까지 쌓였지만(baseline 3 기준 필요치 1500에
    # 근소하게 못 미침) 여전히 부족, 이때도 simulator는 재시작 없이 안정적이었음(CPU는
    # 여유 있음, worker가 너무 빨라서 못 넘긴 것). 10000으로 상향.
    burst_default_count: int = 10000      # 버튼 기본 요청 수
    burst_max_count: int = 15000          # API로 허용하는 절대 상한(안전장치)
    burst_concurrency: int = 100          # 동시 발사 수 — relay_client 풀(200)보다 낮게 잡아 여유를 둠

    # --- Status (A2) ---
    status_write_interval_seconds: float = 2.0   # FileStore(simulator/status.json) 갱신 주기

    # --- S3 (LocalStack/moto 전용 — 운영은 IaC가 버킷 소유) ---
    s3_auto_create_bucket: bool = False


@lru_cache
def get_settings() -> SimulatorSettings:
    return SimulatorSettings()
