"""프레임 한 장 처리: JPEG(base64) 디코드 → HandLandmarker 추론 → Hand 목록.

Redis·asyncio 와 무관한 순수 코드라 main.py 는 process() 를 스레드에서 부르기만 한다.
"""

from __future__ import annotations

import base64
import binascii
import time
from dataclasses import dataclass

import cv2
import mediapipe as mp
import numpy as np

from airstroke_shared.schemas import Hand


@dataclass
class Processed:
    hands: list[Hand]
    decode_ms: float
    infer_ms: float


# JPEG 를 1/2, 1/4, 1/8 크기로 바로 디코드하는 플래그 (전체 디코드 후 줄이는 것보다 싸다)
_REDUCED = (
    (8, cv2.IMREAD_REDUCED_COLOR_8),
    (4, cv2.IMREAD_REDUCED_COLOR_4),
    (2, cv2.IMREAD_REDUCED_COLOR_2),
)


def _jpeg_width(buf: np.ndarray) -> int | None:
    """JPEG SOF 마커에서 가로 크기만 읽는다 (디코드 없이)."""
    data = buf.tobytes()
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            return None
        marker, length = data[i + 1], int.from_bytes(data[i + 2 : i + 4], "big")
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            return int.from_bytes(data[i + 7 : i + 9], "big")
        i += 2 + length
    return None


def decode_jpeg(jpeg_base64: str, max_width: int | None = None) -> np.ndarray | None:
    """base64 JPEG → RGB 배열. 깨진 데이터면 None.

    max_width 를 주면 가로가 그보다 넓을 때 비율을 유지하며 줄인다 (좌표는 0~1 정규화라 영향 없음).
    """
    try:
        buf = np.frombuffer(base64.b64decode(jpeg_base64, validate=True), np.uint8)
    except (binascii.Error, ValueError):
        return None
    if buf.size == 0:
        return None
    flag = cv2.IMREAD_COLOR
    if max_width:
        width = _jpeg_width(buf)
        if width:
            flag = next((f for k, f in _REDUCED if width // k >= max_width), cv2.IMREAD_COLOR)
    bgr = cv2.imdecode(buf, flag)
    if bgr is None:
        return None
    if max_width and bgr.shape[1] > max_width:
        h = round(bgr.shape[0] * max_width / bgr.shape[1])
        bgr = cv2.resize(bgr, (max_width, h), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _clamp01(v: float) -> float:
    return min(1.0, max(0.0, v))


def to_hands(result) -> list[Hand]:
    """HandLandmarkerResult → Hand 목록. 좌표는 원본 기준(반전 없음), x·y 는 [0, 1]로 자른다.

    손이 화면 밖으로 걸치면 MediaPipe 가 범위 밖 값을 추정해 내므로 계약(x, y ∈ [0, 1])에 맞춘다.
    handedness 는 MediaPipe 값 그대로다 (README 주의 참고).
    """
    hands = []
    for points, categories in zip(result.hand_landmarks, result.handedness, strict=True):
        top = categories[0]
        hands.append(
            Hand(
                handedness=top.category_name,
                score=round(top.score, 4),
                points=[[_clamp01(p.x), _clamp01(p.y), p.z] for p in points],
            )
        )
    return hands


def process(
    landmarker, jpeg_base64: str, ts_ms: int, max_width: int | None = None
) -> Processed | None:
    """디코드 + 추론. 디코드 실패면 None. 블로킹이므로 asyncio.to_thread 로 부를 것."""
    t0 = time.perf_counter()
    rgb = decode_jpeg(jpeg_base64, max_width)
    if rgb is None:
        return None
    t1 = time.perf_counter()
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = landmarker.detect_for_video(image, ts_ms)
    t2 = time.perf_counter()
    return Processed(to_hands(result), (t1 - t0) * 1000, (t2 - t1) * 1000)
