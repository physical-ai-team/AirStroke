"""가짜 commands 를 commands:{session} 으로 흘려보냄 (그림판 UI 단독 개발용).

    python tools/mock_commands.py                 # 시나리오 반복 (Ctrl+C 종료)
    python tools/mock_commands.py --fps 30 --once

시나리오(약 13초): 손 없음 → 주먹(idle) → 8자 그리기 → 펜 들고 이동 → 원 그리기
→ 손바닥 지우개로 훑기. draw 구간마다 stroke_id 가 1씩 증가한다.
"""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass

from _common import add_session_arg, redis_client

from airstroke_shared import channels
from airstroke_shared.schemas import Action, CommandMsg, Cursor, Gesture, Trace, now_ms


@dataclass
class Phase:
    seconds: float
    gesture: Gesture
    action: Action
    path: str | None  # None이면 손 없음 (cursor=None)


PHASES = [
    Phase(1.0, "none", "idle", None),
    Phase(1.0, "fist", "idle", "rest"),
    Phase(4.0, "index", "draw", "figure8"),
    Phase(1.0, "index_middle", "move", "to_circle"),
    Phase(3.0, "index", "draw", "circle"),
    Phase(2.0, "palm", "erase", "sweep"),
    Phase(1.0, "fist", "idle", "rest"),
]


def point_on(path: str, t: float) -> tuple[float, float]:
    """t: 구간 진행률 0~1 → 캔버스 정규화 좌표."""
    if path == "rest":
        return 0.5, 0.5
    if path == "figure8":
        a = t * 2 * math.pi
        return 0.35 + 0.2 * math.sin(a), 0.5 + 0.2 * math.sin(a) * math.cos(a)
    if path == "to_circle":
        start, end = (0.35, 0.5), (0.85, 0.5)
        return start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t
    if path == "circle":
        a = t * 2 * math.pi
        return 0.7 + 0.15 * math.cos(a), 0.5 + 0.15 * math.sin(a)
    if path == "sweep":
        return 0.2 + 0.6 * t, 0.5 + 0.1 * math.sin(t * 6 * math.pi)
    raise ValueError(path)


def scenario(fps: float):
    """(gesture, action, cursor, 새 선 시작 여부) 를 fps 간격으로 생성 — 시나리오 1회분."""
    for phase in PHASES:
        n = max(1, round(phase.seconds * fps))
        for i in range(n):
            cursor = None
            if phase.path is not None:
                x, y = point_on(phase.path, i / max(1, n - 1))
                cursor = Cursor(x=x, y=y)
            yield phase.gesture, phase.action, cursor, phase.action == "draw" and i == 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    add_session_arg(parser)
    parser.add_argument("--fps", type=float, default=15)
    parser.add_argument("--once", action="store_true", help="시나리오 1회만")
    args = parser.parse_args()

    r = redis_client()
    channel = channels.commands(args.session)
    print(f"송출: {channel} @ {args.fps}fps (Ctrl+C 종료)")
    seq, stroke_id = 0, 0
    try:
        while True:
            for gesture, action, cursor, new_stroke in scenario(args.fps):
                stroke_id += new_stroke
                ts = now_ms()
                msg = CommandMsg(
                    ts=ts, seq=seq, gesture=gesture, action=action, cursor=cursor,
                    stroke_id=stroke_id if action == "draw" else None,
                    trace=Trace(capture=ts, gw_recv=ts, vision_done=ts, gesture_done=ts),
                )  # fmt: skip
                r.publish(channel, msg.model_dump_json())
                seq += 1
                time.sleep(1.0 / args.fps)
            if args.once:
                break
    except KeyboardInterrupt:
        pass
    print(f"종료: {seq} 메시지")


if __name__ == "__main__":
    main()
