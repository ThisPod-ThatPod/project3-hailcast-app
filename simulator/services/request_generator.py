# Random Request Generator — 실제 서비스와 동일한 CallRequest 모델을 생성한다 (Dummy Model 금지).
# 서울 실제 구역 좌표 기반으로 향후 ML Feature(구역별 수요 패턴)로 쓸 수 있는 데이터를 만든다.
import random
from datetime import datetime, timezone

from common.core.constants import SOURCE_SIMULATOR
from common.models.call import CallRequest, Location

# 서울 주요 구역 중심 좌표 + 수요 가중치 (강남/홍대 등 실제 수요가 높은 곳에 콜 집중)
_ZONES: list[tuple[str, float, float, float]] = [
    # (zone_id, lat, lon, demand_weight)
    ("gangnam",   37.4979, 127.0276, 0.22),
    ("hongdae",   37.5563, 126.9236, 0.15),
    ("jongno",    37.5729, 126.9793, 0.12),
    ("yeouido",   37.5219, 126.9245, 0.11),
    ("jamsil",    37.5133, 127.1001, 0.10),
    ("itaewon",   37.5345, 126.9946, 0.08),
    ("seongsu",   37.5446, 127.0559, 0.08),
    ("mapo",      37.5638, 126.9084, 0.07),
    ("guro",      37.4954, 126.8874, 0.07),
]

# 승객 수 분포 (1인 탑승이 대부분인 실제 택시 수요 반영)
_PASSENGER_CHOICES = [1, 2, 3, 4]
_PASSENGER_WEIGHTS = [0.70, 0.20, 0.07, 0.03]

# 구역 중심에서 좌표를 흩뿌리는 표준편차 (약 ±1km)
_COORD_JITTER_STD = 0.009


class RequestGenerator:
    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)
        self._zone_ids = [z[0] for z in _ZONES]
        self._zone_weights = [z[3] for z in _ZONES]
        self._zone_by_id = {z[0]: z for z in _ZONES}

    def _point_in_zone(self, zone_id: str) -> Location:
        _, lat, lon, _ = self._zone_by_id[zone_id]
        return Location(
            lat=round(self._rng.gauss(lat, _COORD_JITTER_STD), 6),
            lon=round(self._rng.gauss(lon, _COORD_JITTER_STD), 6),
        )

    def generate(self) -> CallRequest:
        pickup_zone = self._rng.choices(self._zone_ids, weights=self._zone_weights, k=1)[0]
        # 목적지는 출발지와 다른 구역을 선호 (같은 구역 이동 20%)
        if self._rng.random() < 0.2:
            dest_zone = pickup_zone
        else:
            dest_zone = self._rng.choice([z for z in self._zone_ids if z != pickup_zone])
        return CallRequest(
            user_id=f"sim-user-{self._rng.randint(1, 5000):05d}",
            pickup=self._point_in_zone(pickup_zone),
            destination=self._point_in_zone(dest_zone),
            zone_id=pickup_zone,
            passenger_count=self._rng.choices(_PASSENGER_CHOICES, weights=_PASSENGER_WEIGHTS, k=1)[0],
            requested_at=datetime.now(timezone.utc),
            source=SOURCE_SIMULATOR,
        )
