"""tools/ 공용 도우미. 로컬 conda(airstroke) 환경에서 실행하며 레포 루트의 .env 를 읽는다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import redis

from airstroke_shared.settings import load_dotenv, redis_url

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
RECORDINGS = ROOT / "recordings"

load_dotenv(ROOT / ".env")


def redis_client() -> redis.Redis:
    r = redis.Redis.from_url(redis_url())
    try:
        r.ping()
    except redis.ConnectionError as exc:
        raise SystemExit(
            f"Redis 연결 실패 ({redis_url()}): {exc}\n"
            "→ docker compose up -d redis 로 Redis를 먼저 띄울 것"
        ) from exc
    return r


def add_session_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--session", default="dev", help="세션 ID (기본: dev)")


def load_recording(path: Path) -> dict:
    """녹화/fixture 파일: {"meta": {...}, "messages": [LandmarksMsg dict, ...]}"""
    return json.loads(Path(path).read_text(encoding="utf-8"))
