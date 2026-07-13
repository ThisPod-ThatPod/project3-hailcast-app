# boto3 클라이언트 팩토리 — region/endpoint를 일원화. 향후 dynamodb 등 서비스 추가 시 이 팩토리만 사용.
import threading

import boto3
from botocore.config import Config


class AwsClientFactory:
    """서비스명 → boto3 client 캐시. endpoint_url 주입으로 LocalStack ↔ 실 AWS 전환.

    max_pool_connections: boto3 기본값(10)은 고TPS 서비스(call-api)에서 실제로 터진
    전례가 있다 — "Connection pool is full, discarding connection" 경고가 반복되다
    프로세스가 죽는다(D3). 트래픽이 몰리는 서비스는 이 값을 넉넉히 올려서 넘긴다.
    """

    def __init__(self, region: str, endpoint_url: str | None = None, max_pool_connections: int | None = None):
        self._region = region
        self._endpoint_url = endpoint_url
        self._max_pool_connections = max_pool_connections
        self._clients: dict[str, object] = {}
        self._lock = threading.Lock()

    def get_client(self, service: str):
        with self._lock:
            if service not in self._clients:
                config = (
                    Config(max_pool_connections=self._max_pool_connections)
                    if self._max_pool_connections
                    else None
                )
                self._clients[service] = boto3.client(
                    service,
                    region_name=self._region,
                    endpoint_url=self._endpoint_url,
                    config=config,
                )
            return self._clients[service]
