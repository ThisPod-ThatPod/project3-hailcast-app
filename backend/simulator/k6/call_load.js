// k6 부하 스크립트 — TARGET_RPS로 TARGET_URL에 고정 payload를 반복 전송한다.
// [B-1, 2026-07-24] call-api를 직접 안 때리고 simulator 자신의 relay 엔드포인트
// (/_relay)를 때린다 — simulator가 call-api로 그대로 전달하면서 성공/실패를
// 그 자리에서 카운트한다(traffic_state.py record_success/record_fail).
// (simulator/services/k6_runner.py가 SimulatorService start/increase/decrease/stop에 맞춰 이 프로세스를 제어한다)
import http from 'k6/http';
import { check } from 'k6';

// _relay는 라우터(/api/simulator) 밖, 앱 루트에 있다 — ①로 /api/simulator/*가 외부에 열려도
// 인증 없는 relay가 딸려 열리지 않게 격리한 것(simulator.py 참고). k6는 같은 파드 안 localhost
// 호출이라 ALB를 타지 않으므로 루트 경로 그대로 문제없다.
const TARGET_URL = __ENV.TARGET_URL || 'http://localhost:8001/_relay';
const TARGET_RPS = Number(__ENV.TARGET_RPS || '1');
// [2026-07-28] 재시작 직전 rate — 0(최초 시작)이면 그냥 0에서 램프. increase/decrease로
// 재시작할 때는 k6_runner.py가 이전 current_tps를 넘겨줘서 그 지점부터 이어서 램프한다.
const CURRENT_RPS = Number(__ENV.CURRENT_RPS || '0');
// 재시작 전까지 계속 도는 게 목적이라 duration은 넉넉히 길게 잡고, 수명은 k6_runner.py가 프로세스 종료로 제어한다.
const DURATION = __ENV.DURATION || '24h';
// CURRENT_RPS → TARGET_RPS로 5초에 걸쳐 램프 — 예전엔 constant-arrival-rate라 재시작마다
// TARGET으로 즉시 점프해서, 클릭할 때마다(특히 여러 번 연달아 누를 때) 그래프가 계단식/펄스
// 형태로 튀는 원인이었다. 목표 도달 후엔 나머지 시간 동안 TARGET_RPS로 유지.
const RAMP_SECONDS = 5;

export const options = {
  scenarios: {
    call_traffic: {
      executor: 'ramping-arrival-rate',
      startRate: CURRENT_RPS,
      timeUnit: '1s',
      stages: [
        { target: TARGET_RPS, duration: `${RAMP_SECONDS}s` },
        { target: TARGET_RPS, duration: DURATION },
      ],
      preAllocatedVUs: Math.max(10, Math.ceil(TARGET_RPS * 2)),
      maxVUs: Math.max(50, Math.ceil(TARGET_RPS * 5)),
    },
  },
};

// common/models/call.py CallRequest와 동일 형태의 고정 payload (B1 — 좌표/zone_id/
// passenger_count 없앰, 모델은 시간+날씨만 씀).
const PAYLOAD = JSON.stringify({
  user_id: 'k6-load-test',
  pickup: 'k6-load-test-pickup',
  destination: 'k6-load-test-destination',
  source: 'simulator',
});

export default function () {
  const res = http.post(TARGET_URL, PAYLOAD, {
    headers: { 'Content-Type': 'application/json' },
  });
  check(res, { 'accepted (202)': (r) => r.status === 202 });
}
