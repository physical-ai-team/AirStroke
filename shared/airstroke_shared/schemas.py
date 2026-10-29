"""Redis 채널로 오가는 메시지 스키마.

시간 단위는 모두 epoch 밀리초(float)이며 gateway 시계 기준이다.
폰·PC에서 찍은 시각은 gateway가 ping/pong으로 추정한 시계 차이를 더해 환산한다.
"""

from __future__ import annotations

import time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

NUM_LANDMARKS = 21


def now_ms() -> float:
    return time.time() * 1000.0


class _Msg(BaseModel):
    # 모르는 필드는 무시해서, 스키마에 필드가 추가돼도 기존 서비스가 깨지지 않게 한다
    model_config = ConfigDict(extra="ignore")


class Trace(_Msg):
    """단계별 타임스탬프. 각 서비스는 자기 단계만 채우고 나머지는 그대로 넘긴다."""

    capture: float | None = None  # 폰 촬영 (gateway 시계로 환산)
    gw_recv: float | None = None  # gateway 수신
    vision_done: float | None = None  # vision 추론 완료
    gesture_done: float | None = None  # gesture 처리 완료
    # PC 표시 시각은 브라우저에서만 측정한다 (메시지에 실리지 않음)


class FrameMsg(_Msg):
    """frames:{session_id}"""

    ts: float
    seq: int
    jpeg_base64: str
    mirror: bool = False  # 전면(셀카) 카메라면 True → gesture가 x좌표를 반전
    # JPEG 크기(px). 폰을 세로로 들면 width < height. None이면 CAMERA_WIDTH:HEIGHT 비율로 간주
    width: int | None = None
    height: int | None = None
    trace: Trace = Field(default_factory=Trace)


Point = Annotated[list[float], Field(min_length=3, max_length=3)]  # [x, y, z], 0~1 정규화


class Hand(_Msg):
    handedness: Literal["Left", "Right"]
    score: float = 1.0
    points: list[Point] = Field(min_length=NUM_LANDMARKS, max_length=NUM_LANDMARKS)


class LandmarksMsg(_Msg):
    """landmarks:{session_id} — 좌표는 카메라 원본 기준(반전·매핑 전)."""

    ts: float
    seq: int
    mirror: bool = False
    width: int | None = None  # 원본 프레임 크기 (FrameMsg 값을 그대로 옮김)
    height: int | None = None
    hands: list[Hand] = Field(default_factory=list)
    trace: Trace = Field(default_factory=Trace)


Gesture = Literal["index", "index_middle", "fist", "palm", "pinch", "thumb_up", "unknown", "none"]
# select: 집고 있는 동안 매 프레임(그림판 팔레트), undo: thumb_up이 확정되는 순간 한 번만
Action = Literal["draw", "move", "idle", "erase", "select", "undo"]


class Cursor(_Msg):
    x: float  # 0~1, 캔버스 기준 (반전·중앙영역 매핑 완료)
    y: float


class CommandMsg(_Msg):
    """commands:{session_id}"""

    ts: float
    seq: int
    gesture: Gesture
    action: Action
    cursor: Cursor | None = None  # 손이 없으면 None
    # draw가 새로 시작될 때마다 증가. PC는 값이 바뀌면 이전 좌표를 버리고 새 선을 시작한다.
    stroke_id: int | None = None
    trace: Trace = Field(default_factory=Trace)
