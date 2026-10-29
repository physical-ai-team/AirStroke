import math

import pytest

from airstroke_shared.schemas import Hand
from gesture.core.classify import ACTIONS, classify, select_hand
from gesture.core.debounce import Debouncer
from gesture.core.fingers import extended_fingers, is_pinch, is_thumb_up
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
    # 엄지: 옆으로 누운 상태(MCP 2 → IP 3 → TIP 4). 집기도 엄지 세움도 아님
    pts[2], pts[3], pts[4] = [0.35, 0.7, 0.0], [0.28, 0.7, 0.0], [0.2, 0.7, 0.0]
    return pts


def pinch_points() -> list[list[float]]:
    """검지를 내밀고 엄지 끝을 검지 끝에 붙인 손."""
    pts = make_points({"index"})
    pts[4] = [pts[8][0] + 0.03, pts[8][1] + 0.02, 0.0]
    return pts


def thumb_up_points() -> list[list[float]]:
    """네 손가락은 접고 엄지만 위로 세운 손."""
    pts = make_points(set())
    pts[2], pts[3], pts[4] = [0.4, 0.45, 0.0], [0.4, 0.3, 0.0], [0.4, 0.2, 0.0]
    return pts


def test_pinch_and_thumb_up():
    ratio = 0.35
    assert is_pinch(pinch_points(), ratio)
    assert not is_pinch(make_points({"index"}), ratio)  # 엄지가 멂
    # 주먹: 엄지가 검지에 붙어 있어도 검지 끝이 손바닥 안이라 집기가 아님
    fist = make_points(set())
    fist[4] = [fist[8][0] + 0.02, fist[8][1], 0.0]
    assert not is_pinch(fist, ratio)

    assert is_thumb_up(thumb_up_points())
    assert not is_thumb_up(make_points(set()))  # 엄지가 옆으로 누움
    tucked = make_points(set())  # 엄지를 세웠지만 검지 뿌리에 붙여 감싸 쥠
    tucked[2], tucked[3], tucked[4] = [0.42, 0.62, 0.0], [0.45, 0.56, 0.0], [0.48, 0.52, 0.0]
    assert not is_thumb_up(tucked)


@pytest.mark.parametrize(
    ("points", "gesture"),
    [
        (pinch_points, "pinch"),  # 검지가 펴져 있어도 집기가 우선
        (thumb_up_points, "thumb_up"),
        (lambda: make_points(set()), "fist"),
    ],
)
def test_classify_thumb_gestures(points, gesture):
    pts = points()
    found = classify(extended_fingers(pts), pinch=is_pinch(pts, 0.35), thumb_up=is_thumb_up(pts))
    assert found == gesture


def test_thumb_up_needs_folded_fingers():
    # 엄지를 세웠어도 다른 손가락이 펴져 있으면 thumb_up 이 아니다
    assert classify(frozenset({"index"}), thumb_up=True) == "index"


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
    assert ACTIONS["pinch"] == "select"
    assert ACTIONS["thumb_up"] == "undo"
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


def test_debounce_per_gesture_frames():
    d = Debouncer(3, per_gesture={"thumb_up": 6})
    assert [d.update("thumb_up") for _ in range(6)][-2:] == ["none", "thumb_up"]
    assert [d.update("fist") for _ in range(3)][-1] == "fist"  # 다른 제스처는 3프레임


def test_mapping_center_mirror_and_clamp():
    assert to_canvas(0.5, 0.5, False, 0.7) == pytest.approx((0.5, 0.5))
    assert to_canvas(0.15, 0.85, False, 0.7) == pytest.approx((0.0, 1.0))
    assert to_canvas(0.0, 1.0, False, 0.7) == (0.0, 1.0)  # 범위 밖은 자름
    assert to_canvas(0.15, 0.5, True, 0.7) == pytest.approx((1.0, 0.5))  # 셀카: x 반전
    assert to_canvas(0.3, 0.4, False, 1.0) == pytest.approx((0.3, 0.4))


def test_mapping_keeps_aspect():
    canvas = 4 / 3
    # 가로 4:3 프레임은 비율을 안 줄 때와 같다
    assert to_canvas(0.2, 0.7, False, 0.7, 4 / 3, canvas) == pytest.approx(
        to_canvas(0.2, 0.7, False, 0.7)
    )
    # 세로 3:4 프레임: 가로는 0.7 전체, 세로는 0.7 * (3/4)/(4/3) = 0.39375 만 쓴다
    h = 0.7 * (3 / 4) / (4 / 3)
    portrait = (3 / 4, canvas)
    assert to_canvas(0.15, 0.5 - h / 2, False, 0.7, *portrait) == pytest.approx((0.0, 0.0))
    assert to_canvas(0.85, 0.5 + h / 2, False, 0.7, *portrait) == pytest.approx((1.0, 1.0))
    # 같은 거리를 움직이면 캔버스 px로도 가로·세로 같은 거리 (원이 타원이 되지 않음)
    d = 0.05
    x0, y0 = to_canvas(0.5, 0.5, False, 0.7, *portrait)
    x1, _ = to_canvas(0.5 + d, 0.5, False, 0.7, *portrait)
    _, y1 = to_canvas(0.5, 0.5 + d * 3 / 4, False, 0.7, *portrait)  # 프레임 px 기준 같은 거리
    assert (x1 - x0) * canvas == pytest.approx(y1 - y0)


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
