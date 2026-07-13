# worker Dockerfile (멀티스테이지·비루트)
# build context = 레포 루트:
#   docker build -f backend/worker/Dockerfile -t hailcast/worker .

FROM python:3.12-slim AS builder
WORKDIR /build
COPY backend/worker/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SERVICE_NAME=worker
WORKDIR /app
COPY --from=builder /install /usr/local
COPY backend/common /app/common
COPY backend/worker/ /app/
RUN useradd --create-home --uid 10001 appuser
USER appuser
CMD ["python", "worker.py"]
