import pytest
from pydantic import ValidationError

from airstroke_shared import channels
from airstroke_shared.schemas import CommandMsg, Cursor, FrameMsg, Hand, LandmarksMsg, Trace


def _hand():
    return Hand(handedness="Right", points=[[0.5, 0.5, 0.0]] * 21)


def test_frame_roundtrip():
    msg = FrameMsg(ts=1.0, seq=3, jpeg_base64="AAAA", mirror=True, trace=Trace(gw_recv=1.0))
    back = FrameMsg.model_validate_json(msg.model_dump_json())
    assert back == msg
    assert back.trace.capture is None


def test_trace_fields_optional():
    assert Trace().model_dump() == {
        "capture": None,
        "gw_recv": None,
        "vision_done": None,
        "gesture_done": None,
    }


def test_landmarks_requires_21_points():
    LandmarksMsg(ts=0, seq=0, hands=[_hand()])
    with pytest.raises(ValidationError):
        Hand(handedness="Right", points=[[0, 0, 0]] * 20)
    with pytest.raises(ValidationError):
        Hand(handedness="Right", points=[[0, 0]] * 21)


def test_unknown_fields_ignored():
    msg = CommandMsg.model_validate_json(
        '{"ts":1,"seq":1,"gesture":"index","action":"draw","cursor":{"x":0.1,"y":0.2},'
        '"future_field":123}'
    )
    assert msg.cursor == Cursor(x=0.1, y=0.2)


def test_invalid_action_rejected():
    with pytest.raises(ValidationError):
        CommandMsg(ts=1, seq=1, gesture="index", action="jump")


def test_channels():
    assert channels.frames("abc") == "frames:abc"
    assert channels.pattern(channels.LANDMARKS) == "landmarks:*"
    assert channels.session_of(b"commands:abc") == "abc"
