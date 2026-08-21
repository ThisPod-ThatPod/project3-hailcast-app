# DynamoDB Adapter — Service는 boto3를 직접 호출하지 않고 이 Adapter만 사용한다.
# 오답노트(hailcast-dev-prediction-log, 인프라 리소스 #41) 전용 — put_item + scan_all + mark_trained.
from botocore.exceptions import BotoCoreError, ClientError

from common.aws.client_factory import AwsClientFactory
from common.core.exceptions import AwsError
from common.core.logger import get_logger

logger = get_logger("dynamodb")


class DynamoDbAdapter:
    def __init__(self, factory: AwsClientFactory, table_name: str):
        self._client = factory.get_client("dynamodb")
        self._table_name = table_name

    def _wrap(self, operation: str, exc: Exception) -> AwsError:
        return AwsError(
            f"DynamoDB {operation} failed: {exc}",
            service="dynamodb",
            operation=operation,
            detail={"table": self._table_name},
        )

    def put_item(self, item: dict) -> None:
        """item은 이미 DynamoDB AttributeValue 형식({"S": ...} 등)으로 변환된 dict."""
        try:
            self._client.put_item(TableName=self._table_name, Item=item)
        except (ClientError, BotoCoreError) as exc:
            raise self._wrap("put_item", exc) from exc

    def scan_all(self) -> list[dict]:
        """테이블 전체를 페이지네이션하며 읽는다. 재학습 수동 트리거가 오답노트 현황을
        확인하는 용도 — 사람이 가끔 호출하는 저빈도 경로라 별도 인덱스/필터 없이 scan으로 충분하다."""
        items: list[dict] = []
        try:
            kwargs: dict = {"TableName": self._table_name}
            while True:
                response = self._client.scan(**kwargs)
                items.extend(response.get("Items", []))
                last_key = response.get("LastEvaluatedKey")
                if not last_key:
                    break
                kwargs["ExclusiveStartKey"] = last_key
        except (ClientError, BotoCoreError) as exc:
            raise self._wrap("scan", exc) from exc
        return items

    def mark_trained(self, prediction_date: str, target_time: str) -> None:
        """재학습에 쓴 레코드를 학습여부=1로 표시 — 다음 배치가 같은 레코드를 재사용 안 하게.
        PutItem과 달리 나머지 속성은 안 건드리고 이 필드만 갱신한다.
        UpdateExpression은 파싱되는 미니 DSL이라(PutItem의 Item dict와 달리), 한글
        속성명을 문자열에 그대로 못 넣고 ExpressionAttributeNames로 별칭 처리해야 한다."""
        try:
            self._client.update_item(
                TableName=self._table_name,
                Key={"prediction_date": {"S": prediction_date}, "target_time": {"S": target_time}},
                UpdateExpression="SET #trained = :v",
                ExpressionAttributeNames={"#trained": "학습여부"},
                ExpressionAttributeValues={":v": {"N": "1"}},
            )
        except (ClientError, BotoCoreError) as exc:
            raise self._wrap("update_item", exc) from exc
