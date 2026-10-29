"""① 손 선택, ③ 제스처 분류."""

from __future__ import annotations

from collections.abc import Sequence

from airstroke_shared.schemas import Action, Gesture, Hand

ACTIONS: dict[Gesture, Action] = {
    "index": "draw",
    "index_middle": "move",
    "fist": "idle",
    "palm": "erase",
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


def classify(extended: frozenset[str]) -> Gesture:
    return _GESTURES.get(extended, "unknown")
