import math

import pytest

from airstroke_shared.schemas import Hand
from gesture.core.classify import ACTIONS, classify, select_hand
from gesture.core.debounce import Debouncer
from gesture.core.fingers import extended_fingers
from gesture.core.mapping import to_canvas
from gesture.core.one_euro import OneEuroFilter


def make_points(extended: set[str]) -> list[list[float]]:
    """손목 (0.5, 0.9)에서 위로 뻗은 단순한 손. 접힌 손가락은 TIP이 PIP보다 손목에 가깝다."""
    pts = [[0.5, 0.5, 0.0] for _ in range(21)]
    pts[0] = [0.5, 0.9, 0.0]
    columns = {"index": (8, 6, 0.45), "middle": (12, 10, 0.5), "ring": (16, 14, 0.55),
               "pinky": (20, 18, 0.6)}  # fmt: skip
    for name, (tip, pip, x) in columns.items():
        pts[pip] = [x, 0.6, 0.0]
        pts[tip] = [x, 0.4 if name in extended else 0.75, 0.0]
    return pts


@pytest.mark.parametrize(
    ("extended", "gesture"),
    [
        ({"index"}, "index"),
        ({"index", "middle"}, "index_middle"),
        (set(), "fist"),
        ({"index", "middle", "ring", "pinky"}, "palm"),
        ({"middle"}, "unknown"),
        ({"index", "pinky"}, "unknown"),
    ],
)
def test_extended_and_classify(extended, gesture):
    found = extended_fingers(make_points(extended))
    assert found == frozenset(extended)
    assert classify(found) == gesture


def test_actions_table():
    assert ACTIONS["index"] == "draw"
    assert ACTIONS["index_middle"] == "move"
    assert ACTIONS["fist"] == "idle"
    assert ACTIONS["palm"] == "erase"
    assert ACTIONS["unknown"] == "idle"
    assert ACTIONS["none"] == "idle"


def test_z_is_ignored():
    pts = make_points({"index"})
    pts[6][2] = 5.0  # PIP z가 아무리 커도 x, y로만 판단
    assert extended_fingers(pts) == {"index"}


def test_select_hand_highest_score():
    pts = make_points(set())
    low = Hand(handedness="Left", score=0.5, points=pts)
    high = Hand(handedness="Right", score=0.9, points=pts)
    assert select_hand([low, high]) is high
    assert select_hand([]) is None


def test_debounce_needs_consecutive_frames():
    d = Debouncer(3)
    assert d.update("index") == "none"
    assert d.update("index") == "none"
    assert d.update("index") == "index"
    # 중간에 다른 값이 끼면 카운트가 다시 시작된다
    assert d.update("palm") == "index"
    assert d.update("palm") == "index"
    assert d.update("fist") == "index"
    assert d.update("palm") == "index"
    assert d.update("palm") == "index"
    assert d.update("palm") == "palm"


def test_debounce_single_glitch_is_ignored():
    d = Debouncer(3)
    for _ in range(3):
        d.update("index")
    assert d.update("unknown") == "index"
    assert d.update("index") == "index"
    assert d.update("unknown") == "index"
    assert d.update("unknown") == "index"  # 앞의 glitch는 index로 끊겼으므로 아직 2회


def test_mapping_center_mirror_and_clamp():
    assert to_canvas(0.5, 0.5, False, 0.7) == pytest.approx((0.5, 0.5))
    assert to_canvas(0.15, 0.85, False, 0.7) == pytest.approx((0.0, 1.0))
    assert to_canvas(0.0, 1.0, False, 0.7) == (0.0, 1.0)  # 범위 밖은 자름
    assert to_canvas(0.15, 0.5, True, 0.7) == pytest.approx((1.0, 0.5))  # 셀카: x 반전
    assert to_canvas(0.3, 0.4, False, 1.0) == pytest.approx((0.3, 0.4))


def test_one_euro_first_value_passthrough_and_reset():
    f = OneEuroFilter(1.0, 0.007, 1.0)
    assert f(0.3, 0.0) == 0.3
    assert f(0.3, 0.0) == 0.3  # dt=0이면 그대로
    f.reset()
    assert f(0.9, 100.0) == 0.9


def test_one_euro_reduces_jitter():
    f = OneEuroFilter(1.0, 0.007, 1.0)
    raw = [0.5 + (0.01 if i % 2 else -0.01) for i in range(60)]
    out = [f(v, i * 1000 / 15) for i, v in enumerate(raw)]
    spread = max(out[30:]) - min(out[30:])
    assert spread < 0.02 * 0.5


def test_one_euro_follows_step():
    f = OneEuroFilter(1.0, 0.007, 1.0)
    f(0.0, 0.0)
    out = 0.0
    for i in range(1, 30):
        out = f(1.0, i * 1000 / 15)
    assert math.isclose(out, 1.0, abs_tol=0.05)
