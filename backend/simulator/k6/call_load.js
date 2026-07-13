// k6 부하 스크립트 — call-api POST /call에 고정 payload를 TARGET_RPS로 반복 전송한다.
// (simulator/services/k6_runner.py가 SimulatorService start/increase/decrease/stop에 맞춰 이 프로세스를 제어한다)
import http from 'k6/http';
import { check } from 'k6';

const CALL_API_URL = __ENV.CALL_API_URL || 'http://localhost:8000';
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
  const res = http.post(`${CALL_API_URL}/call`, PAYLOAD, {
    headers: { 'Content-Type': 'application/json' },
  });
  check(res, { 'accepted (202)': (r) => r.status === 202 });
}
