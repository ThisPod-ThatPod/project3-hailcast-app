# SQS Adapter — Service는 boto3를 직접 호출하지 않고 이 Adapter만 사용한다.
# 향후 FIFO(MessageGroupId)·DLQ(RedrivePolicy)를 send/receive 시그니처 변경 없이 추가할 수 있게 설계.
import json

from botocore.exceptions import BotoCoreError, ClientError

from common.aws.client_factory import AwsClientFactory
from common.core.exceptions import AwsError
from common.core.logger import get_logger

logger = get_logger("sqs")


class SqsAdapter:
    def __init__(
        self,
        factory: AwsClientFactory,
        queue_name: str,
        queue_url: str | None = None,
        auto_create: bool = False,
    ):
        self._client = factory.get_client("sqs")
        self._queue_name = queue_name
        self._queue_url = queue_url
        # 로컬(LocalStack) 개발 편의: 큐가 없으면 생성. 운영에서는 False(IaC가 큐 소유).
        self._auto_create = auto_create

    # ---- 내부 유틸 ----
    def _wrap(self, operation: str, exc: Exception) -> AwsError:
        return AwsError(
            f"SQS {operation} failed: {exc}",
            service="sqs",
            operation=operation,
            detail={"queue": self._queue_name},
        )

    @property
    def queue_url(self) -> str:
        if self._queue_url:
            return self._queue_url
        try:
            resp = self._client.get_queue_url(QueueName=self._queue_name)
            self._queue_url = resp["QueueUrl"]
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if self._auto_create and code in (
                "AWS.SimpleQueueService.NonExistentQueue",
                "QueueDoesNotExist",
            ):
                logger.info(
                    "queue not found, creating",
                    extra={"event": "queue_create", "queue": self._queue_name},
                )
                resp = self._client.create_queue(QueueName=self._queue_name)
                self._queue_url = resp["QueueUrl"]
            else:
                raise self._wrap("get_queue_url", exc) from exc
        except BotoCoreError as exc:
            raise self._wrap("get_queue_url", exc) from exc
        return self._queue_url

    # ---- 공개 API ----
    def send_message(self, body: dict) -> str:
        """dict를 JSON으로 직렬화해 발행하고 MessageId를 반환한다."""
        try:
            resp = self._client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(body, ensure_ascii=False, default=str),
            )
            return resp["MessageId"]
        except (ClientError, BotoCoreError) as exc:
            raise self._wrap("send_message", exc) from exc

    def receive_messages(
        self,
        max_messages: int = 10,
        wait_seconds: int = 20,
        visibility_timeout: int = 30,
    ) -> list[dict]:
        """Long Polling 수신. 반환: [{message_id, receipt_handle, body(str), receive_count}]"""
        try:
            resp = self._client.receive_message(
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_seconds,
                VisibilityTimeout=visibility_timeout,
                AttributeNames=["ApproximateReceiveCount", "SentTimestamp"],
            )
        except (ClientError, BotoCoreError) as exc:
            raise self._wrap("receive_message", exc) from exc
        messages = []
        for m in resp.get("Messages", []):
            attrs = m.get("Attributes", {})
            messages.append(
                {
                    "message_id": m["MessageId"],
                    "receipt_handle": m["ReceiptHandle"],
                    "body": m["Body"],
                    "receive_count": int(attrs.get("ApproximateReceiveCount", "1")),
                    "sent_timestamp_ms": int(attrs.get("SentTimestamp", "0")),
                }
            )
        return messages

    def delete_message(self, receipt_handle: str) -> None:
        try:
            self._client.delete_message(
                QueueUrl=self.queue_url, ReceiptHandle=receipt_handle
            )
        except (ClientError, BotoCoreError) as exc:
            raise self._wrap("delete_message", exc) from exc

    def purge_queue(self) -> None:
        try:
            self._client.purge_queue(QueueUrl=self.queue_url)
        except (ClientError, BotoCoreError) as exc:
            raise self._wrap("purge_queue", exc) from exc

    def queue_attributes(self) -> dict:
        """큐 적체 현황 (Dashboard/모니터링용)."""
        try:
            resp = self._client.get_queue_attributes(
                QueueUrl=self.queue_url,
                AttributeNames=[
                    "ApproximateNumberOfMessages",
                    "ApproximateNumberOfMessagesNotVisible",
                    "ApproximateNumberOfMessagesDelayed",
                ],
            )
            return resp.get("Attributes", {})
        except (ClientError, BotoCoreError) as exc:
            raise self._wrap("get_queue_attributes", exc) from exc
