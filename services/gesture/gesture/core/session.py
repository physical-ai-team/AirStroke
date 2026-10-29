"""세션별 gesture 상태 — LandmarksMsg 하나를 받아 CommandMsg 하나를 만든다.

메시지는 순서대로 모두 넣어야 한다(디바운스·필터 상태 때문).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from airstroke_shared.schemas import CommandMsg, Cursor, LandmarksMsg, now_ms

from .classify import ACTIONS, classify, select_hand
from .debounce import Debouncer
from .fingers import INDEX_TIP, extended_fingers
from .mapping import to_canvas
from .one_euro import OneEuroFilter


@dataclass(frozen=True)
class GestureParams:
    # 기본값은 .env.example과 같게 유지한다
    debounce_frames: int = 3
    active_area: float = 0.7
    one_euro_min_cutoff: float = 1.0
    one_euro_beta: float = 0.007
    one_euro_d_cutoff: float = 1.0


class GestureSession:
    def __init__(self, params: GestureParams, clock: Callable[[], float] = now_ms) -> None:
        self.params = params
        self._clock = clock
        self._debouncer = Debouncer(params.debounce_frames)
        self._filters = [
            OneEuroFilter(
                params.one_euro_min_cutoff, params.one_euro_beta, params.one_euro_d_cutoff
            )
            for _ in range(2)
        ]
        self._stroke_id = 0
        self._prev_action = "idle"

    def _reset_filters(self) -> None:
        for f in self._filters:
            f.reset()

    def process(self, msg: LandmarksMsg) -> CommandMsg:
        hand = select_hand(msg.hands)
        cursor: Cursor | None = None
        if hand is None:
            # 손이 없으면 디바운스 없이 바로 none.
            # 다시 나타날 때 필터가 이전 위치로 끌려가지 않게 초기화한다.
            self._debouncer.reset("none")
            self._reset_filters()
            gesture = "none"
        else:
            gesture = self._debouncer.update(classify(extended_fingers(hand.points)))
        action = ACTIONS[gesture]

        if action == "draw" and self._prev_action != "draw":
            self._stroke_id += 1
            self._reset_filters()
        self._prev_action = action

        if hand is not None:
            # 커서는 디바운스와 관계없이 매 프레임 갱신
            tip = hand.points[INDEX_TIP]
            x, y = to_canvas(tip[0], tip[1], msg.mirror, self.params.active_area)
            fx, fy = self._filters
            cursor = Cursor(x=fx(x, msg.ts), y=fy(y, msg.ts))

        trace = msg.trace.model_copy(update={"gesture_done": self._clock()})
        return CommandMsg(
            ts=msg.ts,
            seq=msg.seq,
            gesture=gesture,
            action=action,
            cursor=cursor,
            stroke_id=self._stroke_id if action == "draw" else None,
            trace=trace,
        )
