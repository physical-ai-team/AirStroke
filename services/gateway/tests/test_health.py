import json

import fakeredis
from fastapi.testclient import TestClient

from airstroke_shared import channels
from gateway.main import create_app


def test_health_reports_services():
    r = fakeredis.FakeAsyncRedis()
    with TestClient(create_app(r)) as client:
        client.portal.call(r.set, channels.heartbeat_key("vision"), json.dumps({"ts": 1}))
        body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["services"]["vision"]["alive"] is True
    assert body["services"]["gesture"]["alive"] is False


def test_root_redirects_to_canvas():
    with TestClient(create_app(fakeredis.FakeAsyncRedis())) as client:
        resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/canvas/"
