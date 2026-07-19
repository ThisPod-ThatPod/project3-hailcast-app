# PredictionAccuracyLogger — DynamoDB 오답노트 write (C10, `hailcast-dev-prediction-log` #41).
#
# ⚠️ 2026-07-16 기준 미확정 — 트리거/필드 설계가 리뷰에서 두 안(수요 기준 vs 파드수 기준)으로
# 갈려서 팀 확정 전까지 어디에서도 호출하지 않는다(dependencies.py/scheduler에 배선 안 함).
# 여기 구현은 "수요 예측값 vs 실제 수요값" 안(review 답변에서 제안한 쪽)을 기본으로 짜뒀다 —
# 확정되면 이 파일만 고치거나 갈아끼우면 되도록 다른 서비스와 분리해뒀다.
# 트리거 방식이 정해지면 K8S_NODES_ENABLED류 env 플래그로 켜고 끄게 만들 가능성이 높다.
from datetime import datetime, timezone

from common.aws.dynamodb_adapter import DynamoDbAdapter
from common.core.logger import get_logger

logger = get_logger("prediction_accuracy_logger")


class PredictionAccuracyLogger:
    def __init__(self, dynamodb: DynamoDbAdapter, error_ratio_threshold: float):
        self._dynamodb = dynamodb
        self._threshold = error_ratio_threshold

    def record_if_needed(self, target_time: datetime, predicted_demand: float, actual_demand: float) -> bool:
        """오차 비율이 임계값을 넘으면 오답노트 1건 기록. 기록했으면 True."""
        diff = actual_demand - predicted_demand
        denom = max(predicted_demand, 1.0)  # 0 나눗셈 방지
        error_ratio = abs(diff) / denom
        if error_ratio < self._threshold:
            return False

        prediction_date = target_time.astimezone(timezone.utc).strftime("%Y-%m-%d")
        item = {
            "prediction_date": {"S": prediction_date},  # PK — 인프라 #41, "date"는 예약어라 회피
            "target_time": {"S": target_time.astimezone(timezone.utc).isoformat()},  # SK
            "predicted_demand": {"N": str(predicted_demand)},
            "actual_demand": {"N": str(actual_demand)},
            "diff": {"N": str(diff)},
        }
        self._dynamodb.put_item(item)
        logger.warning(
            f"prediction accuracy miss logged (ratio={error_ratio:.0%})",
            extra={
                "event": "prediction_accuracy_miss",
                "detail": {"predicted": predicted_demand, "actual": actual_demand, "diff": diff},
            },
        )
        return True
