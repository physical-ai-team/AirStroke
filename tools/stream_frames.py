"""폰 없이 테스트: 노트북 웹캠 또는 영상 파일 → frames:{session} 에 직접 publish.

    python tools/stream_frames.py                       # 웹캠 0번, 셀카이므로 mirror=True
    python tools/stream_frames.py --source clip.mp4 --loop
    python tools/stream_frames.py --show                # 보내는 영상 미리보기 창

gateway를 거치지 않으므로 trace.capture 와 trace.gw_recv 를 이 스크립트가 채운다.
해상도·fps·JPEG 품질 기본값은 .env (CAMERA_WIDTH/HEIGHT/FPS, JPEG_QUALITY).
"""

from __future__ import annotations

import argparse
import base64
import sys
import time

import cv2
from _common import add_session_arg, redis_client

from airstroke_shared import channels
from airstroke_shared.log import get_logger
from airstroke_shared.schemas import FrameMsg, Trace, now_ms
from airstroke_shared.settings import env_int

log = get_logger("stream_frames")


def open_source(source: str) -> tuple[cv2.VideoCapture, bool]:
    if source.isdigit():
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        return cv2.VideoCapture(int(source), backend), True
    return cv2.VideoCapture(source), False


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    add_session_arg(parser)
    parser.add_argument("--source", default="0", help="웹캠 번호 또는 영상 파일 경로")
    parser.add_argument("--fps", type=float, default=env_int("CAMERA_FPS", 15))
    parser.add_argument("--width", type=int, default=env_int("CAMERA_WIDTH", 640))
    parser.add_argument("--height", type=int, default=env_int("CAMERA_HEIGHT", 480))
    parser.add_argument("--quality", type=int, default=env_int("JPEG_QUALITY", 70))
    parser.add_argument("--mirror", action=argparse.BooleanOptionalAction, default=None,
                        help="기본: 웹캠이면 True, 파일이면 False")  # fmt: skip
    parser.add_argument("--loop", action="store_true", help="영상 파일 반복 재생")
    parser.add_argument("--show", action="store_true", help="미리보기 창 표시 (q로 종료)")
    args = parser.parse_args()

    cap, is_camera = open_source(args.source)
    if not cap.isOpened():
        raise SystemExit(f"소스를 열 수 없음: {args.source}")
    mirror = is_camera if args.mirror is None else args.mirror
    r = redis_client()
    channel = channels.frames(args.session)
    interval = 1.0 / args.fps
    log.info("start", extra={"channel": channel, "source": args.source, "mirror": mirror,
                             "fps": args.fps, "size": [args.width, args.height]})  # fmt: skip

    seq, sent, t_report = 0, 0, time.monotonic()
    next_t = time.monotonic()
    try:
        while True:
            ok, img = cap.read()
            if not ok:
                if not is_camera and args.loop:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                break
            img = cv2.resize(img, (args.width, args.height))
            ok, jpeg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, args.quality])
            if not ok:
                continue
            ts = now_ms()
            msg = FrameMsg(
                ts=ts,
                seq=seq,
                jpeg_base64=base64.b64encode(jpeg.tobytes()).decode("ascii"),
                mirror=mirror,
                trace=Trace(capture=ts, gw_recv=ts),
            )
            r.publish(channel, msg.model_dump_json())
            seq += 1
            sent += 1

            if args.show:
                cv2.imshow("stream_frames (q: quit)", cv2.flip(img, 1) if mirror else img)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            now = time.monotonic()
            if now - t_report >= 5:
                log.info("stats", extra={"fps": round(sent / (now - t_report), 1),
                                         "jpeg_kb": round(len(jpeg) / 1024, 1)})  # fmt: skip
                sent, t_report = 0, now
            next_t += interval
            time.sleep(max(0.0, next_t - time.monotonic()))
            next_t = max(next_t, time.monotonic() - interval)  # 밀리면 따라잡지 않고 리셋
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        log.info("stop", extra={"sent_total": seq})


if __name__ == "__main__":
    main()
