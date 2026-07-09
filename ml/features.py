# 학습·서빙 공유 피처 (train-serve skew 방지)
# train.py(학습)와 predict 서비스(서빙)가 이 모듈 하나만 사용한다.
# FEATURE_COLUMNS 순서가 곧 모델 입력 순서 — 변경 시 모델 재학습 필요.
from datetime import datetime

import pandas as pd

from common.core.constants import ZONE_COORDINATES

# 구역을 안정적 정수 인덱스로 인코딩 (정렬 순서 고정)
ZONE_INDEX: dict[str, int] = {zone: i for i, zone in enumerate(sorted(ZONE_COORDINATES))}

FEATURE_COLUMNS: list[str] = [
    # 구역
    "zone_idx",
    # Time / Calendar Feature
    "hour",
    "weekday",
    "is_weekend",
    "is_rush_hour",
    "is_holiday",
    "month",
    # Weather Feature
    "temperature_c",
    "humidity_pct",
    "rain_mm",
    "precipitation_mm",
    "wind_speed_kmh",
    "cloud_cover_pct",
    "weather_code",
    # Call History Feature (최근 수요)
    "recent_calls_1h",
    "recent_calls_3h",
    "recent_calls_24h",
]

# 한국 고정 공휴일 (월, 일) — 음력 명절은 후속(공휴일 API/라이브러리) 확장 지점
_KR_FIXED_HOLIDAYS = {(1, 1), (3, 1), (5, 5), (6, 6), (8, 15), (10, 3), (10, 9), (12, 25)}

RUSH_HOURS = {7, 8, 9, 17, 18, 19, 20}


def time_features(ts: datetime) -> dict:
    weekday = ts.weekday()
    return {
        "hour": ts.hour,
        "weekday": weekday,
        "is_weekend": 1 if weekday >= 5 else 0,
        "is_rush_hour": 1 if ts.hour in RUSH_HOURS else 0,
        "is_holiday": 1 if (ts.month, ts.day) in _KR_FIXED_HOLIDAYS else 0,
        "month": ts.month,
    }


def build_feature_row(
    zone_id: str,
    target_time: datetime,
    weather: dict | None,
    recent_calls: dict | None,
) -> dict:
    """예측 대상 (구역 × 시각) 1건의 피처를 생성한다.

    weather: {temperature_c, humidity_pct, rain_mm, precipitation_mm,
              wind_speed_kmh, cloud_cover_pct, weather_code} (결측 시 None 허용)
    recent_calls: {recent_calls_1h, recent_calls_3h, recent_calls_24h}
    """
    weather = weather or {}
    recent_calls = recent_calls or {}
    row = {"zone_idx": ZONE_INDEX.get(zone_id, -1)}
    row.update(time_features(target_time))
    for key in (
        "temperature_c", "humidity_pct", "rain_mm", "precipitation_mm",
        "wind_speed_kmh", "cloud_cover_pct", "weather_code",
    ):
        row[key] = weather.get(key)
    for key in ("recent_calls_1h", "recent_calls_3h", "recent_calls_24h"):
        row[key] = recent_calls.get(key, 0)
    return row


def to_dataframe(rows: list[dict]) -> pd.DataFrame:
    """피처 행 목록을 모델 입력 DataFrame으로 변환 (컬럼 순서 고정)."""
    return pd.DataFrame(rows, columns=FEATURE_COLUMNS)
