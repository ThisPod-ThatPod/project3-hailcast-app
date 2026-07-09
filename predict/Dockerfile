# predict Dockerfile (멀티스테이지·비루트)
# build context = 레포 루트 (common/ + ml/ 공유 모듈 COPY — train-serve skew 방지):
#   docker build -f predict/Dockerfile -t hailcast/predict .
# ml 학습 실행: docker run ... hailcast/predict python ml/train.py --bootstrap

FROM python:3.12-slim AS builder
WORKDIR /build
COPY predict/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
# lightgbm 런타임 의존성 (OpenMP)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SERVICE_NAME=predict \
    PYTHONPATH=/app:/app/ml
WORKDIR /app
COPY --from=builder /install /usr/local
COPY common /app/common
COPY ml /app/ml
COPY predict/ /app/
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /tmp/hailcast-models && chown appuser /tmp/hailcast-models
USER appuser
EXPOSE 8003
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8003"]
