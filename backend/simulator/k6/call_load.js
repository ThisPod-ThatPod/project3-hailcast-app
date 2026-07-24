// k6 부하 스크립트 — TARGET_RPS로 TARGET_URL에 고정 payload를 반복 전송한다.
// [B-1, 2026-07-24] call-api를 직접 안 때리고 simulator 자신의 relay 엔드포인트
// (/api/simulator/_relay)를 때린다 — simulator가 call-api로 그대로 전달하면서 성공/실패를
// 그 자리에서 카운트한다(traffic_state.py record_success/record_fail).
// (simulator/services/k6_runner.py가 SimulatorService start/increase/decrease/stop에 맞춰 이 프로세스를 제어한다)
import http from 'k6/http';
import { check } from 'k6';

// 경로에 /api가 붙은 이유: simulator_router 전체가 simulator.py에서 prefix="/api"로 마운트된다
// (7/23 「나」안). _relay는 같은 파드 안 localhost 호출이라 ALB를 타지 않지만, 접두어는 ALB가
// 아니라 앱이 갖고 있으므로 여기 경로도 같이 옮겨야 한다.
const TARGET_URL = __ENV.TARGET_URL || 'http://localhost:8001/api/simulator/_relay';
const TARGET_RPS = Number(__ENV.TARGET_RPS || '1');
// 재시작 전까지 계속 도는 게 목적이라 duration은 넉넉히 길게 잡고, 수명은 k6_runner.py가 프로세스 종료로 제어한다.
const DURATION = __ENV.DURATION || '24h';

export const options = {
  scenarios: {
    call_traffic: {
      executor: 'constant-arrival-rate',
      rate: TARGET_RPS,
      timeUnit: '1s',
      duration: DURATION,
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
