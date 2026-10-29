import base64
import json
import struct
import time

import fakeredis
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from airstroke_shared import channels
from airstroke_shared.schemas import CommandMsg, Cursor, FrameMsg, LandmarksMsg, now_ms
from gateway.main import create_app
from gateway.protocol import MobileFrameHeader, pack_frame

JPEG = b"\xff\xd8fake-jpeg\xff\xd9"


@pytest.fixture
def env():
    r = fakeredis.FakeAsyncRedis()
    with TestClient(create_app(r)) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        yield client, r, sid


def next_msg(ws, skip=("ping",)):
    """다음 메시지(바이너리면 bytes, 텍스트면 dict). skip에 있는 type은 건너뛴다."""
    while True:
        m = ws.receive()
        if m["type"] == "websocket.close":
            raise WebSocketDisconnect(m.get("code", 1000))
        if m.get("bytes") is not None:
            return m["bytes"]
        data = json.loads(m["text"])
        if data["type"] not in skip:
            return data


def publish(client, r, channel, msg):
    client.portal.call(r.publish, channel, msg.model_dump_json())


def wait_subscribers(client, r, channel, expected):
    for _ in range(200):
        [(_, n)] = client.portal.call(r.pubsub_numsub, channel)
        if n == expected:
            return
        time.sleep(0.01)
    raise AssertionError(f"{channel}: 구독자 {n} != {expected}")


def published_frame(client, sub) -> FrameMsg:
    """테스트용 구독에서 다음 frames 메시지 (구독 확인 메시지는 건너뜀)."""
    for _ in range(20):
        m = client.portal.call(sub.get_message, True, 0.1)
        if m is not None:
            client.portal.call(sub.aclose)
            return FrameMsg.model_validate_json(m["data"])
    raise AssertionError("frames 메시지 없음")


def frame(seq, capture_ts=None, mirror=False):
    return pack_frame(MobileFrameHeader(seq=seq, capture_ts=capture_ts, mirror=mirror), JPEG)


@pytest.mark.parametrize("role", ["pc", "mobile"])
def test_unknown_session_closed_4404(env, role):
    client, _, _ = env
    with client.websocket_connect(f"/ws/{role}/nope") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            next_msg(ws)
    assert exc.value.code == 4404


def test_pc_forwards_landmarks_and_commands(env):
    client, r, sid = env
    with client.websocket_connect(f"/ws/pc/{sid}") as pc:
        assert next_msg(pc) == {"type": "status", "mobile_connected": False}
        publish(client, r, channels.landmarks(sid), LandmarksMsg(ts=1, seq=5, mirror=True))
        cmd = CommandMsg(
            ts=2, seq=5, gesture="index", action="draw", cursor=Cursor(x=0.1, y=0.2), stroke_id=1
        )
        publish(client, r, channels.commands(sid), cmd)
        lm = next_msg(pc)
        cm = next_msg(pc)
    assert lm["type"] == "landmarks" and lm["data"]["seq"] == 5 and lm["data"]["hands"] == []
    assert cm["type"] == "command" and cm["data"]["cursor"] == {"x": 0.1, "y": 0.2}
    assert cm["data"]["stroke_id"] == 1


def test_status_follows_mobile_connection(env):
    client, _, sid = env
    with client.websocket_connect(f"/ws/pc/{sid}") as pc:
        assert next_msg(pc)["mobile_connected"] is False
        with client.websocket_connect(f"/ws/mobile/{sid}"):
            assert next_msg(pc) == {"type": "status", "mobile_connected": True}
        assert next_msg(pc) == {"type": "status", "mobile_connected": False}


def test_mobile_frame_published_with_converted_capture(env):
    client, r, sid = env
    sub = r.pubsub()
    client.portal.call(sub.subscribe, channels.frames(sid))
    skew = 5000.0  # 폰 시계가 5초 빠름
    with client.websocket_connect(f"/ws/mobile/{sid}") as ws:
        ping = next_msg(ws, skip=())
        assert ping["type"] == "ping"
        ws.send_json({"type": "pong", "id": ping["id"], "t_server": ping["t_server"],
                      "t_client": now_ms() + skew})  # fmt: skip
        clock = next_msg(ws)
        assert clock["type"] == "clock"
        assert clock["offset_ms"] == pytest.approx(skew, abs=clock["rtt_ms"] + 50)

        captured_at = now_ms()
        ws.send_bytes(frame(seq=7, capture_ts=captured_at + skew, mirror=True))
        assert next_msg(ws) == {"type": "ack", "seq": 7}

    msg = published_frame(client, sub)
    assert (msg.seq, msg.mirror) == (7, True)
    assert base64.b64decode(msg.jpeg_base64) == JPEG
    assert msg.trace.gw_recv == msg.ts
    assert msg.trace.capture == pytest.approx(captured_at, abs=clock["rtt_ms"] + 50)
    assert msg.trace.capture <= msg.trace.gw_recv + 50


def test_capture_is_none_before_clock_estimate(env):
    client, r, sid = env
    sub = r.pubsub()
    client.portal.call(sub.subscribe, channels.frames(sid))
    with client.websocket_connect(f"/ws/mobile/{sid}") as ws:
        ws.send_bytes(frame(seq=0, capture_ts=123.0))  # ping에 답하지 않은 상태
        assert next_msg(ws) == {"type": "ack", "seq": 0}
    assert published_frame(client, sub).trace.capture is None


def test_bad_frame_dropped_without_ack(env):
    client, _, sid = env
    with client.websocket_connect(f"/ws/mobile/{sid}") as ws:
        ws.send_bytes(b"junk")
        ws.send_bytes(frame(seq=8))
        assert next_msg(ws) == {"type": "ack", "seq": 8}


def test_new_mobile_replaces_old(env):
    client, _, sid = env
    with client.websocket_connect(f"/ws/pc/{sid}") as pc:
        next_msg(pc)
        with client.websocket_connect(f"/ws/mobile/{sid}") as old:
            assert next_msg(pc)["mobile_connected"] is True
            with client.websocket_connect(f"/ws/mobile/{sid}") as new:
                with pytest.raises(WebSocketDisconnect) as exc:
                    next_msg(old)
                assert exc.value.code == 4409
                assert next_msg(pc)["mobile_connected"] is True  # 끊김 없이 유지
                new.send_bytes(frame(seq=1))
                assert next_msg(new) == {"type": "ack", "seq": 1}
        assert next_msg(pc)["mobile_connected"] is False


def test_pip_frames_only_while_enabled(env):
    client, r, sid = env
    frames_ch = channels.frames(sid)
    msg = FrameMsg(ts=10, seq=3, jpeg_base64=base64.b64encode(JPEG).decode(), mirror=True)
    cmd = CommandMsg(ts=11, seq=3, gesture="none", action="idle")
    with client.websocket_connect(f"/ws/pc/{sid}") as pc:
        next_msg(pc)
        # 기본값(꺼짐): frames를 구독하지도 보내지도 않는다
        wait_subscribers(client, r, frames_ch, 0)
        publish(client, r, frames_ch, msg)
        publish(client, r, channels.commands(sid), cmd)
        assert next_msg(pc)["type"] == "command"

        pc.send_json({"type": "pip", "enabled": True})
        wait_subscribers(client, r, frames_ch, 1)
        publish(client, r, frames_ch, msg)
        data = next_msg(pc)
        (n,) = struct.unpack(">I", data[:4])
        header = json.loads(data[4 : 4 + n])
        assert (header["seq"], header["mirror"]) == (3, True)
        assert data[4 + n :] == JPEG

        pc.send_json({"type": "pip", "enabled": False})
        wait_subscribers(client, r, frames_ch, 0)
