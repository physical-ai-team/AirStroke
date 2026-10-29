"""저장된 랜드마크 JSON을 landmarks:{session} 으로 재생 (gesture 단독 개발용).

    python tools/mock_landmarks.py                                   # 기본 시나리오 1회
    python tools/mock_landmarks.py --file tests/fixtures/landmarks/gesture_palm.json --loop
    python tools/mock_landmarks.py --speed 0.5                        # 절반 속도

원본 ts 간격을 그대로 지키며, ts·seq·trace 는 재생 시점 값으로 다시 쓴다.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from _common import FIXTURES, add_session_arg, load_recording, redis_client

from airstroke_shared import channels
from airstroke_shared.schemas import LandmarksMsg, Trace, now_ms

DEFAULT_FILE = FIXTURES / "landmarks" / "scenario_draw.json"


def replay_messages(raw_messages: list[dict]) -> list[tuple[float, LandmarksMsg]]:
    """(이전 메시지와의 간격 초, 메시지) 목록."""
    msgs = [LandmarksMsg.model_validate(m) for m in raw_messages]
    out, prev_ts = [], None
    for m in msgs:
        gap = 0.0 if prev_ts is None else max(0.0, (m.ts - prev_ts) / 1000.0)
        out.append((gap, m))
        prev_ts = m.ts
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    add_session_arg(parser)
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--speed", type=float, default=1.0, help="재생 배속")
    args = parser.parse_args()

    items = replay_messages(load_recording(args.file)["messages"])
    r = redis_client()
    channel = channels.landmarks(args.session)
    print(f"재생: {args.file.name} → {channel} ({len(items)} 프레임, x{args.speed})")
    seq = 0
    try:
        while True:
            for gap, msg in items:
                time.sleep(gap / args.speed)
                ts = now_ms()
                out = msg.model_copy(
                    update={
                        "ts": ts,
                        "seq": seq,
                        "trace": Trace(capture=ts, gw_recv=ts, vision_done=ts),
                    }
                )
                r.publish(channel, out.model_dump_json())
                seq += 1
            if not args.loop:
                break
    except KeyboardInterrupt:
        pass
    print(f"종료: {seq} 프레임 전송")


if __name__ == "__main__":
    main()
