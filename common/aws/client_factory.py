# boto3 클라이언트 팩토리 — region/endpoint를 일원화. 향후 dynamodb 등 서비스 추가 시 이 팩토리만 사용.
import threading

import boto3


class AwsClientFactory:
    """서비스명 → boto3 client 캐시. endpoint_url 주입으로 LocalStack ↔ 실 AWS 전환."""

    def __init__(self, region: str, endpoint_url: str | None = None):
        self._region = region
        self._endpoint_url = endpoint_url
        self._clients: dict[str, object] = {}
        self._lock = threading.Lock()

    def get_client(self, service: str):
        with self._lock:
            if service not in self._clients:
                self._clients[service] = boto3.client(
                    service,
                    region_name=self._region,
                    endpoint_url=self._endpoint_url,
                )
            return self._clients[service]
