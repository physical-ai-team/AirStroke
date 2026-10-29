import math
from pathlib import Path

import pytest
from _common import FIXTURES, load_recording
from gen_cert import make_cert, set_env_value
from mock_commands import scenario
from mock_landmarks import replay_messages

from airstroke_shared.schemas import CommandMsg, LandmarksMsg

LANDMARK_FILES = sorted((FIXTURES / "landmarks").glob("*.json"))
TIPS = {"index": (8, 6), "middle": (12, 10), "ring": (16, 14), "pinky": (20, 18)}


def _extended(points, finger):
    tip, pip = TIPS[finger]
    return math.dist(points[0][:2], points[tip][:2]) > math.dist(points[0][:2], points[pip][:2])


def test_fixtures_exist():
    assert LANDMARK_FILES, "python tools/gen_synthetic_landmarks.py 로 fixture 생성 필요"


@pytest.mark.parametrize("path", LANDMARK_FILES, ids=lambda p: p.name)
def test_fixture_matches_schema(path: Path):
    for raw in load_recording(path)["messages"]:
        LandmarksMsg.model_validate(raw)


@pytest.mark.parametrize(
    "pose, expected",
    [
        ("index", {"index"}),
        ("index_middle", {"index", "middle"}),
        ("fist", set()),
        ("palm", {"index", "middle", "ring", "pinky"}),
    ],
)
def test_synthetic_pose_geometry(pose, expected):
    msg = load_recording(FIXTURES / "landmarks" / f"gesture_{pose}.json")["messages"][0]
    points = msg["hands"][0]["points"]
    assert {f for f in TIPS if _extended(points, f)} == expected


def test_replay_keeps_gaps():
    items = replay_messages(
        load_recording(FIXTURES / "landmarks" / "scenario_draw.json")["messages"]
    )
    assert items[0][0] == 0
    assert all(abs(gap - 1 / 15) < 1e-6 for gap, _ in items[1:])


def test_mock_commands_scenario_valid():
    frames = list(scenario(fps=15))
    assert sum(new for *_, new in frames) == 2  # draw 구간 2개
    for gesture, action, cursor, _ in frames:
        CommandMsg(ts=0, seq=0, gesture=gesture, action=action, cursor=cursor)
        if cursor:
            assert 0 <= cursor.x <= 1 and 0 <= cursor.y <= 1


def test_set_env_value_replaces_or_appends():
    assert set_env_value("A=1\nPUBLIC_HOST=\nB=2\n", "PUBLIC_HOST", "10.0.0.5") == (
        "A=1\nPUBLIC_HOST=10.0.0.5\nB=2\n"
    )
    assert set_env_value("A=1", "PUBLIC_HOST", "10.0.0.5") == "A=1\nPUBLIC_HOST=10.0.0.5\n"


def test_make_cert_has_san():
    from cryptography import x509

    cert_pem, _ = make_cert("192.168.0.10", days=1)
    cert = x509.load_pem_x509_certificate(cert_pem)
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "192.168.0.10" in [str(ip) for ip in san.get_values_for_type(x509.IPAddress)]
    assert "localhost" in san.get_values_for_type(x509.DNSName)
