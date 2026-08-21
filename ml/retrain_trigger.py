# 수동 재학습 트리거 — 오답노트(DynamoDB)가 일정량 쌓이면, S3의 기존 모델에 "이어학습"한다.
#
# [2026-08-20] 원본 학습 CSV(ml/data/)는 .gitignore 대상이라 어떤 이미지에도 안 들어있어서
# (로컬 개발자 PC 밖에는 존재하지 않음) — from-scratch 재학습은 파드/CI 어디서도 못 돌린다.
# 그래서 "S3에 있는 기존 모델을 불러와서, 오답노트 데이터만으로 이어서 부스팅한다" 방식으로
# 바꿨다. LightGBM sklearn API의 init_model 파라미터로 기존 트리 위에 새 트리를 추가하는
# continued-training — 원본 데이터가 없어도, 이미 학습된 모델 파일과 오답노트만 있으면 된다.
#
# ⚠️ 오답노트가 적을 때 그대로 학습하면 그 몇 건에 극심하게 과적합된다. 그래서
# MIN_RECORDS_FOR_TRAINING건 미만이면 기본적으로 학습을 안 하고 현황만 보여준다.
# --force로 미만이어도 강행할 수 있지만(파이프라인 자체 검증용), 실제 운영 판단으로 쓰면 안 된다.
#
# [2026-08-20] "학습여부"(0/1) 필터링 추가 — 이미 이전 배치에서 학습에 쓴 레코드는 다시
# 안 쓴다. 이전 스키마(날씨 필드 없음)로 남은 레거시 레코드는 개별적으로 건너뛴다(배치
# 전체를 실패시키지 않음).
#
# 실행 방식(수동 vs 자동 스케줄)은 팀 결정 사항(§ 2026-08-20-retrain-pipeline-status.md) —
# 이 스크립트는 어느 쪽이든(사람이 CLI로 직접 실행하거나, K8s CronJob의 entrypoint로) 그대로
# 쓸 수 있게 실행 위치·트리거 방식에 대한 가정을 두지 않는다.
import argparse
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

import joblib
import lightgbm as lgb
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from common.aws.client_factory import AwsClientFactory
from common.aws.dynamodb_adapter import DynamoDbAdapter
from common.aws.s3_adapter import S3Adapter
from common.core.settings import BaseAppSettings

from features import dataframe_to_features
from train import LGBM_PARAMS

MIN_RECORDS_FOR_TRAINING = 20   # 이 미만이면 과적합 위험이 커서 기본적으로 학습 안 함
# [2026-08-21 확정, 이창원] 이어학습 시 추가할 트리 수 — 원본(8000)과 별개로 작게 잡는다.
# MIN_RECORDS_FOR_TRAINING(20건) 규모의 배치에서 과적합을 피하려면 원본만큼 키울 이유가
# 없다 — 담당자 재량으로 30 확정(팀 별도 논의 없이 종료).
CONTINUED_N_ESTIMATORS = 30
# [2026-08-21, 이창원] LGBM_PARAMS의 min_data_in_leaf=20을 이어학습에 그대로 물려받으면,
# 스플릿 한 번에 양쪽 리프가 각각 20개는 있어야 해서 실제로는 배치가 40건을 넘어도(라이브
# 검증 완료 — 40건에서도 "No further splits with positive gain"으로 트리가 0개 추가됨)
# 여전히 스플릿이 거의 안 된다. MIN_RECORDS_FOR_TRAINING(20건) 규모 배치를 실제로 반영하려면
# 훨씬 작아야 한다 — 대신 너무 작으면(1~5 등) 오답노트 개별 건 노이즈에 트리가 과적합될
# 위험이 커서, "학습이 되긴 하되 소량 표본에 덜 민감한" 절충값으로 8을 잡는다.
CONTINUED_MIN_DATA_IN_LEAF = 8
REQUIRED_COLUMNS = ["날짜", "요일", "온도", "습도", "강수유무", "승객수"]
LOCAL_MODEL_PATH = "/tmp/hailcast-current-model.pkl"
LOCAL_NEW_MODEL_PATH = "/tmp/hailcast-continued-model.pkl"


class RetrainTriggerSettings(BaseAppSettings):
    service_name: str = "ml-retrain-trigger"
    # predict/config.py의 prediction_accuracy_table_name과 반드시 같은 값이어야 한다.
    prediction_accuracy_table_name: str = "hailcast-dev-prediction-log"
    model_s3_prefix: str = "models"
    ml_s3_upload_enabled: bool = False   # train.py와 동일 관례 — 명시적으로 켜야 S3에 씀


def _decode(item: dict) -> dict:
    """DynamoDB AttributeValue 형식({"S": ...}/{"N": ...})을 평문 dict로 변환."""
    out = {}
    for key, value in item.items():
        if "S" in value:
            out[key] = value["S"]
        elif "N" in value:
            out[key] = Decimal(value["N"])
        else:
            out[key] = value
    return out


def fetch_accuracy_log(dynamodb: DynamoDbAdapter) -> list[dict]:
    return [_decode(item) for item in dynamodb.scan_all()]


def filter_untrained(items: list[dict]) -> list[dict]:
    """학습여부가 없거나(구버전 레코드) 0인 것만 — 이미 1(학습에 씀)인 건 제외."""
    return [item for item in items if int(item.get("학습여부", 0)) == 0]


def split_usable(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """학습 필수 컬럼이 다 있는 것만 usable로, 없으면 skip(배치 전체를 실패시키지 않음)."""
    usable, skipped = [], []
    for item in items:
        if all(col in item for col in REQUIRED_COLUMNS):
            usable.append(item)
        else:
            skipped.append(item)
    return usable, skipped


def summarize(items: list[dict], label: str = "오답노트") -> None:
    print(f"{label} {len(items)}건")
    if not items:
        return
    items = sorted(items, key=lambda r: r.get("target_time", ""))
    for row in items[-10:]:
        print(
            f"  {row.get('target_time')}  predicted={row.get('predicted_demand')}  "
            f"actual={row.get('actual_demand')}  diff={row.get('diff')}"
        )
    if len(items) > 10:
        print(f"  ... 외 {len(items) - 10}건 (최근 10건만 표시)")


def continue_train(items: list[dict], s3: S3Adapter, settings: RetrainTriggerSettings):
    """S3의 기존 모델을 불러와 오답노트 데이터로 이어학습한다. (새 모델, MAE, RMSE)를 반환.

    MAE/RMSE는 학습에 쓴 데이터 자체에 대한 in-sample 지표다 — MIN_RECORDS_FOR_TRAINING(20건)
    수준의 배치를 또 쪼개 held-out validation을 만들면 몇 건 안 남아 지표 자체가 무의미해진다.
    일반화 성능 검증용이 아니라, 재학습 회차마다 Grafana에서 추세(급격한 악화 등)를 보기 위한
    관측 지표로만 쓴다.
    """
    df = pd.DataFrame(items)
    X = dataframe_to_features(df)
    y = df["승객수"].astype(float)

    os.makedirs(os.path.dirname(LOCAL_MODEL_PATH), exist_ok=True)
    s3.download_file(f"{settings.model_s3_prefix}/latest/model.pkl", LOCAL_MODEL_PATH)
    base_model = joblib.load(LOCAL_MODEL_PATH)
    print(f"기존 모델 로드 완료 (기존 트리 수: {base_model.booster_.num_trees()})")

    continued_params = dict(LGBM_PARAMS)
    continued_params["n_estimators"] = CONTINUED_N_ESTIMATORS
    continued_params["min_data_in_leaf"] = CONTINUED_MIN_DATA_IN_LEAF
    new_model = lgb.LGBMRegressor(**continued_params)
    new_model.fit(X, y, init_model=base_model.booster_)
    print(f"이어학습 완료 (전체 트리 수: {new_model.booster_.num_trees()})")

    pred = new_model.predict(X)
    # float() 캐스팅 필수 — sklearn 지표는 numpy.float64를 반환하는데, S3Adapter.upload_json이
    # 쓰는 json.dumps는 이를 못 다뤄서 default=str로 빠져 숫자가 아니라 문자열로 직렬화된다
    # (Grafana가 숫자 메트릭으로 못 읽음).
    mae = float(mean_absolute_error(y, pred))
    rmse = float(mean_squared_error(y, pred) ** 0.5)
    print(f"in-sample MAE={mae:.2f} RMSE={rmse:.2f}")
    return new_model, mae, rmse


def upload_continued_model(
    model, mae: float, rmse: float, settings: RetrainTriggerSettings, record_count: int
) -> None:
    if not settings.ml_s3_upload_enabled:
        print("ML_S3_UPLOAD_ENABLED=false — S3 업로드 스킵 (로컬 저장만 함)")
        joblib.dump(model, LOCAL_NEW_MODEL_PATH)
        print(f"로컬 저장: {LOCAL_NEW_MODEL_PATH}")
        return

    joblib.dump(model, LOCAL_NEW_MODEL_PATH)
    factory = AwsClientFactory(settings.aws_region, settings.aws_endpoint_url)
    s3 = S3Adapter(factory, bucket=settings.s3_bucket)
    version = f"continued-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    prefix = f"{settings.model_s3_prefix}/latest"
    s3.upload_file(f"{prefix}/model.pkl", LOCAL_NEW_MODEL_PATH)
    s3.upload_json(
        f"{prefix}/metadata.json",
        {
            "version": version,
            "continued_training_records": record_count,
            "trained_at": version,
            # Grafana(Infinity)가 이 metadata.json을 긁어서 재학습 회차별 추세를 보여준다 —
            # from-scratch 학습(train.py)이 로컬에서 그리던 학습곡선 PNG를 대신함.
            "mae": mae,
            "rmse": rmse,
        },
    )
    print(f"S3 업로드 완료 (version={version}, mae={mae:.2f}, rmse={rmse:.2f})")


def mark_used_as_trained(items: list[dict], dynamodb: DynamoDbAdapter) -> None:
    for item in items:
        dynamodb.mark_trained(item["prediction_date"], item["target_time"])
    print(f"학습여부=1로 마킹 완료 ({len(items)}건) — 다음 배치에서 재사용 안 됨")


def main() -> None:
    parser = argparse.ArgumentParser(description="오답노트 현황을 확인하고, 쌓였으면 기존 모델에 이어학습한다.")
    parser.add_argument(
        "--force",
        action="store_true",
        help=f"오답노트가 {MIN_RECORDS_FOR_TRAINING}건 미만이어도 이어학습을 강행한다(파이프라인 검증용 — 과적합 위험 인지하고 사용).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="확인 프롬프트 없이 바로 진행한다(파드/Job 등 비대화형 환경용).",
    )
    args = parser.parse_args()

    settings = RetrainTriggerSettings()
    factory = AwsClientFactory(settings.aws_region, settings.aws_endpoint_url)
    dynamodb = DynamoDbAdapter(factory, table_name=settings.prediction_accuracy_table_name)
    s3 = S3Adapter(factory, bucket=settings.s3_bucket)

    all_items = fetch_accuracy_log(dynamodb)
    untrained = filter_untrained(all_items)
    print(f"전체 {len(all_items)}건 중 학습 미사용 {len(untrained)}건")
    summarize(untrained, label="학습 미사용 오답노트")

    if len(untrained) < MIN_RECORDS_FOR_TRAINING and not args.force:
        print(
            f"학습 미사용 오답노트가 {len(untrained)}/{MIN_RECORDS_FOR_TRAINING}건 — 아직 부족합니다. "
            f"{MIN_RECORDS_FOR_TRAINING}건 이상 쌓이면 자동으로 이어학습을 진행합니다. "
            "그래도 파이프라인만 검증하려면 --force를 붙이세요(과적합 위험 있음)."
        )
        return

    usable, skipped = split_usable(untrained)
    if skipped:
        print(f"학습 필수 컬럼이 없어 건너뛴 레거시 레코드 {len(skipped)}건(날씨 필드 없는 구버전)")
    if not usable:
        print("학습 가능한 레코드가 없습니다(전부 구버전 스키마). 중단.")
        return

    if not args.yes:
        # [2026-08-20] K8s Job엔 보통 stdin이 안 붙는다(stdin: true 명시 안 하면) — 이 상태로
        # input()을 부르면 즉시 EOFError로 죽거나(최악의 경우 붙어있으면) 영원히 걸린다.
        # backoffLimit=0이라 재시도도 없어서, 그냥 죽는 건 낫지만 원인이 트레이스백에 안 보이면
        # "왜 죽었지" 삽질하게 된다 — 여기서 미리 잡아서 명확한 이유를 남기고 종료한다.
        if not sys.stdin.isatty():
            print("비대화형 환경(stdin 없음)에서 --yes 없이 실행됨 — 확인 프롬프트를 띄울 수 없습니다. "
                  "K8s Job/CronJob에서는 command에 --yes를 반드시 포함하세요.")
            sys.exit(1)
        answer = input(f"오답노트 {len(usable)}건으로 이어학습을 진행할까요? [y/N] ")
        if answer.strip().lower() != "y":
            print("취소됨.")
            return

    model, mae, rmse = continue_train(usable, s3, settings)
    upload_continued_model(model, mae, rmse, settings, len(usable))
    mark_used_as_trained(usable, dynamodb)


if __name__ == "__main__":
    main()
