# Node Adapter 추상 인터페이스 — Service는 Kubernetes API를 직접 호출하지 않는다.
# 대시보드 "노드 수" 위젯(C2/C8)의 데이터 소스.
from abc import ABC, abstractmethod


class NodeAdapter(ABC):
    @abstractmethod
    def count_ready_nodes(self) -> int:
        """클러스터에서 Ready 상태인 노드 수를 반환한다."""
