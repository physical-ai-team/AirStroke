"""ping/pong 시계 차이 추정 (NTP 방식). Redis·WebSocket 없이 테스트할 수 있는 순수 로직.

    RTT    = pong 도착 시각 - ping 보낸 시각
    offset = t_client - (t_server + RTT/2)       → gateway_ts = client_ts - offset
최근 `window`개 샘플 중 RTT가 가장 작은 것을 쓴다(지연이 짧을수록 비대칭 오차가 작다).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class ClockSample:
    rtt_ms: float
    offset_ms: float


class ClockEstimator:
    def __init__(self, window: int = 10) -> None:
        self._window = window
        self._samples: deque[ClockSample] = deque(maxlen=window)
        self._pending: dict[int, float] = {}  # ping id → 보낸 시각 (gateway ms)
        self._next_id = 0

    def new_ping(self, now: float) -> int:
        ping_id = self._next_id
        self._next_id += 1
        self._pending[ping_id] = now
        while len(self._pending) > self._window:  # 답이 없는 오래된 ping은 버린다
            del self._pending[next(iter(self._pending))]
        return ping_id

    def on_pong(self, ping_id: int, t_client: float, now: float) -> ClockSample | None:
        """모르는 id(오래됐거나 중복)는 무시하고 None.

        보낸 시각은 pong에 echo된 값이 아니라 gateway가 기록한 값을 쓴다.
        """
        t_server = self._pending.pop(ping_id, None)
        if t_server is None:
            return None
        rtt = now - t_server
        self._samples.append(ClockSample(rtt_ms=rtt, offset_ms=t_client - (t_server + rtt / 2)))
        return self.best

    @property
    def best(self) -> ClockSample | None:
        return min(self._samples, key=lambda s: s.rtt_ms, default=None)

    def to_server_time(self, client_ts: float) -> float | None:
        """클라이언트 시각 → gateway 시각. 아직 추정값이 없으면 None."""
        best = self.best
        return None if best is None else client_ts - best.offset_ms
