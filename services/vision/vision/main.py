"""vision: frames:* 구독 → (3단계) MediaPipe HandLandmarker → landmarks:{sid} publish.

1단계에서는 구독·최신 프레임 슬롯·하트비트·통계 로그까지만 동작한다.
"""

from __future__ import annotations

import asyncio

import redis.asyncio as aioredis

from airstroke_shared import channels
from airstroke_shared.health import heartbeat
from airstroke_shared.log import get_logger
from airstroke_shared.schemas import FrameMsg
from airstroke_shared.settings import redis_url

from . import config
from .latest import LatestSlots

log = get_logger("vision")


async def subscribe(r: aioredis.Redis, slots: LatestSlots) -> None:
    pubsub = r.pubsub()
    await pubsub.psubscribe(channels.pattern(channels.FRAMES))
    log.info("subscribed", extra={"pattern": channels.pattern(channels.FRAMES)})
    async for msg in pubsub.listen():
        if msg["type"] == "pmessage":
            # 파싱은 worker에서 — 구독 루프는 소켓 버퍼를 비우는 일만 빠르게 한다
            slots.put(channels.session_of(msg["channel"]), msg["data"])


async def work(r: aioredis.Redis, slots: LatestSlots, stats: dict) -> None:
    while True:
        session_id, raw = await slots.get()
        try:
            frame = FrameMsg.model_validate_json(raw)
        except ValueError as exc:
            log.warning("bad_frame", extra={"session": session_id, "error": str(exc)})
            continue
        stats["processed"] += 1
        stats["last_seq"] = frame.seq
        # TODO(3단계): 세션별 HandLandmarker로 추론 후 landmarks:{session_id} 로 publish


async def report(slots: LatestSlots, stats: dict) -> None:
    prev = 0
    while True:
        await asyncio.sleep(config.STATS_INTERVAL_SEC)
        stats["fps"] = round((stats["processed"] - prev) / config.STATS_INTERVAL_SEC, 1)
        stats["dropped"] = slots.dropped
        prev = stats["processed"]
        log.info("stats", extra=stats)


async def main() -> None:
    r = aioredis.Redis.from_url(redis_url())
    await r.ping()
    log.info("startup", extra={"redis_url": redis_url(), "num_hands": config.NUM_HANDS})
    slots = LatestSlots()
    stats = {"processed": 0, "fps": 0.0, "dropped": 0, "last_seq": None}
    async with asyncio.TaskGroup() as tg:
        tg.create_task(heartbeat(r, "vision", stats))
        tg.create_task(subscribe(r, slots))
        tg.create_task(work(r, slots, stats))
        tg.create_task(report(slots, stats))
