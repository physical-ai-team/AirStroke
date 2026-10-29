"""실제 vision 출력(landmarks:{session})을 JSON 파일로 녹화.

    python tools/record_landmarks.py --session dev --duration 10
    python tools/record_landmarks.py --out tests/fixtures/landmarks/real_draw.json

Ctrl+C 또는 --duration 경과 시 저장. 파일 형식은 mock_landmarks.py 입력과 같다.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from _common import RECORDINGS, add_session_arg, redis_client

from airstroke_shared import SCHEMA_VERSION, channels
from airstroke_shared.schemas import LandmarksMsg


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    add_session_arg(parser)
    parser.add_argument(
        "--out", type=Path, help="저장 경로 (기본: recordings/landmarks_<세션>_<시각>.json)"
    )
    parser.add_argument("--duration", type=float, default=0, help="녹화 시간(초), 0이면 Ctrl+C까지")
    args = parser.parse_args()

    out = args.out or RECORDINGS / f"landmarks_{args.session}_{datetime.now():%Y%m%d_%H%M%S}.json"
    r = redis_client()
    pubsub = r.pubsub(ignore_subscribe_messages=True)
    channel = channels.landmarks(args.session)
    pubsub.subscribe(channel)
    print(f"녹화 시작: {channel} (Ctrl+C로 종료)")

    messages: list[dict] = []
    start = time.monotonic()
    try:
        while not args.duration or time.monotonic() - start < args.duration:
            msg = pubsub.get_message(timeout=0.5)
            if msg is None:
                continue
            messages.append(LandmarksMsg.model_validate_json(msg["data"]).model_dump())
            if len(messages) % 30 == 0:
                print(f"  {len(messages)} 프레임")
    except KeyboardInterrupt:
        pass

    out.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "meta": {
            "session": args.session,
            "recorded_at": datetime.now().isoformat(timespec="seconds"),
            "count": len(messages),
            "schema_version": SCHEMA_VERSION,
            "synthetic": False,
        },
        "messages": messages,
    }
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"저장: {out} ({len(messages)} 프레임)")


if __name__ == "__main__":
    main()
