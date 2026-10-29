"""세션별 gesture 상태 — LandmarksMsg 하나를 받아 CommandMsg 하나를 만든다.

메시지는 순서대로 모두 넣어야 한다(디바운스·필터 상태 때문).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from airstroke_shared.schemas import CommandMsg, Cursor, Gesture, LandmarksMsg, now_ms

from .classify import ACTIONS, classify, select_hand
from .debounce import Debouncer
from .fingers import INDEX_TIP, THUMB_TIP, extended_fingers, is_pinch, is_thumb_up
from .mapping import to_canvas
from .one_euro import OneEuroFilter


@dataclass(frozen=True)
class GestureParams:
    # 기본값은 .env.example과 같게 유지한다
    debounce_frames: int = 3
    undo_debounce_frames: int = 6
    pinch_distance_ratio: float = 0.35
    active_area: float = 0.7
    one_euro_min_cutoff: float = 1.0
    one_euro_beta: float = 0.007
    one_euro_d_cutoff: float = 1.0
    # 그림판 비율 = CAMERA_WIDTH / CAMERA_HEIGHT (그림판도 /api/config 로 같은 값을 씀)
    canvas_aspect: float = 640 / 480


class GestureSession:
    def __init__(self, params: GestureParams, clock: Callable[[], float] = now_ms) -> None:
        self.params = params
        self._clock = clock
        self._debouncer = Debouncer(
            params.debounce_frames, per_gesture={"thumb_up": params.undo_debounce_frames}
        )
        self._filters = [
            OneEuroFilter(
                params.one_euro_min_cutoff, params.one_euro_beta, params.one_euro_d_cutoff
            )
            for _ in range(2)
        ]
        self._stroke_id = 0
        self._prev_action = "idle"
        self._prev_gesture: Gesture = "none"
        self._pinch_cursor: Cursor | None = None

    def _reset_filters(self) -> None:
        for f in self._filters:
            f.reset()

    def process(self, msg: LandmarksMsg) -> CommandMsg:
        hand = select_hand(msg.hands)
        cursor: Cursor | None = None
        raw: Gesture = "none"
        if hand is None:
            # 손이 없으면 디바운스 없이 바로 none.
            # 다시 나타날 때 필터가 이전 위치로 끌려가지 않게 초기화한다.
            self._debouncer.reset("none")
            self._reset_filters()
            gesture: Gesture = "none"
        else:
            raw = classify(
                extended_fingers(hand.points),
                pinch=is_pinch(hand.points, self.params.pinch_distance_ratio),
                thumb_up=is_thumb_up(hand.points),
            )
            gesture = self._debouncer.update(raw)
        action = ACTIONS[gesture]

        if action == "draw" and self._prev_action != "draw":
            self._stroke_id += 1
            self._reset_filters()
        # 집기는 커서 기준점이 검지 끝 → 두 손가락 가운데로 바뀐다. 필터가 그 사이를 미끄러지면
        # 그림판 팔레트의 중심이 밀리므로 들어가고 나올 때 필터를 초기화해 바로 옮긴다.
        if (gesture == "pinch") != (self._prev_gesture == "pinch"):
            self._reset_filters()
        # 실행 취소는 thumb_up이 확정되는 순간 한 번만 보낸다. 들고 있는 동안은 idle.
        out_action = "idle" if action == "undo" and self._prev_action == "undo" else action
        self._prev_action = action
        self._prev_gesture = gesture

        if hand is not None:
            if gesture == "pinch" and raw != "pinch" and self._pinch_cursor is not None:
                # 손가락을 떼는 중(디바운스로 아직 pinch): 떼는 동작에 커서가 밀려
                # 다른 색이 골라지지 않도록 마지막 집기 위치에 고정한다.
                cursor = self._pinch_cursor
            else:
                cursor = self._cursor(msg, hand.points, pinch=gesture == "pinch")
        self._pinch_cursor = cursor if gesture == "pinch" else None

        trace = msg.trace.model_copy(update={"gesture_done": self._clock()})
        return CommandMsg(
            ts=msg.ts,
            seq=msg.seq,
            gesture=gesture,
            action=out_action,
            cursor=cursor,
            stroke_id=self._stroke_id if action == "draw" else None,
            trace=trace,
        )

    def _cursor(self, msg: LandmarksMsg, points, *, pinch: bool) -> Cursor:
        # 커서는 디바운스와 관계없이 매 프레임 갱신. 집기 중에는 엄지·검지 끝의 가운데
        tip = points[INDEX_TIP]
        if pinch:
            thumb = points[THUMB_TIP]
            tip = [(tip[0] + thumb[0]) / 2, (tip[1] + thumb[1]) / 2]
        frame_aspect = msg.width / msg.height if msg.width and msg.height else None
        x, y = to_canvas(
            tip[0],
            tip[1],
            msg.mirror,
            self.params.active_area,
            frame_aspect,
            self.params.canvas_aspect,
        )
        fx, fy = self._filters
        return Cursor(x=fx(x, msg.ts), y=fy(y, msg.ts))
