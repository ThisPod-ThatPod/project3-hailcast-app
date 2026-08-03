# InMemory 구현체 — 로컬(docker-compose, K8s 없음)·테스트용 Mock 교체 지점.
# K8S_NODES_ENABLED=false일 때 사용되며, 고정값을 반환해 응답 계약만 유지한다.
from common.core.logger import get_logger

from adapters.node_adapter import NodeAdapter

logger = get_logger("node_adapter")


class InMemoryNodeAdapter(NodeAdapter):
    def __init__(self, fixed_count: int):
        self._fixed_count = fixed_count

    def count_ready_nodes(self) -> int:
        return self._fixed_count
