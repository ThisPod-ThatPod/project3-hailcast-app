# AccuracyCheckService — 대조 스케줄러 Business Logic (C10 후속)
# PredictionAccuracyLogger(DI, dependencies.py)는 "공책과 펜"만 조립돼 있고, 예측 vs 실측을
# 시간 정렬해서 실제로 비교·기록하는 주체가 없었다(dependencies.py:196-198 주석 참고).
# 이 서비스가 그 대조 주체 — AccuracyCheckScheduler가 매시 :59분(정시 직전, 그 시간의
# 실측이 거의 다 쌓인 시점)에 호출한다.
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from common.core.logger import get_logger
from common.core.store import FileStore
from common.models.prediction import PredictionItem

from config import PredictSettings
from services.prediction_accuracy_logger import PredictionAccuracyLogger
from services.prediction_reader import PredictionReader
from services.scaler_service import ScalerService

logger = get_logger("accuracy_check_service")

# ml/features.py::weekday_sunday_zero, weather_service.py와 반드시 같은 공식(일=0)이어야
# 학습 데이터와 어긋나지 않는다.
NYC_TZ = ZoneInfo("America/New_York")


def _floor_to_hour(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


def _weekday_sunday_zero(dt: datetime) -> int:
    return (dt.weekday() + 1) % 7


class AccuracyCheckService:
    def __init__(
        self,
        scaler: ScalerService,
        reader: PredictionReader,
        store: FileStore,
        settings: PredictSettings,
        accuracy_logger: PredictionAccuracyLogger | None,
    ):
        self._scaler = scaler
        self._reader = reader
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

    def _find_weather_item(self, target_time: datetime) -> PredictionItem | None:
        """last_predicted_demand(scaler_service `_current_demand`와 동일 매칭 로직)가
        고른 것과 같은 시간창의 날씨를 찾는다 — 최신 문서에서 target_time에 가장 가까운
        항목을 tolerance 안에서 매칭한다."""
        document = self._reader.read_latest()
        if document is None or not document.predictions:
            return None
        closest = min(document.predictions, key=lambda item: abs(item.target_time - target_time))
        tolerance = timedelta(minutes=self._settings.prediction_window_minutes)
        if abs(closest.target_time - target_time) > tolerance:
            return None
        return closest

    def check_and_record(self) -> None:
        """이번 시간창의 예측 vs 실측을 비교해서, 실측이 예측을 초과하고 오차가 크면
        재학습 입력 스키마(날짜·요일·온도·습도·강수유무·승객수)로 오답노트에 기록한다.

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
        weather = self._find_weather_item(target_time)
        local = target_time.astimezone(NYC_TZ)

        recorded = self._accuracy_logger.record_if_needed(
            target_time,
            predicted,
            actual,
            local_date=local.strftime("%Y-%m-%d %H:%M:%S"),
            weekday=_weekday_sunday_zero(local),
            temperature=weather.temperature if weather else None,
            humidity=weather.humidity if weather else None,
            is_raining=weather.is_raining if weather else None,
        )
        logger.info(
            f"accuracy check done (predicted={predicted:g}, actual={actual:g}, recorded={recorded})",
            extra={
                "event": "accuracy_check_done",
                "detail": {"predicted": predicted, "actual": actual, "recorded": recorded},
            },
        )
