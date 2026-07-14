# KEDA Adapter 추상 인터페이스 — Service는 Kubernetes API를 직접 호출하지 않는다.
# Deployment를 직접 수정하지 않고 KEDA ScaledObject의 minReplicaCount만 Patch한다:
#   - minReplicaCount는 "선제 확보 하한선" — Prediction 기반으로 미리 끌어올린다
#   - 실제 트래픽 폭증 시 KEDA의 SQS scaler가 그 이상으로 추가 확장 (두 신호 공존)
from abc import ABC, abstractmethod


class KedaAdapter(ABC):
    @abstractmethod
    def get_min_replicas(self) -> int:
        """ScaledObject의 현재 minReplicaCount를 읽는다."""

    @abstractmethod
    def patch_min_replicas(self, replicas: int) -> int:
        """minReplicaCount를 Patch하고 적용된 값을 반환한다."""

    @abstractmethod
    def get_actual_replicas(self) -> int:
        """worker Deployment의 실제 가동 중인(ready) 파드 수 — KEDA의 반응형 확장까지 반영된 값."""
