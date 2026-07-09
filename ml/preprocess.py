# 8.1 전처리
# 실 데이터(calls × weather) → 학습 데이터셋. 데이터가 부족하면 train.py가 bootstrap으로 대체한다.
import math
import random
from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from common.db.entities import Call, Weather

from features import RUSH_HOURS, build_feature_row

# 실 데이터 학습에 필요한 최소 (zone × hour) 표본 수
MIN_TRAINING_ROWS = 500


class InsufficientDataError(Exception):
    pass


def build_training_frame(session: Session) -> tuple[pd.DataFrame, pd.Series]:
    """DB의 콜 이력을 zone × 1시간 버킷으로 집계해 학습 데이터셋을 만든다."""
    hour_bucket = func.date_trunc("hour", Call.requested_at).label("bucket")
    stmt = (
        select(Call.zone_id, hour_bucket, func.count(Call.id).label("demand"))
        .where(Call.zone_id.isnot(None))
        .group_by(Call.zone_id, hour_bucket)
    )
    demand_rows = session.execute(stmt).all()
    if len(demand_rows) < MIN_TRAINING_ROWS:
        raise InsufficientDataError(
            f"only {len(demand_rows)} zone-hour samples (< {MIN_TRAINING_ROWS})"
        )

    # 시간별 수요 lookup — lag(recent_calls_*) 계산용
    demand_by_key = {(z, b): d for z, b, d in demand_rows}

    def recent(zone: str, bucket: datetime) -> dict:
        return {
            "recent_calls_1h": demand_by_key.get((zone, bucket - timedelta(hours=1)), 0),
            "recent_calls_3h": sum(
                demand_by_key.get((zone, bucket - timedelta(hours=h)), 0) for h in (1, 2, 3)
            ),
            "recent_calls_24h": demand_by_key.get((zone, bucket - timedelta(hours=24)), 0),
        }

    weather_rows = session.execute(select(Weather).where(Weather.data_type == "current")).scalars()
    weather_by_key: dict[tuple[str, datetime], dict] = {}
    for w in weather_rows:
        bucket = w.observed_at.replace(minute=0, second=0, microsecond=0)
        weather_by_key[(w.zone_id, bucket)] = {
            "temperature_c": w.temperature_c,
            "humidity_pct": w.humidity_pct,
            "rain_mm": w.rain_mm,
            "precipitation_mm": w.precipitation_mm,
            "wind_speed_kmh": w.wind_speed_kmh,
            "cloud_cover_pct": w.cloud_cover_pct,
            "weather_code": w.weather_code,
        }

    feature_rows, targets = [], []
    for zone, bucket, demand in demand_rows:
        feature_rows.append(
            build_feature_row(zone, bucket, weather_by_key.get((zone, bucket)), recent(zone, bucket))
        )
        targets.append(demand)
    from features import to_dataframe

    return to_dataframe(feature_rows), pd.Series(targets, name="demand")


# ---------------- Bootstrap (합성 데이터) ----------------
# 서비스 초기에 실 데이터가 부족할 때 그럴듯한 수요 곡선으로 초기 모델을 만든다.
_ZONE_BASE = {
    "gangnam": 22, "hongdae": 15, "jongno": 12, "yeouido": 11, "jamsil": 10,
    "itaewon": 8, "seongsu": 8, "mapo": 7, "guro": 7,
}


def _synthetic_demand(zone: str, ts: datetime, rain_mm: float, rng: random.Random) -> float:
    base = _ZONE_BASE.get(zone, 8)
    # 시간대 곡선: 출퇴근 피크 + 심야 하락
    hour_factor = 1.6 if ts.hour in RUSH_HOURS else (0.3 if 1 <= ts.hour <= 5 else 1.0)
    # 주말: 업무지구 하락, 유흥가 상승 근사
    weekend_factor = 0.8 if ts.weekday() >= 5 else 1.0
    if ts.weekday() >= 5 and zone in ("hongdae", "itaewon", "jamsil"):
        weekend_factor = 1.3
    # 비가 오면 택시 수요 증가
    rain_factor = 1.0 + min(rain_mm * 0.15, 0.6)
    noise = rng.gauss(1.0, 0.15)
    return max(0.0, base * hour_factor * weekend_factor * rain_factor * noise)


def build_bootstrap_frame(days: int = 30, seed: int = 42) -> tuple[pd.DataFrame, pd.Series]:
    rng = random.Random(seed)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    feature_rows, targets = [], []
    demand_history: dict[tuple[str, datetime], float] = {}
    for step in range(days * 24, 0, -1):
        ts = now - timedelta(hours=step)
        # 합성 날씨: 완만한 일교차 + 간헐적 강수
        rain = round(max(0.0, rng.gauss(0, 1.2)), 1) if rng.random() < 0.2 else 0.0
        weather = {
            "temperature_c": round(22 + 6 * math.sin((ts.hour - 6) / 24 * 2 * math.pi) + rng.gauss(0, 1), 1),
            "humidity_pct": round(min(100, max(20, rng.gauss(70, 12))), 0),
            "rain_mm": rain,
            "precipitation_mm": rain,
            "wind_speed_kmh": round(abs(rng.gauss(8, 4)), 1),
            "cloud_cover_pct": round(min(100, max(0, rng.gauss(60, 25))), 0),
            "weather_code": 61 if rain > 0 else rng.choice([0, 1, 2, 3]),
        }
        for zone in _ZONE_BASE:
            demand = _synthetic_demand(zone, ts, rain, rng)
            demand_history[(zone, ts)] = demand
            recent = {
                "recent_calls_1h": demand_history.get((zone, ts - timedelta(hours=1)), 0),
                "recent_calls_3h": sum(
                    demand_history.get((zone, ts - timedelta(hours=h)), 0) for h in (1, 2, 3)
                ),
                "recent_calls_24h": demand_history.get((zone, ts - timedelta(hours=24)), 0),
            }
            feature_rows.append(build_feature_row(zone, ts, weather, recent))
            targets.append(demand)
    from features import to_dataframe

    return to_dataframe(feature_rows), pd.Series(targets, name="demand")
