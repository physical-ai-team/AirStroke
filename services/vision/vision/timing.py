"""통계 구간 동안의 소요 시간(ms)을 모아 평균·p95 로 요약한다 (CPU 튜닝 근거용)."""

from __future__ import annotations

import math


class LatencyWindow:
    def __init__(self) -> None:
        self._values: list[float] = []

    def add(self, ms: float) -> None:
        self._values.append(ms)

    def flush(self) -> tuple[float | None, float | None]:
        """(평균, p95)를 돌려주고 비운다. 값이 없으면 (None, None)."""
        values, self._values = sorted(self._values), []
        if not values:
            return None, None
        p95 = values[min(len(values) - 1, math.ceil(len(values) * 0.95) - 1)]
        return round(sum(values) / len(values), 1), round(p95, 1)
