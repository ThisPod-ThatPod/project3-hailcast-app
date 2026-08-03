# 공통 구조화 JSON Logger — 전 서비스 공용, print() 대체
import json
import logging
import os
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """로그 레코드를 한 줄 JSON으로 직렬화한다 (CloudWatch/Loki 수집 친화)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service": os.getenv("SERVICE_NAME", "unknown"),
            "message": record.getMessage(),
        }
        # logger.info("...", extra={"event": "...", ...}) 로 넘긴 구조화 필드 병합
        for key, value in record.__dict__.items():
            if key in ("event", "request_id", "queue", "status", "detail", "count", "latency_ms"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


_configured = False


def configure_logging(level: str | None = None) -> None:
    """루트 로거를 stdout JSON 핸들러로 1회 구성한다."""
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level or os.getenv("LOG_LEVEL", "INFO"))
    _configured = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
