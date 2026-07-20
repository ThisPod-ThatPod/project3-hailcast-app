# scripts — app 레포 운영 스크립트

이 Pod 저 Pod · **hailcast** 프로젝트 **app 레포**의 Makefile 과 셸 스크립트 설명서.
로컬 테스트 환경(docker compose) 기동과 ECR 배포(build→push)를 `make` 한 번으로 돌리기 위한 도구들이다.

설계는 ops 레포(`project3-hailcast-ops`)의 패턴을 따른다 — 계정 가드 · `.env` 안전 파싱 · CONFIRM 스위치 · 공용 상수 단일화.

---

## 파일 구성

```
project3-hailcast-app/
├── Makefile                  # make 진입점 (ops 의 make -C 위임도 여기로 들어옴)
├── .env.example              # PROJECT_ACCOUNT_ID 템플릿 (복사해서 .env 생성)
└── scripts/
    ├── _lib.sh               # 공용: 상수·색상 출력·.env 파싱·계정 가드
    ├── dev_local.sh          # 로컬 docker compose 관리 (AWS 불필요)
    ├── build_push.sh         # docker build → ECR push (계정 가드 선행)
    ├── teardown_app.sh       # 로컬 도커 이미지·볼륨·캐시 정리
    └── README.md             # 이 문서
```

| 파일 | 역할 | AWS 자격증명 |
|---|---|---|
| `_lib.sh` | 직접 실행하지 않는다. 다른 스크립트가 `source` 하는 공용 라이브러리 | — |
| `dev_local.sh` | docker-compose.yml (postgres + LocalStack + 서비스 5종) 기동/중지/로그 | **불필요** |
| `build_push.sh` | 서비스 이미지 빌드 → 프로젝트 계정 ECR push | **필요 + 계정 가드** |
| `teardown_app.sh` | 로컬 도커 자원 정리 (ops teardown 의 마지막 단계) | 불필요 |

---

## 빠른 시작

```bash
# 로컬 테스트 (AWS 계정·.env 없이 바로 됨)
make dev-up                   # 전체 빌드 + 기동
make dev-logs SVC=call-api    # 특정 서비스 로그 팔로우
make dev-down                 # 중지 (DB 데이터 유지)

# ECR 배포 (최초 1회: .env 준비)
cp .env.example .env          # PROJECT_ACCOUNT_ID 를 채운다 (값은 팀 채널에서)
make build-push               # 계정 가드 → ECR 로그인 → build → push
```

---

## Makefile 명령 일람

| 명령 | 스크립트 | 설명 |
|---|---|---|
| `make help` | — | 명령 목록 |
| `make dev-up` | `dev_local.sh up` | 전체 빌드 + 백그라운드 기동 (postgres·localstack 포함) |
| `make dev-down` | `dev_local.sh down` | 중지. **볼륨은 남긴다** (DB 데이터 유지) |
| `make dev-clean` | `dev_local.sh clean` | 중지 + 볼륨 삭제 (DB 초기화 · y/N 확인 후 실행) |
| `make dev-rebuild SVC=<svc>` | `dev_local.sh rebuild` | 해당 서비스만 다시 빌드해 교체 (SVC 생략 시 전체) |
| `make dev-logs SVC=<svc>` | `dev_local.sh logs` | 로그 팔로우 (SVC 생략 시 전체) |
| `make dev-ps` | `dev_local.sh ps` | 컨테이너 상태 |
| `make dev-train` | `dev_local.sh train` | 오프라인 학습 1회 (`docker compose run --rm ml-train`) |
| `make build-push` | `build_push.sh` | docker build → ECR push. **ops 의 `make app-build-push` 가 위임하는 타겟** |
| `make teardown` | `teardown_app.sh` | 로컬 도커 정리. **ops 의 `destroy-all` 3단계(마지막)가 부르는 타겟** |

로컬 엔드포인트 (dev-up 후):

| 서비스 | 주소 |
|---|---|
| call-api | http://localhost:8000 |
| simulator | http://localhost:8001 |
| weather-cron | http://localhost:8002 |
| predict | http://localhost:8003 |

---

## 변수 (환경변수 · make 변수)

| 변수 | 기본값 | 쓰는 곳 | 뜻 |
|---|---|---|---|
| `SVC` | (없음 = 전체) | `dev-rebuild` · `dev-logs` | 대상 서비스 하나를 지정 |
| `SERVICES` | `call-api predict worker weather-cron simulator` | `build-push` | 빌드·push 대상 목록. frontend 는 서빙방식(nginx 파드) 확정 후 추가 |
| `TAG` | git 짧은 커밋 해시 | `build-push` | 이미지 태그. `TAG=v0.1.0 make build-push` 처럼 지정. latest 는 항상 함께 push |
| `REGION` / `AWS_REGION` | `ap-northeast-2` | `build-push` | ECR 리전 |
| `PROJECT_ACCOUNT_ID` | `.env` 에서 읽음 | `build-push` | 프로젝트 AWS 계정 12자리. **환경변수가 있으면 .env 보다 우선** (CI 는 GitHub Secret 으로 주입) |
| `CONFIRM=yes` | (없음 = 미리보기) | `teardown` | 실제 삭제 실행. ops `destroy-all --yes` 가 자동 주입 |
| `FILTER` | `hailcast` | `teardown` | 지울 이미지·볼륨 이름 필터 |

---

## 설계 원칙 (왜 이렇게 나눴나)

### 1. 로컬용과 ECR용을 파일로 분리했다

- `dev_local.sh` 는 **AWS 자격증명이 아예 필요 없는** 작업이다. compose 안의 AWS 키는 LocalStack 전용 더미값(`test`)이다. 여기에 계정 가드를 걸면 로컬 테스트가 `.env` 없이는 안 되는 이상한 상황이 된다.
- `build_push.sh` 는 **운영 이미지를 바꾸는** 경로라 계정 가드가 선행된다.
- ops 레포가 "위험한 경로와 안전한 경로를 파일 단위로 분리"하는 철학(예: `infra-fmt` 만 가드 제외)과 같은 논리다.

### 2. 계정 가드 — push 전에 '어느 계정인지' 먼저 대조한다

`build_push.sh` 는 시작하자마자 `aws sts get-caller-identity` 결과를 `PROJECT_ACCOUNT_ID` 와 대조하고, 다르면 즉시 중단한다. 엉뚱한 계정에 앉은 채로 돌면 남의 레지스트리에 올리거나 로그인부터 죽는다.

⚠️ 환경변수 자격증명(`AWS_ACCESS_KEY_ID` 등)은 프로필·`[default]` 보다 우선한다. 가드가 빨간불이면 먼저 확인:

```bash
aws sts get-caller-identity
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN   # 엉뚱한 키가 잡혀 있을 때
```

### 3. `.env` 는 `source` 하지 않는다 — 한 줄만 값으로 읽는다

`_lib.sh` 는 `.env` 에서 `PROJECT_ACCOUNT_ID=` 대입문 한 줄만 뽑아 따옴표를 벗긴다. `source` 하면 `.env` 의 다른 변수가 가드와 실제 도구의 자격증명을 가르거나, 함수 정의로 가드를 통째로 속일 수 있다 (ops 레포 `scripts/_lib.sh` 주석 참조 — 둘 다 실증됨). 그래서 **`.env` 에는 `PROJECT_ACCOUNT_ID` 말고 아무것도 적지 마라** — 적어도 효과가 없다.

### 4. ECR 리포지토리는 여기서 만들지 않는다

리포지토리 이름은 **네이밍규약서 §5-2** (`hailcast-dev-<서비스>`)를 따르고, 생성은 **infra(Terraform) 소관**이다. `build_push.sh` 가 몰래 `create-repository` 하면 규약서 밖 리소스가 생기고 `terraform destroy` 로도 안 지워진다. 리포지토리가 없으면 만들지 않고 중단한다 → ops 에서 `make infra-apply` 가 먼저다.

### 5. 태그는 git 커밋 해시 + latest

`latest` 만 쓰면 클러스터에 '어느 코드가 떠 있는지' 역추적할 수 없다. 커밋 해시 태그를 함께 올려 이미지 ↔ 코드를 1:1 로 잇는다. 커밋 안 된 변경이 있으면 경고가 뜬다 (해시가 실제 이미지 내용을 대변하지 못하므로).

### 6. 공용 상수는 `_lib.sh` 한 곳에만

리전·서비스 목록·이름 prefix(`hailcast-dev`)·계정 가드 함수는 `_lib.sh` 에만 있다. 스크립트마다 흩어 두면 하나만 고치고 나머지가 낡는다.

---

## ops 레포와의 관계

ops 레포의 최상위 Makefile 이 이 레포에 `make -C` 로 위임한다. **타겟 이름이 계약이다** — 바꾸면 ops 쪽 위임이 조용히 깨진다.

| ops 명령 | 이 레포에서 실행되는 것 |
|---|---|
| `make app-build-push` | `make build-push` → `scripts/build_push.sh` |
| `make destroy-all` (3단계 app) | `scripts/teardown_app.sh` (CONFIRM 은 ops 가 주입하지 않음 — 로컬 청소라 각자 판단) |

push 이후의 배포 흐름: **build_push (여기) → manifests 레포에서 이미지 태그 갱신 → ops 에서 `make deploy`** (GitOps · ArgoCD).

---

## 자주 겪는 문제

| 증상 | 원인 · 해결 |
|---|---|
| `PROJECT_ACCOUNT_ID 가 없습니다` | `cp .env.example .env` 후 계정 ID 를 채운다 (값은 팀 채널에서) |
| `프로젝트 계정이 아닙니다` | 다른 계정 자격증명이 잡혀 있다. `aws sts get-caller-identity` 로 확인, 환경변수 키가 있으면 `unset` |
| `ECR 리포지토리 '...' 없음` | infra apply 전이다. ops 에서 `make infra-apply` 가 먼저 |
| `docker 데몬에 접근 불가` | `sudo systemctl start docker` 또는 그룹 미반영이면 `newgrp docker` |
| dev-up 후 predict 가 unhealthy | 기동 직후 학습 모델·의존 대기일 수 있다. `make dev-logs SVC=predict` 로 원인 확인 |
| 로컬 DB 를 초기화하고 싶다 | `make dev-clean` (볼륨까지 삭제 · y/N 확인) |
