# 8.2 LightGBM 학습 → S3
# 오프라인 학습 (1회 실행). 실 데이터(calls×weather)가 충분하면 그것으로,
# 부족하면 bootstrap 합성 데이터로 초기 모델을 만들어 S3에 업로드한다.
#   python ml/train.py              # 실 데이터 시도 → 부족 시 bootstrap
#   python ml/train.py --bootstrap  # 합성 데이터 강제
import os
import sys
import tempfile
from datetime import datetime, timezone

os.environ.setdefault("SERVICE_NAME", "ml-train")

import lightgbm as lgb

from common.aws.client_factory import AwsClientFactory
from common.aws.s3_adapter import S3Adapter
from common.core.logger import configure_logging, get_logger
from common.core.settings import BaseAppSettings
from common.db.database import Database

from features import FEATURE_COLUMNS
from preprocess import InsufficientDataError, build_bootstrap_frame, build_training_frame


class TrainSettings(BaseAppSettings):
    service_name: str = "ml-train"
    model_s3_prefix: str = "models"
    s3_auto_create_bucket: bool = False
    bootstrap_days: int = 30
    random_seed: int = 42


def main() -> None:
    settings = TrainSettings()
    configure_logging(settings.log_level)
    logger = get_logger("train")

    force_bootstrap = "--bootstrap" in sys.argv
    source = "bootstrap"
    if force_bootstrap:
        X, y = build_bootstrap_frame(settings.bootstrap_days, settings.random_seed)
    else:
        try:
            db = Database(settings.database_url)
            with db.session_scope() as session:
                X, y = build_training_frame(session)
            source = "database"
        except InsufficientDataError as exc:
            logger.warning(f"insufficient real data ({exc}), falling back to bootstrap")
            X, y = build_bootstrap_frame(settings.bootstrap_days, settings.random_seed)

    logger.info(f"training on {len(X)} rows (source={source})")
    dataset = lgb.Dataset(X, label=y, feature_name=FEATURE_COLUMNS)
    params = {
        "objective": "regression",
        "metric": "mae",
        "num_leaves": 31,
        "learning_rate": 0.08,
        "verbose": -1,
        "seed": settings.random_seed,
    }
    cv = lgb.cv(params, dataset, num_boost_round=300, nfold=4, stratified=False, seed=settings.random_seed)
    # lightgbm은 metric 별칭을 정규화한다 (mae → l1) — "-mean"으로 끝나는 첫 키 사용
    mae_key = next(k for k in cv if k.endswith("-mean"))
    best_rounds = len(cv[mae_key])
    mae = float(cv[mae_key][-1])
    booster = lgb.train(params, dataset, num_boost_round=best_rounds)

    version = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    metadata = {
        "version": version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "rows": len(X),
        "cv_mae": round(mae, 3),
        "num_boost_round": best_rounds,
        "feature_columns": FEATURE_COLUMNS,
    }

    s3 = S3Adapter(
        AwsClientFactory(settings.aws_region, settings.aws_endpoint_url),
        bucket=settings.s3_bucket,
        auto_create=settings.s3_auto_create_bucket,
    )
    with tempfile.TemporaryDirectory() as tmp:
        model_path = os.path.join(tmp, "model.txt")
        booster.save_model(model_path)
        prefix = settings.model_s3_prefix
        # 버전 보관 + latest 갱신 (Forecast는 항상 latest를 사용)
        for target in (f"{prefix}/{version}", f"{prefix}/latest"):
            s3.upload_file(f"{target}/model.txt", model_path)
            s3.upload_json(f"{target}/metadata.json", metadata)
    logger.info(
        f"model uploaded (version={version}, cv_mae={mae:.3f}, rounds={best_rounds})",
        extra={"event": "model_uploaded", "detail": metadata},
    )


if __name__ == "__main__":
    main()
