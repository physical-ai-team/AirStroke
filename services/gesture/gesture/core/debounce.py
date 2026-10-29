"""④ 디바운스 — 같은 제스처가 N 프레임 연속으로 나와야 확정한다.

제스처별로 N을 다르게 둘 수 있다(예: 실수하면 안 되는 thumb_up은 더 길게).
"""

from __future__ import annotations

from collections.abc import Mapping

from airstroke_shared.schemas import Gesture


class Debouncer:
    def __init__(
        self,
        frames: int,
        initial: Gesture = "none",
        per_gesture: Mapping[Gesture, int] | None = None,
    ) -> None:
        self.frames = max(1, frames)
        self.per_gesture = {g: max(1, n) for g, n in (per_gesture or {}).items()}
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
        if self._count >= self.per_gesture.get(gesture, self.frames):
            self.confirmed, self._count = gesture, 0
        return self.confirmed

    def reset(self, gesture: Gesture = "none") -> None:
        self.confirmed = self._candidate = gesture
        self._count = 0
