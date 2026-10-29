"""Redis 하트비트 기반 헬스체크.

HTTP 서버가 없는 서비스(vision, gesture)는 메인 루프에서 heartbeat()를 돌리고,
Docker healthcheck는 `python -m airstroke_shared.health <service>` 로 키 존재를 확인한다.
키가 있다 = Redis 연결 정상 + 루프가 살아 있음.
"""

from __future__ import annotations

import asyncio
import json
import sys

import redis
import redis.asyncio as aioredis

from . import channels
from .schemas import now_ms
from .settings import env_float, redis_url


async def heartbeat(r: aioredis.Redis, service: str, stats: dict | None = None) -> None:
    interval = env_float("HEARTBEAT_INTERVAL_SEC", 5.0)
    ttl = max(int(interval * 3), 3)
    while True:
        payload = {"ts": now_ms(), **(stats or {})}
        await r.set(channels.heartbeat_key(service), json.dumps(payload), ex=ttl)
        await asyncio.sleep(interval)


def check(service: str) -> bool:
    r = redis.Redis.from_url(redis_url(), socket_timeout=3)
    return r.exists(channels.heartbeat_key(service)) == 1


if __name__ == "__main__":
    try:
        ok = check(sys.argv[1])
    except Exception as exc:  # noqa: BLE001 — 헬스체크는 어떤 실패든 unhealthy
        print(f"unhealthy: {exc}")
        sys.exit(1)
    sys.exit(0 if ok else 1)
