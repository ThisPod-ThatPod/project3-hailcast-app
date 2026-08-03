from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from features import dataframe_to_features

MODEL_PATH = Path(__file__).parent / "latest_model8.pkl"
INPUT_PATH = Path(__file__).parent / "data" / "dummy_predict_input_7_8월.csv"
OUTPUT_PATH = Path(__file__).parent / "data" / "dummy_predict_output_7_8월_v3.csv"

HOURLY_REFERENCE = {
    0: 70677, 2: 40145, 4: 33208, 6: 43148,
    8: 70402, 10: 73592, 12: 72568, 14: 71678,
    16: 70674, 18: 73416, 20: 80999, 22: 86364,
}

DAWN_BUCKETS = (0, 2, 4, 6)
BUCKET_DAMPING = {b: 0.85 for b in DAWN_BUCKETS}
BUCKET_DAMPING.update({b: 0.15 for b in (8, 10, 12, 14, 16, 18, 20, 22)})


def load_model(path: Path = MODEL_PATH):
    return joblib.load(path)


def load_input(path: Path = INPUT_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["날짜"] = pd.to_datetime(df["날짜"])
    return df.sort_values("날짜").reset_index(drop=True)


def _hour_bucket(dates: pd.Series) -> pd.Series:
    return (dates.dt.hour // 2) * 2


def compute_correction_factors(
    dates: pd.Series,
    raw_pred: np.ndarray,
    reference: dict = HOURLY_REFERENCE,
    bucket_damping: dict = BUCKET_DAMPING,
) -> pd.Series:
    bucket = _hour_bucket(dates)

    ref = pd.Series(reference).sort_index()
    ref_shape = ref / ref.mean()

    model_avg = pd.Series(np.asarray(raw_pred), index=dates.index).groupby(bucket).mean()
    model_shape = model_avg / model_avg.mean()

    ratio = (ref_shape / model_shape).reindex(ref_shape.index).fillna(1.0)
    damping = pd.Series(bucket_damping).reindex(ref_shape.index).fillna(0.0)
    return 1 + damping * (ratio - 1)


def predict(df: pd.DataFrame, model) -> pd.DataFrame:
    X = dataframe_to_features(df)
    raw_pred = model.predict(X).clip(min=0)

    factor_by_bucket = compute_correction_factors(df["날짜"], raw_pred)
    bucket = _hour_bucket(df["날짜"])
    correction = bucket.map(factor_by_bucket).to_numpy()

    corrected_pred = (raw_pred * correction).clip(min=0)

    print("시간대별 보정계수 (1보다 크면 상향, 작으면 하향):")
    print(factor_by_bucket.round(3).to_string())

    out = df[["날짜", "요일"]].copy()
    out["예측승객수"] = corrected_pred.round().astype(int)
    return out


def main() -> None:
    model = load_model()
    df = load_input()
    result = predict(df, model)
    result.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")
    print(f"저장 완료: {OUTPUT_PATH} ({len(result)}행)")


if __name__ == "__main__":
    main()
