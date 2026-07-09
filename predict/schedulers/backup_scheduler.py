# Backup Scheduler — Stub (Part 2 설계 예약). 향후 Prediction/Weather 데이터 백업에 사용.
from common.core.logger import get_logger
from common.core.scheduler import IntervalScheduler

logger = get_logger("backup_scheduler")


class BackupScheduler(IntervalScheduler):
    name = "backup_scheduler"

    async def run_once(self) -> None:
        # TODO: RDS 스냅샷/S3 아카이브 백업 로직 (후속 Part)
        logger.info("backup scheduler stub run", extra={"event": "backup_stub"})
