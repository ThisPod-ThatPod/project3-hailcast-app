# S3 Adapter — Service는 boto3를 직접 호출하지 않고 이 Adapter만 사용한다.
# 모델 아티팩트(다운로드)와 prediction.json(업로드) 모두 여기를 거친다.
import json

from botocore.exceptions import BotoCoreError, ClientError

from common.aws.client_factory import AwsClientFactory
from common.core.exceptions import AwsError
from common.core.logger import get_logger

logger = get_logger("s3")


class S3Adapter:
    def __init__(self, factory: AwsClientFactory, bucket: str, auto_create: bool = False):
        self._client = factory.get_client("s3")
        self._bucket = bucket
        # 로컬(LocalStack) 개발 편의: 버킷이 없으면 생성. 운영에서는 False(IaC가 버킷 소유).
        self._auto_create = auto_create
        self._ensured = False

    def _wrap(self, operation: str, key: str, exc: Exception) -> AwsError:
        return AwsError(
            f"S3 {operation} failed: {exc}",
            service="s3",
            operation=operation,
            detail={"bucket": self._bucket, "key": key},
        )

    def _ensure_bucket(self) -> None:
        if self._ensured or not self._auto_create:
            return
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            logger.info(
                "bucket not found, creating",
                extra={"event": "bucket_create", "detail": {"bucket": self._bucket}},
            )
            region = self._client.meta.region_name
            create_kwargs = {"Bucket": self._bucket}
            if region and region != "us-east-1":
                # us-east-1 외 리전은 LocationConstraint 필수
                create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
            self._client.create_bucket(**create_kwargs)
        self._ensured = True

    # ---- JSON ----
    def upload_json(self, key: str, body: dict) -> None:
        try:
            self._ensure_bucket()
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=json.dumps(body, ensure_ascii=False, default=str).encode("utf-8"),
                ContentType="application/json",
            )
        except (ClientError, BotoCoreError) as exc:
            raise self._wrap("put_object", key, exc) from exc

    def download_json(self, key: str) -> dict:
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
            return json.loads(resp["Body"].read())
        except (ClientError, BotoCoreError) as exc:
            raise self._wrap("get_object", key, exc) from exc

    # ---- 텍스트 (CSV 등 JSON이 아닌 상태 파일) ----
    def upload_text(self, key: str, body: str) -> None:
        try:
            self._ensure_bucket()
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=body.encode("utf-8"),
                ContentType="text/plain",
            )
        except (ClientError, BotoCoreError) as exc:
            raise self._wrap("put_object", key, exc) from exc

    def download_text(self, key: str) -> str:
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
            return resp["Body"].read().decode("utf-8")
        except (ClientError, BotoCoreError) as exc:
            raise self._wrap("get_object", key, exc) from exc

    def list_keys(self, prefix: str) -> list[str]:
        try:
            resp = self._client.list_objects_v2(Bucket=self._bucket, Prefix=prefix)
        except (ClientError, BotoCoreError) as exc:
            raise self._wrap("list_objects_v2", prefix, exc) from exc
        return [obj["Key"] for obj in resp.get("Contents", [])]

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False

    # ---- 파일 (모델 아티팩트) ----
    def upload_file(self, key: str, path: str) -> None:
        try:
            self._ensure_bucket()
            self._client.upload_file(path, self._bucket, key)
        except (ClientError, BotoCoreError) as exc:
            raise self._wrap("upload_file", key, exc) from exc

    def download_file(self, key: str, path: str) -> None:
        try:
            self._client.download_file(self._bucket, key, path)
        except (ClientError, BotoCoreError) as exc:
            raise self._wrap("download_file", key, exc) from exc
