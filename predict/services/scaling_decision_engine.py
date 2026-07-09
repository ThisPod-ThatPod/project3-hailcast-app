# Scaling Decision Engine — 이 프로젝트의 핵심 Business Logic.
# Prediction(수요 예측)을 해석해 필요한 Replica 수를 계산한다. AI는 예측만, 결정은 여기서만 한다.
from common.core.logger import get_logger
from common.models.scaling import ScalingDecision, ScalingSignals

logger = get_logger("decision_engine")


def parse_rules(rules: str) -> list[tuple[float, int]]:
    """Config 문자열 "20:1,50:2,100:3,300:5,500:10" → [(threshold, replicas), ...] (임계값 오름차순).

    의미: predicted_demand < threshold 이면 해당 replicas. 모든 임계값 이상이면 max_replicas.
    """
    parsed = []
    for pair in rules.split(","):
        threshold, replicas = pair.strip().split(":")
        parsed.append((float(threshold), int(replicas)))
    return sorted(parsed, key=lambda p: p[0])


class ScalingDecisionEngine:
    def __init__(self, rules: list[tuple[float, int]], min_replicas: int, max_replicas: int):
        self._rules = rules
        self._min = min_replicas
        self._max = max_replicas

    def decide(self, signals: ScalingSignals) -> ScalingDecision:
        """예측 수요 → 필요 Replica. 향후 queue_length/cpu 등 signals의 다른 필드를
        여기서 함께 반영하도록 확장한다 (예: max(예측 기반, 큐 기반))."""
        demand = signals.predicted_demand
        desired = self._max
        matched = f"demand>={self._rules[-1][0]:g} -> max({self._max})"
        for threshold, replicas in self._rules:
            if demand < threshold:
                desired = replicas
                matched = f"demand<{threshold:g} -> {replicas}"
                break
        clamped = max(self._min, min(self._max, desired))
        return ScalingDecision(
            desired_replicas=clamped,
            matched_rule=matched,
            reason=f"predicted_demand={demand:g}, rule[{matched}]"
            + (f", clamped to [{self._min},{self._max}]" if clamped != desired else ""),
        )
