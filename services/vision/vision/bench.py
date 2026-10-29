"""CPU 튜닝용 벤치마크: 추론 해상도(max_width)·NUM_HANDS 조합별 디코드/추론 시간과 검출률.

손 사진(또는 영상 파일)을 폰 프레임처럼 CAMERA_WIDTH×HEIGHT, JPEG_QUALITY 로 만들어
VIDEO 모드로 연속 추론한다. 손 없는 검은 화면도 함께 잰다(매 프레임 손 검출이 돌아 최악의 경우).
Redis 는 필요 없다. services/vision 에서:
    python -m vision.bench hand1.jpg hand2.jpg
    python -m vision.bench clip.mp4 --widths 640 480 320 --hands 1 2 --frames 90
컨테이너(시연 환경에 가까움, CPU 2개 제한 예):
    docker run --rm --cpus=2 -v <사진폴더>:/data airstroke-vision python -m vision.bench /data/a.jpg
결과는 JSON 로그 한 줄씩(event=bench_result)으로 나온다.
"""

from __future__ import annotations

import argparse
import base64
from pathlib import Path

import cv2
import numpy as np

from airstroke_shared.log import get_logger
from airstroke_shared.settings import env_int

from .infer import process
from .landmarker import create_landmarker
from .timing import LatencyWindow

log = get_logger("vision")


def letterbox(img: np.ndarray, width: int, height: int) -> np.ndarray:
    """비율을 유지해 width×height 캔버스 가운데에 놓는다."""
    scale = min(width / img.shape[1], height / img.shape[0])
    resized = cv2.resize(img, (round(img.shape[1] * scale), round(img.shape[0] * scale)))
    out = np.zeros((height, width, 3), np.uint8)
    y = (height - resized.shape[0]) // 2
    x = (width - resized.shape[1]) // 2
    out[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return out


def load_frames(path: Path, width: int, height: int, limit: int) -> list[np.ndarray]:
    if path.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp"):
        img = cv2.imread(str(path))
        if img is None:
            raise SystemExit(f"cannot read image: {path}")
        return [letterbox(img, width, height)]
    cap = cv2.VideoCapture(str(path))
    frames = []
    while len(frames) < limit:
        ok, img = cap.read()
        if not ok:
            break
        frames.append(letterbox(img, width, height))
    cap.release()
    if not frames:
        raise SystemExit(f"cannot read video: {path}")
    return frames


def encode(img: np.ndarray, quality: int) -> str:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    assert ok
    return base64.b64encode(buf.tobytes()).decode()


def run_case(frames_b64: list[str], max_width: int | None, num_hands: int, n: int, warmup: int):
    landmarker = create_landmarker(num_hands)
    decode, infer, detected = LatencyWindow(), LatencyWindow(), 0
    try:
        for i in range(warmup + n):
            out = process(landmarker, frames_b64[i % len(frames_b64)], 1000 + i * 66, max_width)
            if i < warmup:
                continue
            decode.add(out.decode_ms)
            infer.add(out.infer_ms)
            detected += bool(out.hands)
    finally:
        landmarker.close()
    return decode.flush(), infer.flush(), detected / n


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="손 사진 또는 영상 파일")
    parser.add_argument("--widths", nargs="+", type=int, default=[640, 480, 320, 256])
    parser.add_argument("--hands", nargs="+", type=int, default=[1, 2])
    parser.add_argument("--frames", type=int, default=60, help="측정 프레임 수 (워밍업 제외)")
    parser.add_argument("--warmup", type=int, default=5)
    args = parser.parse_args()

    cam_w, cam_h = env_int("CAMERA_WIDTH", 640), env_int("CAMERA_HEIGHT", 480)
    quality = env_int("JPEG_QUALITY", 70)
    sources = {p.name: load_frames(p, cam_w, cam_h, args.frames) for p in args.inputs}
    sources["(no hand)"] = [np.zeros((cam_h, cam_w, 3), np.uint8)]

    for name, frames in sources.items():
        encoded = [encode(f, quality) for f in frames]
        for num_hands in args.hands:
            for width in args.widths:
                max_width = None if width >= cam_w else width
                (dec_avg, dec_p95), (inf_avg, inf_p95), rate = run_case(
                    encoded, max_width, num_hands, args.frames, args.warmup
                )
                log.info(
                    "bench_result",
                    extra={
                        "input": name,
                        "camera": f"{cam_w}x{cam_h}",
                        "infer_width": min(width, cam_w),
                        "num_hands": num_hands,
                        "decode_ms_avg": dec_avg,
                        "decode_ms_p95": dec_p95,
                        "infer_ms_avg": inf_avg,
                        "infer_ms_p95": inf_p95,
                        "total_ms_avg": round(dec_avg + inf_avg, 1),
                        "detect_rate": round(rate, 2),
                    },
                )


if __name__ == "__main__":
    main()
