"""① 손 선택, ③ 제스처 분류."""

from __future__ import annotations

from collections.abc import Sequence

from airstroke_shared.schemas import Action, Gesture, Hand

ACTIONS: dict[Gesture, Action] = {
    "index": "draw",
    "index_middle": "move",
    "fist": "idle",
    "palm": "erase",
    "pinch": "select",
    "thumb_up": "undo",
    "unknown": "idle",
    "none": "idle",
}

_GESTURES: dict[frozenset[str], Gesture] = {
    frozenset({"index"}): "index",
    frozenset({"index", "middle"}): "index_middle",
    frozenset(): "fist",
    frozenset({"index", "middle", "ring", "pinky"}): "palm",
}


def select_hand(hands: Sequence[Hand]) -> Hand | None:
    """손이 여러 개면 score가 가장 높은 손 하나만 쓴다(초기안)."""
    return max(hands, key=lambda h: h.score, default=None)


def classify(extended: frozenset[str], *, pinch: bool = False, thumb_up: bool = False) -> Gesture:
    """집기를 가장 먼저 본다(집을 때 검지가 반쯤 펴져 index로 잡히는 것을 막음).
    엄지 세움은 네 손가락이 모두 접혔을 때만 인정한다(그 외에는 fist)."""
    if pinch:
        return "pinch"
    if not extended and thumb_up:
        return "thumb_up"
    return _GESTURES.get(extended, "unknown")
