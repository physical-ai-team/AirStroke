"""② 손가락 펴짐 판별 — 손목(0번)~TIP 거리가 손목~PIP 거리보다 크면 펴진 것.

엄지는 손목 기준 비교가 불안정해서 판별하지 않는다. 거리는 x, y만 쓴다(z는 노이즈가 큼).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

WRIST = 0
INDEX_TIP = 8

# 손가락 이름 → (TIP, PIP) 인덱스 (MediaPipe 21점 순서)
FINGER_JOINTS: dict[str, tuple[int, int]] = {
    "index": (8, 6),
    "middle": (12, 10),
    "ring": (16, 14),
    "pinky": (20, 18),
}


def _dist_xy(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def extended_fingers(points: Sequence[Sequence[float]]) -> frozenset[str]:
    """펴진 손가락 이름 집합 (엄지 제외)."""
    wrist = points[WRIST]
    return frozenset(
        name
        for name, (tip, pip) in FINGER_JOINTS.items()
        if _dist_xy(wrist, points[tip]) > _dist_xy(wrist, points[pip])
    )
