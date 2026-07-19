#!/bin/bash
# =============================================================
# 파일위치 : project3-hailcast-app/scripts/dev_local.sh
# 이 Pod 저 Pod · hailcast — 로컬 docker compose 테스트 환경 관리
# 역할    : docker-compose.yml(로컬 전용 · postgres + LocalStack + 서비스 5종)을
#           기동/중지/점검하는 개발용 진입점. 운영 배포와 무관하다.
# 실행    : bash scripts/dev_local.sh <명령>   또는   make dev-up 등
#
# ⚠️ 계정 가드를 걸지 않는다 — AWS 자격증명이 아예 필요 없는 작업이다.
#    (compose 안의 AWS 키는 LocalStack 전용 더미값 'test' 다.)
#    실제 AWS 를 만지는 build_push.sh 와 파일을 일부러 분리했다.
# =============================================================
set -u

# shellcheck source=scripts/_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"

usage() {
    echo ""
    echo "사용법: bash scripts/dev_local.sh <명령> [서비스]"
    echo ""
    echo "  up              전체 빌드 + 백그라운드 기동 (postgres·localstack 포함)"
    echo "  down            중지 (데이터 볼륨은 남김)"
    echo "  clean           중지 + 볼륨 삭제 (DB 데이터까지 초기화 · 확인 후 실행)"
    echo "  rebuild [서비스] 해당 서비스만 다시 빌드해 교체 (생략 시 전체)"
    echo "  logs [서비스]    로그 팔로우 (생략 시 전체)"
    echo "  ps              컨테이너 상태"
    echo "  train           오프라인 학습 1회 실행 (docker compose run --rm ml-train)"
    echo ""
    echo "  로컬 엔드포인트: call-api :8000 · simulator :8001 · weather-cron :8002 · predict :8003"
    echo ""
}

# ── 전제 확인 : docker 데몬 + compose 플러그인 ─────────────
command -v docker &>/dev/null || error "docker 미설치 → ops 레포에서 make setup"
docker info &>/dev/null       || error "docker 데몬에 접근 불가 → sudo systemctl start docker 또는 newgrp docker"
docker compose version &>/dev/null || error "docker compose 플러그인 없음 → ops 레포에서 make setup"

# compose 는 항상 레포 루트 기준으로 돈다 (어느 디렉토리에서 불러도 동일 동작)
cd "$APP_ROOT"

CMD="${1:-}"
SVC="${2:-}"

case "$CMD" in
    up)
        info "로컬 테스트 환경 기동 (build + up -d)..."
        docker compose up -d --build
        echo ""
        docker compose ps
        echo ""
        success "기동 완료 — 엔드포인트:"
        echo "    call-api      http://localhost:8000"
        echo "    simulator     http://localhost:8001"
        echo "    weather-cron  http://localhost:8002"
        echo "    predict       http://localhost:8003"
        echo "    로그 보기:  bash scripts/dev_local.sh logs [서비스]"
        ;;
    down)
        info "로컬 테스트 환경 중지 (볼륨 유지)..."
        docker compose down
        success "중지 완료 — DB 데이터는 남아 있습니다. 초기화하려면: clean"
        ;;
    clean)
        warning "볼륨까지 삭제합니다 — 로컬 postgres 데이터가 사라집니다."
        read -rp "  계속할까요? (y/N) " ans
        case "$ans" in
            y|Y)
                docker compose down -v
                success "중지 + 볼륨 삭제 완료"
                ;;
            *)  echo "중단." ;;
        esac
        ;;
    rebuild)
        # SVC 가 비어 있으면 전체 리빌드와 같다 (compose 가 알아서 전체를 잡는다)
        info "다시 빌드해 교체: ${SVC:-전체}"
        # shellcheck disable=SC2086 — SVC 는 단일 서비스명(공백 없음)
        docker compose up -d --build $SVC
        docker compose ps
        ;;
    logs)
        # shellcheck disable=SC2086
        docker compose logs -f --tail=100 $SVC
        ;;
    ps)
        docker compose ps
        ;;
    train)
        info "오프라인 학습 1회 실행 (profiles: tools)..."
        docker compose run --rm ml-train
        ;;
    ""|help|-h|--help)
        usage
        ;;
    *)
        error "알 수 없는 명령: $CMD  (help 로 목록 확인)"
        ;;
esac
