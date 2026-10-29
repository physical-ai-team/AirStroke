"""gesture: landmarks:* 구독 → (4단계) 제스처 분류·디바운스·스무딩 → commands:{sid} publish.

1단계에서는 구독·스키마 검증·하트비트·통계 로그까지만 동작한다.
gesture는 디바운스 상태 때문에 프레임을 버리지 않고 순서대로 모두 처리한다.
"""

from __future__ import annotations

import asyncio

import redis.asyncio as aioredis

from airstroke_shared import channels
from airstroke_shared.health import heartbeat
from airstroke_shared.log import get_logger
from airstroke_shared.schemas import LandmarksMsg
from airstroke_shared.settings import redis_url

from . import config

log = get_logger("gesture")


async def consume(r: aioredis.Redis, stats: dict) -> None:
    pubsub = r.pubsub()
    await pubsub.psubscribe(channels.pattern(channels.LANDMARKS))
    log.info("subscribed", extra={"pattern": channels.pattern(channels.LANDMARKS)})
    async for msg in pubsub.listen():
        if msg["type"] != "pmessage":
            continue
        session_id = channels.session_of(msg["channel"])
        try:
            landmarks = LandmarksMsg.model_validate_json(msg["data"])
        except ValueError as exc:
            log.warning("bad_landmarks", extra={"session": session_id, "error": str(exc)})
            continue
        stats["processed"] += 1
        stats["last_seq"] = landmarks.seq
        # TODO(4단계): 세션별 상태(디바운스·One Euro)로 CommandMsg 생성 후 commands:{sid} publish


async def report(stats: dict) -> None:
    prev = 0
    while True:
        await asyncio.sleep(config.STATS_INTERVAL_SEC)
        stats["fps"] = round((stats["processed"] - prev) / config.STATS_INTERVAL_SEC, 1)
        prev = stats["processed"]
        log.info("stats", extra=stats)


async def main() -> None:
    r = aioredis.Redis.from_url(redis_url())
    await r.ping()
    log.info("startup", extra={"redis_url": redis_url(), "debounce": config.DEBOUNCE_FRAMES})
    stats = {"processed": 0, "fps": 0.0, "last_seq": None}
    async with asyncio.TaskGroup() as tg:
        tg.create_task(heartbeat(r, "gesture", stats))
        tg.create_task(consume(r, stats))
        tg.create_task(report(stats))
