# GitOps 테스트를 위한 주석입니다. 테스트 이후 삭제 예정입니다.
# call-api Dockerfile (멀티스테이지·비루트)
# build context = 레포 루트 (common/ 공유 패키지 COPY 필요):
#   docker build -f backend/call-api/Dockerfile -t hailcast/call-api .

FROM python:3.12-slim AS builder
WORKDIR /build
COPY backend/call-api/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SERVICE_NAME=call-api
WORKDIR /app
COPY --from=builder /install /usr/local
COPY backend/common /app/common
COPY backend/call-api/ /app/
RUN useradd --create-home --uid 10001 appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]