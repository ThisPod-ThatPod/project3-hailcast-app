# weather-cron Dockerfile (멀티스테이지·비루트)
# build context = 레포 루트:
#   docker build -f weather-cron/Dockerfile -t hailcast/weather-cron .
# CronJob 모드로 쓰려면 command를 ["python", "fetch.py", "--once"] 로 교체

FROM python:3.12-slim AS builder
WORKDIR /build
COPY weather-cron/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SERVICE_NAME=weather-cron
WORKDIR /app
COPY --from=builder /install /usr/local
COPY common /app/common
COPY weather-cron/ /app/
RUN useradd --create-home --uid 10001 appuser
USER appuser
EXPOSE 8002
CMD ["python", "fetch.py"]
