# AccuracyCheckService — 대조 스케줄러 Business Logic (C10 후속)
# PredictionAccuracyLogger(DI, dependencies.py)는 "공책과 펜"만 조립돼 있고, 예측 vs 실측을
# 시간 정렬해서 실제로 비교·기록하는 주체가 없었다(dependencies.py:196-198 주석 참고).
# 이 서비스가 그 대조 주체 — AccuracyCheckScheduler가 매시 :59분(정시 직전, 그 시간의
# 실측이 거의 다 쌓인 시점)에 호출한다.
from datetime import datetime, timezone

from common.core.logger import get_logger
from common.core.store import FileStore

from config import PredictSettings
from services.prediction_accuracy_logger import PredictionAccuracyLogger
from services.scaler_service import ScalerService

logger = get_logger("accuracy_check_service")


def _floor_to_hour(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


class AccuracyCheckService:
    def __init__(
        self,
        scaler: ScalerService,
        store: FileStore,
        settings: PredictSettings,
        accuracy_logger: PredictionAccuracyLogger | None,
    ):
        self._scaler = scaler
        self._store = store
        self._settings = settings
        self._accuracy_logger = accuracy_logger

    def _read_actual_demand(self) -> float | None:
        """실측 수요 — G2(scaler_service.py `_read_actual_traffic`)와 반드시 같은 정의를
        쓴다. "실제 수요"의 정의가 두 군데로 갈리면 어긋난다(INSIGHT-1과 같은 종류의 함정).
        dashboard/traffic.json의 hourly_requests는 최근 1시간 트래픽 합계라, 이 스케줄러가
        매시 :59분(정시가 거의 다 됐을 때)에 도는 것과 맞물려 "이번 시간창 실측 총합"의
        근사치로 쓸 수 있다.
        """
        body = self._store.read_json(self._settings.traffic_json_key)
        if not body:
            return None
        return body.get("hourly_requests")

    def check_and_record(self) -> None:
        """이번 시간창의 예측 vs 실측을 비교해서, 오차가 크면 오답노트에 1건 기록한다.

        기능이 꺼져 있으면(PREDICTION_ACCURACY_LOG_ENABLED=false) accuracy_logger가
        None이라 바로 반환 — dependencies.py의 on/off 관례를 그대로 따른다.
        """
        if self._accuracy_logger is None:
            return

        predicted = self._scaler.last_predicted_demand
        if predicted is None:
            logger.info(
                "no predicted demand yet, accuracy check skipped",
                extra={"event": "accuracy_check_skipped"},
            )
            return

        actual = self._read_actual_demand()
        if actual is None:
            logger.info(
                "no actual traffic data yet, accuracy check skipped",
                extra={"event": "accuracy_check_skipped"},
            )
            return

        target_time = _floor_to_hour(datetime.now(timezone.utc))
        recorded = self._accuracy_logger.record_if_needed(target_time, predicted, actual)
        logger.info(
            f"accuracy check done (predicted={predicted:g}, actual={actual:g}, recorded={recorded})",
            extra={
                "event": "accuracy_check_done",
                "detail": {"predicted": predicted, "actual": actual, "recorded": recorded},
            },
        )
