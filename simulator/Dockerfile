# simulator Dockerfile (멀티스테이지·비루트)
# build context = 레포 루트:
#   docker build -f simulator/Dockerfile -t hailcast/simulator .

FROM python:3.12-slim AS builder
WORKDIR /build
COPY simulator/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SERVICE_NAME=simulator
WORKDIR /app
COPY --from=builder /install /usr/local
# 부하 생성용 k6 바이너리 — 공식 이미지에서 그대로 복사 (apt 저장소/GPG 키 설정 불필요)
COPY --from=grafana/k6:latest /usr/bin/k6 /usr/local/bin/k6
COPY common /app/common
COPY simulator/ /app/
RUN useradd --create-home --uid 10001 appuser
USER appuser
EXPOSE 8001
CMD ["uvicorn", "simulator:app", "--host", "0.0.0.0", "--port", "8001"]
