"""⑤ 좌표 변환 — 셀카면 x 반전, 카메라 중앙 ACTIVE_AREA를 캔버스 0~1로 매핑.

그림판도 손 뼈대 21점에 같은 변환을 적용하므로 이 식을 바꾸면 docs/04-gestures.md도 갱신한다.
"""

from __future__ import annotations


def _clamp01(v: float) -> float:
    return min(1.0, max(0.0, v))


def to_canvas(x: float, y: float, mirror: bool, active_area: float) -> tuple[float, float]:
    if mirror:
        x = 1.0 - x
    m = (1.0 - active_area) / 2.0
    return _clamp01((x - m) / active_area), _clamp01((y - m) / active_area)
