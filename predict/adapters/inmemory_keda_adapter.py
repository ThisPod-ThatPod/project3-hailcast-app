# InMemory 구현체 — 로컬(docker-compose, K8s 없음)·테스트용 Mock 교체 지점.
# KEDA_ENABLED=false일 때 사용되며, Patch 결과를 메모리에 유지해 파이프라인 전체를 검증할 수 있다.
from common.core.logger import get_logger

from adapters.keda_adapter import KedaAdapter

logger = get_logger("keda_adapter")


class InMemoryKedaAdapter(KedaAdapter):
    def __init__(self, initial_replicas: int):
        self._replicas = initial_replicas

    def get_min_replicas(self) -> int:
        return self._replicas

    def patch_min_replicas(self, replicas: int) -> int:
        self._replicas = replicas
        logger.info(
            f"[dry-run] scaledobject patched (minReplicaCount={replicas})",
            extra={"event": "patch_success", "count": replicas},
        )
        return self._replicas
