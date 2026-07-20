#!/bin/bash
# =============================================================
# 파일위치 : project3-hailcast-app/scripts/_lib.sh
# 이 Pod 저 Pod · hailcast — app 스크립트 공용 상수·출력 함수·계정 가드
# 사용    : source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
#
# ⚠️ 리전·서비스 목록·ECR 이름 규칙은 여기 한 곳에서만 고친다.
#    스크립트마다 흩어 두면 하나만 고치고 나머지가 낡는다.
#
# ⚠️ ops 의 _lib.sh 와 달리, PROJECT_ACCOUNT_ID 가 없어도 source 시점엔 죽지 않는다.
#    dev_local.sh(로컬 docker compose)는 AWS 자격증명이 아예 필요 없는 작업이라,
#    여기서 죽이면 로컬 테스트가 .env 없이는 안 되는 이상한 상황이 된다.
#    → AWS 를 만지는 스크립트(build_push.sh)만 require_project_account_id 를 명시 호출한다.
#    (ops 가 infra-fmt 에 가드를 일부러 뺀 것과 같은 논리)
# =============================================================

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── 프로젝트 상수 (네이밍규약서 §2 · §5-2) ─────────────────
AWS_REGION="${AWS_REGION:-ap-northeast-2}"     # 서울
PROJECT_NAME="hailcast"
ENVIRONMENT="dev"
NAME_PREFIX="${PROJECT_NAME}-${ENVIRONMENT}"   # hailcast-dev

# ECR 리포지토리 이름 = ${NAME_PREFIX}-<서비스> (규약서 §5-2)
# frontend 는 서빙 방식(nginx 파드) 확정 후 추가 — Dockerfile 이 아직 없다.
DEFAULT_SERVICES="call-api predict worker weather-cron simulator"

# ── 색상 출력 함수 ─────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}    $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC}   $1" >&2; exit 1; }

# ── PROJECT_ACCOUNT_ID 로딩 ────────────────────────────────
# ⚠️⚠️ .env 를 `source` 하지 않는다. PROJECT_ACCOUNT_ID '한 줄만' 파싱한다.
#    source 하면 .env 의 다른 변수(AWS_PROFILE 등)가 가드와 실제 도구의 자격증명을
#    가르거나, 함수 정의로 가드를 통째로 속일 수 있다(ops _lib.sh 주석 참조 — 실증됨).
# → 환경변수가 이미 있으면 파일을 아예 보지 않는다 (CI 의 GitHub Secret 이 항상 이긴다).
# ⚠️ 계정 ID 는 반드시 '문자열'로 다룬다. 앞자리 0 이 숫자 비교에서 날아가면 대조가 항상 실패한다.
if [ -z "${PROJECT_ACCOUNT_ID:-}" ] && [ -f "$APP_ROOT/.env" ]; then
    PROJECT_ACCOUNT_ID="$(
        grep -E '^[[:space:]]*PROJECT_ACCOUNT_ID[[:space:]]*=' "$APP_ROOT/.env" \
        | tail -n 1 | cut -d= -f2- | tr -d "\"' \t\r"
    )"
fi
PROJECT_ACCOUNT_ID="${PROJECT_ACCOUNT_ID:-}"

# AWS 를 만지는 스크립트가 시작 전에 명시적으로 부른다. 없으면 여기서 끊는다.
require_project_account_id() {
    if [ -z "$PROJECT_ACCOUNT_ID" ]; then
        echo "❌ PROJECT_ACCOUNT_ID 가 없습니다." >&2
        echo "   로컬 :  cp .env.example .env   → 계정 ID 를 채웁니다 (값은 팀 채널에서)." >&2
        echo "   CI   :  GitHub Secret 을 환경변수 PROJECT_ACCOUNT_ID 로 주입하십시오(.env 파일 불필요)." >&2
        # 조용히 통과시키면 계정 대조 없이 도는 셈 — 이 가드가 막으려던 사고를 스스로 저지른다.
        exit 1
    fi
}

# ── 계정 가드 ──────────────────────────────────────────────
# 지금 자격증명이 프로젝트 계정인지 대조한다. (ops scripts/_lib.sh 와 같은 계약)
# 반환값: 0 = 맞음 / 1 = 다른 계정 / 2 = 자격증명 없음·만료
# 부수효과: CURRENT_ACCOUNT 에 조회된 계정 ID 를 담는다 (호출자 메시지용)
verify_project_account() {
    CURRENT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) || {
        CURRENT_ACCOUNT=""
        return 2
    }
    [ -n "$CURRENT_ACCOUNT" ] || return 2
    [ "$CURRENT_ACCOUNT" = "$PROJECT_ACCOUNT_ID" ]
}

# 가드 결과를 사람이 읽을 메시지로 바꿔 주는 래퍼. 통과 못 하면 exit 1.
guard_project_account() {
    require_project_account_id
    local rc=0
    verify_project_account || rc=$?
    case "$rc" in
        0)
            success "프로젝트 계정 확인 : ${CURRENT_ACCOUNT}"
            ;;
        1)
            echo -e "${RED}❌ 프로젝트 계정이 아닙니다 → 현재 ${CURRENT_ACCOUNT} / 기대 ${PROJECT_ACCOUNT_ID}${NC}" >&2
            echo "   이대로 push 하면 엉뚱한 계정의 ECR 에 이미지를 올립니다. 중단합니다." >&2
            echo "   지금 무엇이 잡혀 있는지 확인:  aws sts get-caller-identity" >&2
            echo "   ⚠️ 환경변수(AWS_ACCESS_KEY_ID)는 프로필·[default] 보다 우선합니다 — 설정돼 있으면 unset 하십시오." >&2
            exit 1
            ;;
        *)
            echo -e "${RED}❌ AWS 자격증명이 없거나 만료됐습니다${NC}" >&2
            echo "   중단합니다. ops 레포에서  make setup  으로 먼저 등록하세요." >&2
            exit 1
            ;;
    esac
}
