"""vision: frames:* 구독 → MediaPipe HandLandmarker → landmarks:{sid} publish.

세션마다 최신 프레임 하나만 처리하고(latest.py), 디코드·추론은 스레드에서 돌려 구독 루프가
멈추지 않게 한다. 세션별 HandLandmarker 는 첫 프레임에서 만들고 VISION_SESSION_IDLE_SEC 동안
프레임이 없으면 닫는다. stats 로그의 *_ms 값(평균/p95)이 CPU 튜닝의 근거다.
실행: services/vision 에서 python vision/model.py (최초 1회, 모델 받기) 후 python -m vision
"""

from __future__ import annotations

import asyncio

import redis.asyncio as aioredis

from airstroke_shared import channels
from airstroke_shared.health import heartbeat
from airstroke_shared.log import get_logger
from airstroke_shared.schemas import FrameMsg, LandmarksMsg, now_ms
from airstroke_shared.settings import redis_url

from . import config
from .infer import process
from .landmarker import SessionLandmarkers, create_landmarker
from .latest import LatestSlots
from .model import MODEL_PATH, is_ready
from .timing import LatencyWindow

log = get_logger("vision")


async def subscribe(r: aioredis.Redis, slots: LatestSlots) -> None:
    pubsub = r.pubsub()
    await pubsub.psubscribe(channels.pattern(channels.FRAMES))
    log.info("subscribed", extra={"pattern": channels.pattern(channels.FRAMES)})
    async for msg in pubsub.listen():
        if msg["type"] == "pmessage":
            # 파싱은 worker에서 — 구독 루프는 소켓 버퍼를 비우는 일만 빠르게 한다
            slots.put(channels.session_of(msg["channel"]), msg["data"])


def reap_idle(sessions: SessionLandmarkers, stats: dict) -> None:
    for session_id in sessions.reap():
        log.info("session_closed", extra={"session": session_id, "reason": "idle"})
    stats["sessions"] = len(sessions)


async def work(
    r: aioredis.Redis,
    slots: LatestSlots,
    sessions: SessionLandmarkers,
    stats: dict,
    timings: dict[str, LatencyWindow],
) -> None:
    # 프레임이 끊겨도 유휴 세션을 닫을 수 있게 get()을 주기적으로 깨운다.
    # 해제는 이 루프에서만 해서 추론 중인 인스턴스를 닫지 않는다.
    reap_every = config.SESSION_IDLE_SEC / 2
    while True:
        try:
            session_id, raw = await asyncio.wait_for(slots.get(), timeout=reap_every)
        except TimeoutError:
            reap_idle(sessions, stats)
            continue
        try:
            frame = FrameMsg.model_validate_json(raw)
        except ValueError as exc:
            log.warning("bad_frame", extra={"session": session_id, "error": str(exc)})
            continue
        # 새 세션이면 모델 로드(~2초)가 일어나므로 이것도 스레드에서. 이 루프만 sessions 를 만진다.
        landmarker, ts_ms, created = await asyncio.to_thread(sessions.acquire, session_id, frame.ts)
        if created:
            log.info("session_opened", extra={"session": session_id, "sessions": len(sessions)})
        try:
            out = await asyncio.to_thread(process, landmarker, frame.jpeg_base64, ts_ms)
        except Exception:
            log.exception("infer_failed", extra={"session": session_id, "seq": frame.seq})
            continue
        if out is None:
            log.warning("bad_jpeg", extra={"session": session_id, "seq": frame.seq})
            continue
        done = now_ms()
        msg = LandmarksMsg(
            ts=frame.ts,
            seq=frame.seq,
            mirror=frame.mirror,
            width=frame.width,
            height=frame.height,
            hands=out.hands,
            trace=frame.trace.model_copy(update={"vision_done": done}),
        )
        await r.publish(channels.landmarks(session_id), msg.model_dump_json())
        stats["processed"] += 1
        stats["last_seq"] = frame.seq
        timings["decode_ms"].add(out.decode_ms)
        timings["infer_ms"].add(out.infer_ms)
        if frame.trace.gw_recv is not None:
            # gateway 수신 → vision 완료: 큐 대기 + 디코드 + 추론
            timings["lag_ms"].add(done - frame.trace.gw_recv)
        reap_idle(sessions, stats)


async def report(slots: LatestSlots, stats: dict, timings: dict[str, LatencyWindow]) -> None:
    prev = 0
    while True:
        await asyncio.sleep(config.STATS_INTERVAL_SEC)
        stats["fps"] = round((stats["processed"] - prev) / config.STATS_INTERVAL_SEC, 1)
        stats["dropped"] = slots.dropped
        for name, window in timings.items():
            stats[f"{name}_avg"], stats[f"{name}_p95"] = window.flush()
        prev = stats["processed"]
        log.info("stats", extra=stats)


async def main() -> None:
    r = aioredis.Redis.from_url(redis_url())
    await r.ping()
    if not is_ready():
        raise SystemExit(f"model missing or corrupt: {MODEL_PATH} (run: python vision/model.py)")
    log.info("startup", extra={"redis_url": redis_url(), "num_hands": config.NUM_HANDS})
    slots = LatestSlots()
    sessions = SessionLandmarkers(create_landmarker, config.SESSION_IDLE_SEC)
    stats = {"processed": 0, "fps": 0.0, "dropped": 0, "sessions": 0, "last_seq": None}
    timings = {name: LatencyWindow() for name in ("decode_ms", "infer_ms", "lag_ms")}
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(heartbeat(r, "vision", stats))
            tg.create_task(subscribe(r, slots))
            tg.create_task(work(r, slots, sessions, stats, timings))
            tg.create_task(report(slots, stats, timings))
    finally:
        sessions.close_all()
