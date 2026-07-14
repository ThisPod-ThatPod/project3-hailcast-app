# 학습·서빙 공유 피처 (train-serve skew 방지)
from datetime import datetime

import pandas as pd

FEATURE_COLUMNS = ["hour", "weekday", "is_weekend", "temperature", "humidity", "is_raining"]
CATEGORICAL_FEATURES = ["weekday"] 


def weekday_sunday_zero(dt: datetime) -> int:
    return (dt.weekday() + 1) % 7


def build_features(dt: datetime, temperature: float, humidity: float, is_raining) -> dict:
    weekday = weekday_sunday_zero(dt)
    return {
        "hour": dt.hour,
        "weekday": weekday,
        "is_weekend": int(weekday in (0, 6)),
        "temperature": float(temperature),
        "humidity": float(humidity),
        "is_raining": int(bool(is_raining)),
    }


def to_model_input(features: dict) -> pd.DataFrame:
    return pd.DataFrame([features])[FEATURE_COLUMNS]


def dataframe_to_features(df: pd.DataFrame) -> pd.DataFrame:
    dt = pd.to_datetime(df["날짜"])
    weekday = df["요일"].astype(int)
    out = pd.DataFrame(
        {
            "hour": dt.dt.hour,
            "weekday": weekday,
            "is_weekend": weekday.isin([0, 6]).astype(int),
            "temperature": df["온도"].astype(float),
            "humidity": df["습도"].astype(float),
            "is_raining": df["강수유무"].astype(int),
        }
    )
    return out[FEATURE_COLUMNS]
