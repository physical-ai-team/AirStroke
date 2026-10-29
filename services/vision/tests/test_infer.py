import base64
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from vision.infer import decode_jpeg, process, to_hands
from vision.model import is_ready


def jpeg_b64(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return base64.b64encode(buf.tobytes()).decode()


def fake_result(points: list[tuple[float, float, float]], label="Right", score=0.9):
    landmarks = [SimpleNamespace(x=x, y=y, z=z) for x, y, z in points]
    return SimpleNamespace(
        hand_landmarks=[landmarks],
        handedness=[[SimpleNamespace(category_name=label, score=score)]],
    )


def test_decode_jpeg_returns_rgb():
    bgr = np.zeros((48, 64, 3), np.uint8)
    bgr[:, :, 2] = 255  # BGR 빨강
    rgb = decode_jpeg(jpeg_b64(bgr))
    assert rgb.shape == (48, 64, 3)
    assert rgb[0, 0, 0] > 200 and rgb[0, 0, 2] < 50


@pytest.mark.parametrize("data", ["", "!!!not-base64", base64.b64encode(b"not a jpeg").decode()])
def test_decode_jpeg_rejects_garbage(data):
    assert decode_jpeg(data) is None


def test_to_hands_converts_and_clamps():
    pts = [(0.5, 0.5, -0.01)] * 20 + [(1.2, -0.1, 0.03)]
    hands = to_hands(fake_result(pts, "Left", 0.87654))
    assert len(hands) == 1
    hand = hands[0]
    assert hand.handedness == "Left" and hand.score == 0.8765
    assert hand.points[0] == [0.5, 0.5, -0.01]
    assert hand.points[20] == [1.0, 0.0, 0.03]  # x·y 만 [0, 1]로 자르고 z 는 그대로


def test_to_hands_empty():
    assert to_hands(SimpleNamespace(hand_landmarks=[], handedness=[])) == []


def test_process_passes_timestamp_and_measures():
    seen = {}

    class FakeLandmarker:
        def detect_for_video(self, image, ts_ms):
            seen["shape"], seen["ts"] = (image.height, image.width), ts_ms
            return fake_result([(0.1, 0.2, 0.0)] * 21)

    out = process(FakeLandmarker(), jpeg_b64(np.zeros((48, 64, 3), np.uint8)), 1234)
    assert seen == {"shape": (48, 64), "ts": 1234}
    assert len(out.hands) == 1
    assert out.decode_ms >= 0 and out.infer_ms >= 0


def test_process_bad_jpeg_returns_none():
    class Never:
        def detect_for_video(self, image, ts_ms):
            raise AssertionError("should not be called")

    assert process(Never(), "AAAA", 1) is None


@pytest.mark.skipif(not is_ready(), reason="모델 없음: python vision/model.py")
def test_real_landmarker_no_hand():
    from vision.landmarker import create_landmarker

    lm = create_landmarker()
    try:
        out = process(lm, jpeg_b64(np.zeros((480, 640, 3), np.uint8)), 1000)
        assert out.hands == []
    finally:
        lm.close()
