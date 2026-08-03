# Scaling Decision Engine — 이 프로젝트의 핵심 Business Logic.
# 예측 수요를 해석해 필요한 Replica 수를 계산한다 (G1). AI는 예측만, 결정은 여기서만 한다.
#
# 공식: 예측수요==0 → 1개(버퍼 없음). 그 외 → ceil(예측수요/파드당수용치) + 버퍼(n+1).
# 파드 하나가 500만 감당한다고 예측했는데 실제 1000이면 파드 2개로는 빠듯하니, 여유분
# 하나를 항상 더 얹는다 — 다만 수요가 아예 없는 새벽 등에는 버퍼도 필요 없다고 판단.
import math

from common.core.logger import get_logger
from common.models.scaling import ScalingDecision, ScalingSignals

logger = get_logger("decision_engine")


class ScalingDecisionEngine:
    def __init__(self, demand_per_pod: float, buffer_pods: int, min_replicas: int, max_replicas: int):
        self._demand_per_pod = demand_per_pod
        self._buffer = buffer_pods
        self._min = min_replicas
        self._max = max_replicas

    def decide(self, signals: ScalingSignals) -> ScalingDecision:
        demand = signals.predicted_demand
        if demand <= 0:
            desired = 1
            matched = "demand=0 -> 1 (버퍼 없음)"
        else:
            base = math.ceil(demand / self._demand_per_pod)
            desired = base + self._buffer
            matched = f"ceil({demand:g}/{self._demand_per_pod:g})+{self._buffer} -> {desired}"
        clamped = max(self._min, min(self._max, desired))
        return ScalingDecision(
            desired_replicas=clamped,
            matched_rule=matched,
            reason=f"predicted_demand={demand:g}, rule[{matched}]"
            + (f", clamped to [{self._min},{self._max}]" if clamped != desired else ""),
        )
