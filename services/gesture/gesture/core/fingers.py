"""② 손가락 펴짐 판별 — 손목(0번)~TIP 거리가 손목~PIP 거리보다 크면 펴진 것.

엄지는 손목 기준 비교가 불안정해서 펴짐 판별에 넣지 않고, 집기·엄지 세우기만 따로 본다.
거리는 x, y만 쓴다(z는 노이즈가 큼). 손 크기 = 손목~중지 뿌리(9번) 거리.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

WRIST = 0
THUMB_MCP, THUMB_IP, THUMB_TIP = 2, 3, 4
INDEX_MCP, INDEX_TIP = 5, 8
MIDDLE_MCP = 9

# 엄지 끝이 검지 뿌리에서 손 크기의 이 배 이상 떨어져야 '엄지 세움' (초기안)
THUMB_UP_MIN_RATIO = 0.6

# 손가락 이름 → (TIP, PIP) 인덱스 (MediaPipe 21점 순서)
FINGER_JOINTS: dict[str, tuple[int, int]] = {
    "index": (8, 6),
    "middle": (12, 10),
    "ring": (16, 14),
    "pinky": (20, 18),
}


def _dist_xy(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def hand_size(points: Sequence[Sequence[float]]) -> float:
    return _dist_xy(points[WRIST], points[MIDDLE_MCP])


def extended_fingers(points: Sequence[Sequence[float]]) -> frozenset[str]:
    """펴진 손가락 이름 집합 (엄지 제외)."""
    wrist = points[WRIST]
    return frozenset(
        name
        for name, (tip, pip) in FINGER_JOINTS.items()
        if _dist_xy(wrist, points[tip]) > _dist_xy(wrist, points[pip])
    )


def is_pinch(points: Sequence[Sequence[float]], ratio: float) -> bool:
    """엄지 끝과 검지 끝이 손 크기 × ratio 보다 가까우면 집기.

    주먹을 쥐어도 두 끝이 가까워지므로, 검지 끝이 검지 뿌리보다 손목에서 멀 때만(손가락이
    손바닥 밖으로 나와 있을 때만) 인정한다.
    """
    size = hand_size(points)
    if size <= 0:
        return False
    wrist = points[WRIST]
    if _dist_xy(wrist, points[INDEX_TIP]) <= _dist_xy(wrist, points[INDEX_MCP]):
        return False
    return _dist_xy(points[THUMB_TIP], points[INDEX_TIP]) < ratio * size


def is_thumb_up(points: Sequence[Sequence[float]]) -> bool:
    """엄지가 위로 서 있고(끝 → IP → MCP 순으로 위) 검지 뿌리에서 충분히 떨어져 있으면 True.

    네 손가락이 접혔는지는 호출 쪽에서 extended_fingers로 확인한다. 이미지 y는 아래로 증가.
    '위로'를 조건에 넣어 엄지를 감싸 쥔 주먹과 구분한다.
    """
    tip, ip, mcp = points[THUMB_TIP], points[THUMB_IP], points[THUMB_MCP]
    upright = tip[1] < ip[1] < mcp[1]
    return upright and _dist_xy(tip, points[INDEX_MCP]) > THUMB_UP_MIN_RATIO * hand_size(points)
