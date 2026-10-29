"""⑥ One Euro Filter (Casiez et al., 2012) — 1차원. x, y에 각각 하나씩 쓴다.

시각은 epoch ms로 받는다. 프레임이 버려질 수 있어 간격이 일정하지 않으므로 ts 차이로 dt를 구한다.
"""

from __future__ import annotations

import math


def _alpha(cutoff: float, dt: float) -> float:
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class OneEuroFilter:
    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    def reset(self) -> None:
        self._x: float | None = None
        self._dx = 0.0
        self._t_ms: float | None = None

    def __call__(self, x: float, t_ms: float) -> float:
        if self._x is None or self._t_ms is None:
            self._x, self._t_ms = x, t_ms
            return x
        dt = (t_ms - self._t_ms) / 1000.0
        if dt <= 0:  # 같은 시각이거나 역전된 메시지 — 갱신하지 않는다
            return self._x
        dx = (x - self._x) / dt
        self._dx += _alpha(self.d_cutoff, dt) * (dx - self._dx)
        cutoff = self.min_cutoff + self.beta * abs(self._dx)
        self._x += _alpha(cutoff, dt) * (x - self._x)
        self._t_ms = t_ms
        return self._x
