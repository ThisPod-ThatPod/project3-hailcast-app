# PredictionAccuracyLogger — DynamoDB 오답노트 write (C10, `hailcast-dev-prediction-log` #41).
#
# [2026-08-14 팀 확정] 트리거는 수요 기준(predicted_demand vs 실측 수요).
# [2026-08-20] 트리거 방향을 대칭(abs) → 비대칭으로 변경 — "예측 실패"는 예측형
# 오토스케일링 관점에서 실제로 위험한 쪽(실측이 예측을 초과 = 용량 부족 가능성)만
# 의미가 있다. 예측이 실측보다 컸던 경우(과잉 프로비저닝)는 비용 손해일 뿐 서비스
# 위험이 아니라서 재학습 입력 대상에서 제외한다.
# [2026-08-20] 재학습 시 ml/train.py가 바로 이어붙일 수 있도록, 학습 데이터와 동일한
# 컬럼명(날짜·요일·온도·습도·강수유무·승객수)으로 저장한다(ml/features.py, weather_service.py
# _CSV_FIELDS와 동일 스키마). "승객수"는 학습 라벨과 같은 의미로 실측 수요(actual_demand)를 쓴다.
# [2026-08-20] "학습여부"(0/1) 추가 — ml/retrain_trigger.py가 이 값으로 이미 재학습에 쓴
# 레코드를 걸러낸다(재사용 방지). 새로 기록되는 시점엔 항상 0, 재학습 완료 후
# DynamoDbAdapter.mark_trained()가 1로 갱신한다.
from datetime import datetime, timezone

from common.aws.dynamodb_adapter import DynamoDbAdapter
from common.core.logger import get_logger

logger = get_logger("prediction_accuracy_logger")


class PredictionAccuracyLogger:
    def __init__(self, dynamodb: DynamoDbAdapter, error_ratio_threshold: float):
        self._dynamodb = dynamodb
        self._threshold = error_ratio_threshold

    def record_if_needed(
        self,
        target_time: datetime,
        predicted_demand: float,
        actual_demand: float,
        local_date: str,
        weekday: int,
        temperature: float | None,
        humidity: float | None,
        is_raining: bool | None,
    ) -> bool:
        """실측이 예측을 초과하고 그 폭이 임계값을 넘으면 오답노트 1건 기록. 기록했으면 True.

        local_date/weekday는 뉴욕 현지시간 기준(호출부에서 변환) — 학습 데이터가 그 기준이라
        그대로 맞춘다.
        """
        diff = actual_demand - predicted_demand
        if diff <= 0:  # 과대예측(예측≥실측)은 재학습 입력 대상 아님 — 위 주석 참고
            return False
        denom = max(predicted_demand, 1.0)  # 0 나눗셈 방지
        error_ratio = diff / denom
        if error_ratio < self._threshold:
            return False

        prediction_date = target_time.astimezone(timezone.utc).strftime("%Y-%m-%d")
        item = {
            "prediction_date": {"S": prediction_date},  # PK — 인프라 #41, "date"는 예약어라 회피
            "target_time": {"S": target_time.astimezone(timezone.utc).isoformat()},  # SK
            "predicted_demand": {"N": str(predicted_demand)},
            "actual_demand": {"N": str(actual_demand)},
            "diff": {"N": str(diff)},
            # 재학습 입력용 — ml/train.py가 기대하는 컬럼명과 동일
            "날짜": {"S": local_date},
            "요일": {"N": str(weekday)},
            "승객수": {"N": str(actual_demand)},
            "학습여부": {"N": "0"},
        }
        if temperature is not None:
            item["온도"] = {"N": str(temperature)}
        if humidity is not None:
            item["습도"] = {"N": str(humidity)}
        if is_raining is not None:
            item["강수유무"] = {"N": str(int(is_raining))}
        self._dynamodb.put_item(item)
        logger.warning(
            f"prediction accuracy miss logged (ratio={error_ratio:.0%})",
            extra={
                "event": "prediction_accuracy_miss",
                "detail": {"predicted": predicted_demand, "actual": actual_demand, "diff": diff},
            },
        )
        return True
