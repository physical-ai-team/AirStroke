"""tests/fixtures/landmarks/ 의 합성 랜드마크 fixture 생성.

    python tools/gen_synthetic_landmarks.py

실제 손 녹화(record_landmarks.py)가 생기기 전까지 gesture 개발·테스트용으로 쓴다.
MediaPipe 21점 순서(0 손목, 1-4 엄지, 5-8 검지, 9-12 중지, 13-16 약지, 17-20 소지)를 따르며
"펴진 손가락은 손목~끝마디 거리가 손목~PIP 거리보다 크다" 는 규칙을 만족하도록 만든다.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from airstroke_shared import SCHEMA_VERSION

OUT_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "landmarks"
FPS = 15
SIZE = 0.2  # 화면 대비 손 크기

# 손목 기준 MCP(엄지는 CMC) 위치 (손 크기 단위, y는 위쪽이 음수)
BASES = {
    "thumb": (-0.25, -0.15),
    "index": (-0.15, -0.55),
    "middle": (0.0, -0.58),
    "ring": (0.12, -0.55),
    "pinky": (0.22, -0.48),
}
FINGERS = ["thumb", "index", "middle", "ring", "pinky"]
POSES = {  # 펴진 손가락 집합
    "index": {"index"},
    "index_middle": {"index", "middle"},
    "fist": set(),
    "palm": {"thumb", "index", "middle", "ring", "pinky"},
}


def finger_points(name: str, extended: bool) -> list[tuple[float, float]]:
    bx, by = BASES[name]
    if name == "thumb":
        steps = [(-0.15, -0.10), (-0.12, -0.08), (-0.10, -0.06)] if extended else \
                [(-0.02, -0.12), (0.10, -0.06), (0.10, 0.04)]  # fmt: skip
    else:
        k = 0.75 if name == "pinky" else 1.0
        steps = [(0, -0.22 * k), (0, -0.16 * k), (0, -0.13 * k)] if extended else \
                [(0, -0.12), (0.01, 0.10), (0.0, 0.10)]  # fmt: skip
    pts, x, y = [(bx, by)], bx, by
    for dx, dy in steps:
        x, y = x + dx, y + dy
        pts.append((x, y))
    return pts


def hand_points(pose: str, wrist: tuple[float, float], rng: random.Random) -> list[list[float]]:
    rel = [(0.0, 0.0)]
    for f in FINGERS:
        rel += finger_points(f, f in POSES[pose])
    pts = []
    for i, (dx, dy) in enumerate(rel):
        jitter = lambda: rng.uniform(-0.003, 0.003)  # noqa: E731
        z = 0.0 if i == 0 else -0.02 * (i % 4 + 1) / 4
        pts.append([
            round(wrist[0] + dx * SIZE + jitter(), 5),
            round(wrist[1] + dy * SIZE + jitter(), 5),
            round(z, 5),
        ])  # fmt: skip
    return pts


def index_tip_offset() -> tuple[float, float]:
    """검지 끝(8번)이 손목 대비 얼마나 떨어져 있는지 — 궤적을 검지 끝 기준으로 그리기 위함."""
    x, y = finger_points("index", True)[-1]
    return x * SIZE, y * SIZE


def build(segments: list[tuple[str | None, float, callable]], seed: int) -> list[dict]:
    """segments: (pose 또는 None=손 없음, 초, t→검지 끝 좌표 함수)"""
    rng = random.Random(seed)
    ox, oy = index_tip_offset()
    msgs, ts, seq = [], 1_700_000_000_000.0, 0
    for pose, seconds, path in segments:
        n = round(seconds * FPS)
        for i in range(n):
            hands = []
            if pose is not None:
                tx, ty = path(i / max(1, n - 1))
                hands.append({
                    "handedness": "Right",
                    "score": 0.98,
                    "points": hand_points(pose, (tx - ox, ty - oy), rng),
                })  # fmt: skip
            msgs.append({"ts": ts, "seq": seq, "mirror": True, "hands": hands, "trace": {}})
            ts += 1000.0 / FPS
            seq += 1
    return msgs


def still(x: float, y: float):
    return lambda t: (x, y)


def circle(cx, cy, r):
    return lambda t: (cx + r * math.cos(2 * math.pi * t), cy + r * math.sin(2 * math.pi * t))


def line(x0, y0, x1, y1):
    return lambda t: (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)


def write(name: str, msgs: list[dict], description: str) -> None:
    data = {
        "meta": {
            "description": description,
            "fps": FPS,
            "count": len(msgs),
            "schema_version": SCHEMA_VERSION,
            "synthetic": True,
        },
        "messages": msgs,
    }
    path = OUT_DIR / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"{path.relative_to(OUT_DIR.parents[2])}: {len(msgs)} 프레임")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for i, pose in enumerate(POSES):
        write(f"gesture_{pose}.json", build([(pose, 2.0, still(0.5, 0.45))], seed=i),
              f"합성: '{pose}' 손 모양 정지 2초")  # fmt: skip
    write(
        "scenario_draw.json",
        build(
            [
                ("fist", 1.0, still(0.5, 0.5)),
                ("index", 3.0, circle(0.5, 0.5, 0.12)),
                ("index_middle", 1.0, line(0.62, 0.5, 0.35, 0.65)),
                ("index", 2.0, line(0.35, 0.65, 0.65, 0.65)),
                ("palm", 1.0, line(0.65, 0.6, 0.35, 0.6)),
                (None, 1.0, still(0, 0)),
            ],
            seed=100,
        ),
        "합성 시나리오: 주먹 → 검지로 원 → 두 손가락 이동 → 검지로 직선 → 손바닥 → 손 없음",
    )


if __name__ == "__main__":
    main()
