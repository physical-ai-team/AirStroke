import pytest
from test_core_units import make_points, pinch_points, thumb_up_points

from airstroke_shared.schemas import Hand, LandmarksMsg, Trace
from gesture.core import GestureParams, GestureSession


def run(messages: list[LandmarksMsg], **params):
    session = GestureSession(GestureParams(**params), clock=lambda: 123.0)
    return [session.process(m) for m in messages]


@pytest.mark.parametrize(
    ("name", "gesture", "action"),
    [
        ("gesture_index.json", "index", "draw"),
        ("gesture_index_middle.json", "index_middle", "move"),
        ("gesture_fist.json", "fist", "idle"),
        ("gesture_palm.json", "palm", "erase"),
    ],
)
def test_static_fixtures(fixture_messages, name, gesture, action):
    cmds = run(fixture_messages(name))
    # 디바운스 3프레임: 앞 두 프레임은 아직 none
    assert [c.gesture for c in cmds[:2]] == ["none", "none"]
    assert all(c.gesture == gesture and c.action == action for c in cmds[2:])
    assert all(c.cursor is not None and 0 <= c.cursor.x <= 1 and 0 <= c.cursor.y <= 1 for c in cmds)


def test_passthrough_fields_and_trace(fixture_messages):
    msgs = fixture_messages("gesture_fist.json")
    msgs[0] = msgs[0].model_copy(update={"trace": Trace(capture=1.0, gw_recv=2.0, vision_done=3.0)})
    cmd = run(msgs[:1])[0]
    assert (cmd.ts, cmd.seq) == (msgs[0].ts, msgs[0].seq)
    assert cmd.trace == Trace(capture=1.0, gw_recv=2.0, vision_done=3.0, gesture_done=123.0)


def test_no_hand_is_immediate_none():
    cmd = run([LandmarksMsg(ts=0, seq=0, hands=[])])[0]
    assert (cmd.gesture, cmd.action, cmd.cursor, cmd.stroke_id) == ("none", "idle", None, None)


def test_scenario_stroke_ids(fixture_messages):
    cmds = run(fixture_messages("scenario_draw.json"))
    # 확정된 제스처가 바뀌는 구간만 뽑기
    segments = []
    for c in cmds:
        if not segments or segments[-1][0] != c.gesture:
            segments.append((c.gesture, set()))
        segments[-1][1].add(c.stroke_id)
    assert [g for g, _ in segments] == ["none", "fist", "index", "index_middle", "index", "palm",
                                        "none"]  # fmt: skip
    assert [ids for g, ids in segments if g == "index"] == [{1}, {2}]
    assert all(ids == {None} for g, ids in segments if g != "index")


def hand_msgs(points_fns, start_seq=0) -> list[LandmarksMsg]:
    return [
        LandmarksMsg(
            ts=(start_seq + i) * 1000 / 15,
            seq=start_seq + i,
            hands=[Hand(handedness="Right", points=fn())],
        )
        for i, fn in enumerate(points_fns)
    ]


def test_undo_fires_once_per_thumb_up():
    fist = lambda: make_points(set())  # noqa: E731
    seq = [thumb_up_points] * 10 + [fist] * 4 + [thumb_up_points] * 8
    actions = [c.action for c in run(hand_msgs(seq))]
    # 6프레임 유지해야 확정되고, 들고 있는 동안은 다시 보내지 않는다
    assert actions[:5] == ["idle"] * 5
    assert actions[5] == "undo"
    assert actions.count("undo") == 2
    assert actions.index("undo", 6) == 14 + 5


def test_pinch_selects_and_freezes_cursor_on_release():
    seq = [pinch_points] * 8 + [lambda: make_points({"index"})] * 5
    cmds = run(hand_msgs(seq))
    assert [c.action for c in cmds[2:8]] == ["select"] * 6
    last_select = cmds[7].cursor
    # 손가락을 떼는 중(디바운스 2프레임)에는 아직 select 이고 커서는 마지막 집기 위치에 고정
    assert [c.action for c in cmds[8:10]] == ["select", "select"]
    assert cmds[8].cursor == last_select and cmds[9].cursor == last_select
    assert cmds[10].action == "draw" and cmds[10].stroke_id == 1


def test_portrait_frame_uses_aspect(fixture_messages):
    msgs = fixture_messages("gesture_index.json")
    landscape = run(msgs)[-1].cursor  # width/height 없음 = 가로 4:3과 같음
    portrait = run([m.model_copy(update={"width": 480, "height": 640}) for m in msgs])[-1].cursor
    # 세로는 중앙 영역이 납작해져서 같은 점이라도 y가 중앙에서 더 멀어진다
    assert portrait != landscape
    assert abs(portrait.y - 0.5) >= abs(landscape.y - 0.5)


def test_mirror_flips_cursor(fixture_messages):
    msgs = fixture_messages("gesture_index.json")
    mirrored = run(msgs)[-1].cursor
    plain = run([m.model_copy(update={"mirror": not m.mirror}) for m in msgs])[-1].cursor
    assert mirrored.x == pytest.approx(1 - plain.x, abs=1e-6)
    assert mirrored.y == pytest.approx(plain.y, abs=1e-6)
