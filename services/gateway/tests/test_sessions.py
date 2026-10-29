import json

import fakeredis
import pytest
from fastapi.testclient import TestClient

from airstroke_shared import channels
from gateway import config
from gateway.main import create_app
from gateway.sessions import mobile_url


@pytest.mark.parametrize(
    "host, public_host, expected",
    [
        ("192.168.45.89:8443", "10.0.0.1", "https://192.168.45.89:8443/mobile/?s=abc"),
        ("localhost:9443", "192.168.45.89", "https://192.168.45.89:9443/mobile/?s=abc"),
        ("127.0.0.1:8443", "192.168.45.89", "https://192.168.45.89:8443/mobile/?s=abc"),
        ("[::1]:8443", "192.168.45.89", "https://192.168.45.89:8443/mobile/?s=abc"),
        ("localhost", "192.168.45.89", "https://192.168.45.89/mobile/?s=abc"),
        ("localhost:8443", "", "https://localhost:8443/mobile/?s=abc"),  # PUBLIC_HOST 미설정
    ],
)
def test_mobile_url(host, public_host, expected):
    assert mobile_url("https", host, public_host, "abc") == expected


def test_create_session_sets_key_with_ttl(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_HOST", "192.168.45.89")
    r = fakeredis.FakeAsyncRedis()
    with TestClient(create_app(r), base_url="http://localhost:8443") as client:
        body = client.post("/api/sessions").json()
        sid = body["session_id"]
        raw = client.portal.call(r.get, channels.session_key(sid))
        ttl = client.portal.call(r.ttl, channels.session_key(sid))
    assert body["mobile_url"] == f"http://192.168.45.89:8443/mobile/?s={sid}"
    assert body["qr_url"] == f"/api/sessions/{sid}/qr.svg"
    assert "created" in json.loads(raw)
    assert 0 < ttl <= config.SESSION_TTL_SEC


def test_session_ids_are_unique():
    with TestClient(create_app(fakeredis.FakeAsyncRedis())) as client:
        ids = {client.post("/api/sessions").json()["session_id"] for _ in range(20)}
    assert len(ids) == 20


def test_qr_svg():
    with TestClient(create_app(fakeredis.FakeAsyncRedis())) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        resp = client.get(f"/api/sessions/{sid}/qr.svg")
        missing = client.get("/api/sessions/nope/qr.svg")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in resp.content
    assert missing.status_code == 404


def test_config():
    with TestClient(create_app(fakeredis.FakeAsyncRedis())) as client:
        body = client.get("/api/config").json()
    assert body == {
        "camera": {
            "width": config.CAMERA_WIDTH,
            "height": config.CAMERA_HEIGHT,
            "fps": config.CAMERA_FPS,
            "jpeg_quality": config.JPEG_QUALITY,
        },
        "max_inflight_frames": config.MAX_INFLIGHT_FRAMES,
        "active_area": config.ACTIVE_AREA,
    }
