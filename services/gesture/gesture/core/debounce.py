"""④ 디바운스 — 같은 제스처가 N 프레임 연속으로 나와야 확정한다."""

from __future__ import annotations

from airstroke_shared.schemas import Gesture


class Debouncer:
    def __init__(self, frames: int, initial: Gesture = "none") -> None:
        self.frames = max(1, frames)
        self.confirmed: Gesture = initial
        self._candidate: Gesture = initial
        self._count = 0

    def update(self, gesture: Gesture) -> Gesture:
        """이번 프레임의 제스처를 넣고, 확정된 제스처를 돌려준다."""
        if gesture == self.confirmed:
            self._candidate, self._count = gesture, 0
            return self.confirmed
        if gesture == self._candidate:
            self._count += 1
        else:
            self._candidate, self._count = gesture, 1
        if self._count >= self.frames:
            self.confirmed, self._count = gesture, 0
        return self.confirmed

    def reset(self, gesture: Gesture = "none") -> None:
        self.confirmed = self._candidate = gesture
        self._count = 0
