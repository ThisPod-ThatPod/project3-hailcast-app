# frontend Dockerfile (멀티스테이지) — 정적 빌드 산출물을 nginx로 서빙
# build context = 레포 루트:
#   docker build -f frontend/Dockerfile -t hailcast/frontend .
#
# ⚠️ 2026-07-20: 운영 서빙 방식(S3+CloudFront vs 이 nginx Pod)은 아직 미확정 —
# 이건 로컬/EKS 양쪽에서 다 쓸 수 있게 만든 컨테이너 이미지일 뿐, 운영에 이 방식을
# 쓴다고 확정된 게 아니다. Vite 환경변수(VITE_*)는 빌드 시점에 고정되므로
# 백엔드 주소가 바뀌면 이미지를 다시 빌드해야 한다(런타임 주입 아님).

FROM node:22-slim AS builder
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./

# 빌드 시점 백엔드 주소 — 미지정 시 로컬 개발 기본값과 동일하게 폴백
ARG VITE_API_BASE_URL=""
ARG VITE_CALL_API_BASE_URL="http://localhost:8000"
ARG VITE_SIMULATOR_BASE_URL="http://localhost:8001"
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_CALL_API_BASE_URL=${VITE_CALL_API_BASE_URL} \
    VITE_SIMULATOR_BASE_URL=${VITE_SIMULATOR_BASE_URL}
RUN npm run build

FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/dist /usr/share/nginx/html
EXPOSE 80
