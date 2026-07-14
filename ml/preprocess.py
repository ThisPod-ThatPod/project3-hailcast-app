# 8.1 전처리
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).parent / "data"
RAW_PATH = DATA_DIR / "nycTaxiDataset.csv"
OUT_PATH = DATA_DIR / "nycTaxiWeather.csv"

NYC_LATITUDE = 40.7128
NYC_LONGITUDE = -74.0060
TIMEZONE = "America/New_York"

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HOURLY_VARS = ["temperature_2m", "relative_humidity_2m", "precipitation"]


def load_taxi_data(path: Path = RAW_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=["pickup_timestamp", "passenger_count"])
    df["pickup_timestamp"] = pd.to_datetime(df["pickup_timestamp"])
    return df


def fetch_weather(start_date: str, end_date: str) -> pd.DataFrame:
    """Open-Meteo Archive API에서 시간 단위 날씨를 받아온다."""
    resp = requests.get(
        ARCHIVE_URL,
        params={
            "latitude": NYC_LATITUDE,
            "longitude": NYC_LONGITUDE,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": ",".join(HOURLY_VARS),
            "timezone": TIMEZONE,
        },
        timeout=60,
    )
    resp.raise_for_status()
    hourly = resp.json()["hourly"]

    weather = pd.DataFrame(
        {
            "hour": pd.to_datetime(hourly["time"]),
            "temperature": hourly["temperature_2m"],
            "humidity": hourly["relative_humidity_2m"],
            "precipitation": hourly["precipitation"],
        }
    )
    return weather


def weekday_sunday_zero(dt: pd.Series) -> pd.Series:
    """일요일=0, 월=1, ... 토=6 (pandas dt.weekday는 월=0 기준이라 보정)."""
    return (dt.dt.weekday + 1) % 7


def build_dataset(taxi_df: pd.DataFrame, weather_df: pd.DataFrame) -> pd.DataFrame:
    merged = taxi_df.copy()
    merged["hour"] = merged["pickup_timestamp"].dt.floor("h")
    merged = merged.merge(weather_df, on="hour", how="left")

    if merged[["temperature", "humidity", "precipitation"]].isna().any().any():
        missing = merged[merged["temperature"].isna()]["pickup_timestamp"].tolist()
        raise ValueError(f"날씨 미매칭 타임스탬프 {len(missing)}건: {missing[:5]} ...")

    out = pd.DataFrame(
        {
            "날짜": merged["pickup_timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S"),
            "요일": weekday_sunday_zero(merged["pickup_timestamp"]),
            "승객수": merged["passenger_count"].astype(int),
            "온도": merged["temperature"].round(1),
            "습도": merged["humidity"].round().astype(int),
            "강수유무": (merged["precipitation"] > 0).astype(int),
        }
    )
    return out


def main() -> None:
    taxi_df = load_taxi_data()

    start_date = taxi_df["pickup_timestamp"].min().strftime("%Y-%m-%d")
    end_date = taxi_df["pickup_timestamp"].max().strftime("%Y-%m-%d")
    weather_df = fetch_weather(start_date, end_date)

    result = build_dataset(taxi_df, weather_df)
    result.to_csv(OUT_PATH, index=False, encoding="utf-8")
    print(f"저장 완료: {OUT_PATH} ({len(result)}행)")


if __name__ == "__main__":
    main()
