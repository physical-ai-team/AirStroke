"""⑤ 좌표 변환 — 셀카면 x 반전, 카메라 중앙 영역을 캔버스 0~1로 매핑.

중앙 영역은 프레임 안에 들어가는 가장 큰 '캔버스 비율' 사각형의 ACTIVE_AREA배다.
프레임과 캔버스 비율이 같으면(가로 4:3) 가로·세로 모두 ACTIVE_AREA이고, 폰을 세로로 들어
비율이 다르면 영역이 납작해져서 가로·세로 배율이 같게 유지된다(원이 타원이 되지 않음).
그림판도 손 뼈대 21점에 같은 변환을 적용하므로 이 식을 바꾸면 docs/04-gestures.md도 갱신한다.
"""

from __future__ import annotations


def _clamp01(v: float) -> float:
    return min(1.0, max(0.0, v))


def active_region(
    active_area: float, frame_aspect: float | None, canvas_aspect: float | None
) -> tuple[float, float]:
    """중앙 영역의 (가로, 세로) 크기 — 프레임 기준 0~1 비율. 비율을 모르면 정사각 매핑."""
    if not frame_aspect or not canvas_aspect:
        return active_area, active_area
    return (
        active_area * min(1.0, canvas_aspect / frame_aspect),
        active_area * min(1.0, frame_aspect / canvas_aspect),
    )


def to_canvas(
    x: float,
    y: float,
    mirror: bool,
    active_area: float,
    frame_aspect: float | None = None,
    canvas_aspect: float | None = None,
) -> tuple[float, float]:
    if mirror:
        x = 1.0 - x
    w, h = active_region(active_area, frame_aspect, canvas_aspect)
    return _clamp01((x - (1.0 - w) / 2.0) / w), _clamp01((y - (1.0 - h) / 2.0) / h)
