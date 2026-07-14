# worker-db-original/

인프라팀이 공유한 최종 아키텍처 다이어그램(2026-07-13)은 "워커 Pod: 큐 소비 → RDS
기록"이라고 명시한다 — 이 세션의 백엔드 재설계 결정(J3: DB를 이번 페이즈에서 뺀다,
`docs/2026-07-13-backend-redesign-discussion.md`)과 정면으로 충돌한다
(`project_hailcast_architecture_conflict.md` 메모리에도 기록됨).

결정: **둘 다 만든다.** 다이어그램이 요구하는 RDS 버전은 여기 격리해두고(최신
`CallRequest` 스키마(B1)에 맞춰 고쳐서 컴파일 가능한 상태로 유지), 실제로 도는 건
`worker/services/worker_service.py`의 FileStore 버전이다.

## 여기 있는 것

| 파일 | 원래 자리 | 비고 |
|---|---|---|
| `worker_service.py` | worker/services/worker_service.py | DB(RDS) 기반, Polling→Deserialize→DB Save→ACK |
| `state_manager.py` | worker/services/state_manager.py | DB `Call` 엔티티의 상태 전이 관리 |
| `call_repository.py` | worker/repositories/call_repository.py | DB 쓰기 — `CallRequest` 최신 스키마(pickup/destination 텍스트)에 맞춰 고침. `get_by_call_id`는 call-api가 `GET /call/{id}` 조회용으로도 그대로 썼던 것과 동일 로직(그쪽 사본은 중복이라 삭제, 여기 하나로 통일) |

## RDS를 실제로 쓰게 되면

1. 이 폴더 3개 파일을 각자 원래 자리(위 표)로 되돌린다.
2. `worker/dependencies.py`를 `Database` 기반으로 다시 바꾼다(지금은 FileStore).
3. `worker/worker.py`에 `get_database().init_schema()` 복원.
4. `common/db/entities.py::Call`은 이미 최신 스키마로 고쳐져 있어서 추가 작업 불필요.
