# 8.2 LightGBM 학습 → S3
from pathlib import Path

import joblib
import lightgbm as lgb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from features import CATEGORICAL_FEATURES, dataframe_to_features

DATA_PATH = Path(__file__).parent / "data" / "nycTaxiWeather.csv"
MODEL_PATH = Path(__file__).parent / "latest_model8.pkl"
LEARNING_CURVE_PATH = Path(__file__).parent / "learning_curve8.png"

VALID_RATIO = 0.15

LGBM_PARAMS = dict(

    objective="regression",
    boosting_type="gbdt",
    n_estimators=8000,
    learning_rate=0.005,
    max_depth=6,
    min_data_in_leaf=20,
    num_leaves=63,
    bagging_fraction=0.9,
    bagging_freq=1,
    lambda_l1=0.0,
    lambda_l2=0.0,
    min_gain_to_split=0.0,
    max_cat_threshold=32,
    random_state=42
)

EARLY_STOPPING_ROUND = 100


def load_dataset() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)
    df["날짜"] = pd.to_datetime(df["날짜"])
    return df.sort_values("날짜").reset_index(drop=True)


def time_based_split(df: pd.DataFrame, valid_ratio: float = VALID_RATIO):
    split_idx = int(len(df) * (1 - valid_ratio))
    return df.iloc[:split_idx], df.iloc[split_idx:]


def plot_learning_curve(model: lgb.LGBMRegressor, path: Path = LEARNING_CURVE_PATH) -> None:
    results = model.evals_result_
    metric = next(iter(next(iter(results.values())).keys()))

    plt.figure(figsize=(8, 5))
    for name, metrics in results.items():
        plt.plot(metrics[metric], label=name)
    plt.axvline(model.best_iteration_, color="gray", linestyle="--", label=f"best_iteration={model.best_iteration_}")
    plt.xlabel("boosting iteration")
    plt.ylabel(metric.upper())
    plt.title("Train vs Valid Learning Curve")
    plt.legend()
    plt.tight_layout()
    plt.savefig(path)
    plt.close()

def train() -> lgb.LGBMRegressor:
    df = load_dataset()
    train_df, valid_df = time_based_split(df)

    X_train, y_train = dataframe_to_features(train_df), train_df["승객수"].astype(float)
    X_valid, y_valid = dataframe_to_features(valid_df), valid_df["승객수"].astype(float)

    model = lgb.LGBMRegressor(**LGBM_PARAMS)
    model.fit(
        X_train,
        y_train,
        eval_set=[(X_train, y_train), (X_valid, y_valid)],
        eval_names=["train", "valid"],
        eval_metric="mae",
        categorical_feature=CATEGORICAL_FEATURES,
        callbacks=[lgb.early_stopping(stopping_rounds=EARLY_STOPPING_ROUND), lgb.log_evaluation(period=200)],
    )
    plot_learning_curve(model)

    pred = model.predict(X_valid, num_iteration=model.best_iteration_)
    mae = mean_absolute_error(y_valid, pred)
    rmse = mean_squared_error(y_valid, pred) ** 0.5
    print(f"valid MAE={mae:.2f} RMSE={rmse:.2f} best_iteration={model.best_iteration_}")

    return model


def save_model(model: lgb.LGBMRegressor, path: Path = MODEL_PATH) -> None:
    joblib.dump(model, path)
def main() -> None:
    model = train()
    save_model(model)


if __name__ == "__main__":
    main()
