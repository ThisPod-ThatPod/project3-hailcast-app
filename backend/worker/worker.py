# 7.2 워커 (SQS 소비, KEDA 대상)
# Entry Point — SIGTERM(Pod 종료) 시 현재 배치까지 처리하고 정상 종료한다.
import os
import signal

os.environ.setdefault("SERVICE_NAME", "worker")

from common.core.logger import configure_logging, get_logger

from config import get_settings
from dependencies import build_worker_service, get_database


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = get_logger("worker")

    get_database().init_schema()
    service = build_worker_service()

    def handle_sigterm(signum, frame):
        logger.info("shutdown signal received", extra={"event": "worker_stop"})
        service.stop()

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    service.run_forever()


if __name__ == "__main__":
    main()
