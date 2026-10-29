"""세션별 HandLandmarker(VIDEO 모드) 생성·보관·해제.

VIDEO 모드는 인스턴스마다 타임스탬프가 단조 증가해야 하므로 세션마다 따로 만든다.
SessionLandmarkers 는 MediaPipe 와 무관한 순수 로직이라 가짜 factory 로 테스트한다.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from . import config
from .model import MODEL_PATH


class Closable(Protocol):
    def close(self) -> None: ...


T = TypeVar("T", bound=Closable)


@dataclass
class _Entry(Generic[T]):
    landmarker: T
    last_ts_ms: int
    last_used: float


class SessionLandmarkers(Generic[T]):
    """세션 ID → 인스턴스. 첫 프레임에서 만들고, idle_sec 동안 안 쓰이면 reap()이 닫는다.

    acquire()·reap()은 같은 루프(추론 루프)에서만 부른다. 그래야 추론 중인 인스턴스를
    닫는 일이 없다.
    """

    def __init__(
        self,
        factory: Callable[[], T],
        idle_sec: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._factory = factory
        self._idle_sec = idle_sec
        self._clock = clock
        self._entries: dict[str, _Entry[T]] = {}

    def acquire(self, session_id: str, ts_ms: float) -> tuple[T, int, bool]:
        """(인스턴스, detect_for_video 에 넘길 타임스탬프, 새로 만들었는지)를 돌려준다.

        타임스탬프는 정수 ms 이고, 이전 값보다 크지 않으면 이전 값 + 1 로 올린다.
        """
        now = self._clock()
        ts = int(ts_ms)
        entry = self._entries.get(session_id)
        created = entry is None
        if entry is None:
            entry = _Entry(self._factory(), ts, now)
            self._entries[session_id] = entry
        else:
            ts = max(ts, entry.last_ts_ms + 1)
            entry.last_ts_ms = ts
            entry.last_used = now
        return entry.landmarker, ts, created

    def reap(self) -> list[str]:
        """idle_sec 이상 쓰이지 않은 세션을 닫고 그 ID 목록을 돌려준다."""
        now = self._clock()
        idle = [sid for sid, e in self._entries.items() if now - e.last_used >= self._idle_sec]
        for sid in idle:
            self._entries.pop(sid).landmarker.close()
        return idle

    def close_all(self) -> None:
        for entry in self._entries.values():
            entry.landmarker.close()
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, session_id: str) -> bool:
        return session_id in self._entries


def create_landmarker():
    """설정(.env)대로 CPU·VIDEO 모드 HandLandmarker 를 만든다."""
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import (
        HandLandmarker,
        HandLandmarkerOptions,
        RunningMode,
    )

    options = HandLandmarkerOptions(
        base_options=BaseOptions(
            model_asset_path=str(MODEL_PATH), delegate=BaseOptions.Delegate.CPU
        ),
        running_mode=RunningMode.VIDEO,
        num_hands=config.NUM_HANDS,
        min_hand_detection_confidence=config.MIN_HAND_DETECTION_CONFIDENCE,
        min_hand_presence_confidence=config.MIN_HAND_PRESENCE_CONFIDENCE,
        min_tracking_confidence=config.MIN_TRACKING_CONFIDENCE,
    )
    return HandLandmarker.create_from_options(options)
