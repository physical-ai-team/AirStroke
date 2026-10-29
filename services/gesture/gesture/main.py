"""gesture: landmarks:* 구독 → 제스처 분류·디바운스·스무딩 → commands:{sid} publish.

    cd services/gesture ; python -m gesture

gesture는 디바운스 상태 때문에 프레임을 버리지 않고 순서대로 모두 처리한다.
판별 로직은 gesture/core/에 있고, 여기서는 세션별 상태 관리와 Redis 입출력만 한다.
"""

from __future__ import annotations

import asyncio

import redis.asyncio as aioredis

from airstroke_shared import channels
from airstroke_shared.health import heartbeat
from airstroke_shared.log import get_logger
from airstroke_shared.schemas import CommandMsg, LandmarksMsg
from airstroke_shared.settings import redis_url

from . import config
from .core import GestureParams, GestureSession

log = get_logger("gesture")


def load_params() -> GestureParams:
    return GestureParams(
        debounce_frames=config.DEBOUNCE_FRAMES,
        undo_debounce_frames=config.UNDO_DEBOUNCE_FRAMES,
        pinch_distance_ratio=config.PINCH_DISTANCE_RATIO,
        active_area=config.ACTIVE_AREA,
        one_euro_min_cutoff=config.ONE_EURO_MIN_CUTOFF,
        one_euro_beta=config.ONE_EURO_BETA,
        one_euro_d_cutoff=config.ONE_EURO_D_CUTOFF,
        canvas_aspect=config.CANVAS_ASPECT,
    )


class SessionRouter:
    """세션별 GestureSession을 두고 메시지를 해당 세션으로 보낸다."""

    def __init__(self, params: GestureParams) -> None:
        self.params = params
        self.sessions: dict[str, GestureSession] = {}

    def handle(self, session_id: str, landmarks: LandmarksMsg) -> CommandMsg:
        session = self.sessions.get(session_id)
        if session is None:
            session = self.sessions[session_id] = GestureSession(self.params)
            log.info("session_started", extra={"session": session_id})
        return session.process(landmarks)


async def consume(r: aioredis.Redis, router: SessionRouter, stats: dict) -> None:
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
        command = router.handle(session_id, landmarks)
        # 순서를 지키기 위해 publish가 끝난 뒤 다음 메시지를 처리한다
        await r.publish(channels.commands(session_id), command.model_dump_json())
        stats["processed"] += 1
        stats["last_seq"] = landmarks.seq
        stats["sessions"] = len(router.sessions)


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
    params = load_params()
    log.info("startup", extra={"redis_url": redis_url(), **params.__dict__})
    router = SessionRouter(params)
    stats = {"processed": 0, "fps": 0.0, "last_seq": None, "sessions": 0}
    async with asyncio.TaskGroup() as tg:
        tg.create_task(heartbeat(r, "gesture", stats))
        tg.create_task(consume(r, router, stats))
        tg.create_task(report(stats))
