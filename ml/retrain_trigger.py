# 수동 재학습 트리거 — 오답노트(DynamoDB) 현황을 사람이 보고 판단해서 재학습을 실행한다.
# 이번 스프린트 스코프: "오답노트가 쌓이고 수동 트리거로 재학습되는 데까지" — 자동
# 스케줄링(대조 스케줄러가 오답노트를 언제·얼마나 채우는지)은 별도 결정 대상(§10 D-1)이라
# 여기서는 관여하지 않는다. 오답노트가 비어 있어도(대조 스케줄러 미구현 상태) --force로
# 재학습 자체는 그대로 검증할 수 있다.
#
# 실행 환경(로컬 vs 전용 파드)은 아직 미정 — 이 스크립트는 어느 쪽이든 그대로 쓸 수 있게
# 실행 위치에 대한 가정을 두지 않는다(로컬 CLI로 바로 돌리거나, 나중에 파드/Job의
# entrypoint로 그대로 넣어도 코드 변경이 필요 없다).
import argparse
from decimal import Decimal

from common.aws.client_factory import AwsClientFactory
from common.aws.dynamodb_adapter import DynamoDbAdapter
from common.core.settings import BaseAppSettings

from train import MODEL_PATH, save_model, train, upload_to_s3


class RetrainTriggerSettings(BaseAppSettings):
    service_name: str = "ml-retrain-trigger"
    # predict/config.py의 prediction_accuracy_table_name과 반드시 같은 값이어야 한다.
    prediction_accuracy_table_name: str = "hailcast-dev-prediction-log"


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


def summarize(items: list[dict]) -> None:
    print(f"오답노트 {len(items)}건")
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


def main() -> None:
    parser = argparse.ArgumentParser(description="오답노트 현황을 확인하고 수동으로 재학습을 트리거한다.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="오답노트가 비어 있어도(대조 스케줄러 미구현 상태 포함) 재학습을 강행한다.",
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

    items = fetch_accuracy_log(dynamodb)
    summarize(items)

    if not items and not args.force:
        print("오답노트가 비어 있습니다. 그래도 재학습 파이프라인 자체를 검증하려면 --force를 붙이세요.")
        return

    if not args.yes:
        answer = input(f"오답노트 {len(items)}건 확인됨. 재학습을 진행할까요? [y/N] ")
        if answer.strip().lower() != "y":
            print("취소됨.")
            return

    model, mae, rmse = train()
    save_model(model)
    upload_to_s3(MODEL_PATH, mae, rmse)
    print(f"재학습 완료 — MAE={mae:.2f} RMSE={rmse:.2f}")


if __name__ == "__main__":
    main()
