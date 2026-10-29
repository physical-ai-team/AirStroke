"""폰·PC WebSocket.

- /ws/mobile/{sid}: 바이너리 프레임 → FrameMsg → frames:{sid} publish → ack
- /ws/pc/{sid}: landmarks·commands 전달, status(mobile_connected), PiP가 켜진 동안만 frames 전달
- 둘 다 접속 직후부터 CLOCK_PING_INTERVAL_SEC마다 ping → pong으로 시계 차이 추정 → clock

close 코드: 4404 모르는(만료된) 세션, 4409 같은 세션에 새 폰이 접속해 밀려남.
연결 상태는 이 프로세스 메모리에만 둔다(gateway는 1개).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import time
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError
from redis.asyncio.client import PubSub

from airstroke_shared import channels
from airstroke_shared.log import get_logger
from airstroke_shared.schemas import CommandMsg, FrameMsg, LandmarksMsg, Trace, now_ms

from . import config
from .clock import ClockEstimator
from .protocol import (
    Ack,
    Clock,
    Ping,
    Pip,
    Pong,
    Status,
    forward_text,
    jpeg_size,
    parse_client_text,
    pip_frame,
    unpack_mobile_frame,
)
from .sessions import session_exists

log = get_logger("gateway")
router = APIRouter()

CLOSE_UNKNOWN_SESSION = 4404
CLOSE_REPLACED = 4409


class Peer:
    """WebSocket 하나. 여러 태스크가 보내므로 송신을 lock으로 직렬화한다."""

    def __init__(self, ws: WebSocket, sid: str, role: str) -> None:
        self.ws = ws
        self.sid = sid
        self.role = role
        self.clock = ClockEstimator(config.CLOCK_SAMPLES)
        self._lock = asyncio.Lock()

    async def send_text(self, text: str) -> None:
        async with self._lock:
            await self.ws.send_text(text)

    async def send_msg(self, msg: BaseModel) -> None:
        await self.send_text(msg.model_dump_json())

    async def send_bytes(self, data: bytes) -> None:
        async with self._lock:
            await self.ws.send_bytes(data)

    async def close(self, code: int) -> None:
        async with self._lock:
            with contextlib.suppress(Exception):
                await self.ws.close(code)

    async def on_pong(self, pong: Pong) -> None:
        best = self.clock.on_pong(pong.id, pong.t_client, now_ms())
        if best is not None:
            await self.send_msg(Clock(offset_ms=best.offset_ms, rtt_ms=best.rtt_ms))


class Hub:
    """세션별 연결 목록 (폰 1개, PC 여러 개)."""

    def __init__(self) -> None:
        self.mobiles: dict[str, Peer] = {}
        self.pcs: dict[str, set[Peer]] = {}

    def set_mobile(self, peer: Peer) -> Peer | None:
        old = self.mobiles.get(peer.sid)
        self.mobiles[peer.sid] = peer
        return old

    def remove_mobile(self, peer: Peer) -> bool:
        """지금 등록된 폰이 이 peer일 때만 지우고 True (밀려난 폰은 False)."""
        if self.mobiles.get(peer.sid) is peer:
            del self.mobiles[peer.sid]
            return True
        return False

    def status(self, sid: str) -> Status:
        return Status(mobile_connected=sid in self.mobiles)

    async def broadcast_status(self, sid: str) -> None:
        text = self.status(sid).model_dump_json()
        for pc in list(self.pcs.get(sid, ())):
            with contextlib.suppress(Exception):
                await pc.send_text(text)


def _hub(ws: WebSocket) -> Hub:
    return ws.app.state.hub


async def _accept(ws: WebSocket, sid: str) -> bool:
    """수락한 뒤 세션을 확인한다(수락 전에 닫으면 close 코드가 브라우저에 전달되지 않음)."""
    await ws.accept()
    if await session_exists(ws.app.state.redis, sid):
        return True
    log.info("ws_unknown_session", extra={"session": sid, "path": ws.url.path})
    await ws.close(CLOSE_UNKNOWN_SESSION)
    return False


async def _ping_loop(peer: Peer, r: aioredis.Redis) -> None:
    """ping을 보내고, 연결이 살아 있는 동안 세션 TTL을 연장한다."""
    while True:
        now = now_ms()
        await peer.send_msg(Ping(id=peer.clock.new_ping(now), t_server=now))
        await r.expire(channels.session_key(peer.sid), config.SESSION_TTL_SEC)
        await asyncio.sleep(config.CLOCK_PING_INTERVAL_SEC)


async def _receive_loop(
    peer: Peer,
    on_bytes: Callable[[bytes], Awaitable[None]] | None,
    on_text: Callable[[Pong | Pip], Awaitable[None]],
) -> None:
    while True:
        try:
            msg = await peer.ws.receive()
        except (WebSocketDisconnect, RuntimeError):
            return
        if msg["type"] == "websocket.disconnect":
            return
        if msg.get("bytes") is not None and on_bytes is not None:
            await on_bytes(msg["bytes"])
        elif msg.get("text") is not None:
            parsed = parse_client_text(msg["text"])
            if parsed is None:
                log.debug("ws_text_ignored", extra={"session": peer.sid, "role": peer.role})
            else:
                await on_text(parsed)


async def _cancel(*tasks: asyncio.Task | None) -> None:
    live = [t for t in tasks if t is not None]
    for t in live:
        t.cancel()
    if not live:
        return
    # gather는 기다리는 쪽이 취소되면 하위 작업의 CancelledError를 대신 올려서, anyio cancel
    # scope(테스트 클라이언트 등)가 자기 취소로 알아보지 못하고 밖으로 샌다. wait는 그대로 둔다.
    await asyncio.wait(live)
    for t in live:
        if not t.cancelled():
            t.exception()  # 예외를 꺼내 'never retrieved' 경고를 막는다


_cleanups: set[asyncio.Task] = set()  # 실행 중인 정리 작업 (GC로 사라지지 않게 참조 유지)


async def _run_cleanup(coro: Coroutine[Any, Any, None]) -> None:
    """연결 정리를 끝까지 돌린다. 핸들러가 취소돼도(서버 종료, 테스트 클라이언트가 닫자마자
    취소) 정리는 따로 마저 실행된다. 그냥 await하면 첫 await에서 끊겨 폰 목록·PC 상태 알림·
    Redis 구독 해제가 빠진다."""
    task = asyncio.ensure_future(coro)
    _cleanups.add(task)
    task.add_done_callback(_cleanups.discard)
    await asyncio.shield(task)


async def _close_pubsub(pubsub: PubSub) -> None:
    with contextlib.suppress(Exception):  # Redis가 끊긴 경우에도 정리는 계속
        await pubsub.unsubscribe()
    await pubsub.aclose()


# ---------------------------------------------------------------- 폰
class _MobileStats:
    def __init__(self) -> None:
        self.frames = self.bad = self.bytes = 0
        self.total = 0
        self.t0 = time.monotonic()

    def maybe_report(self, sid: str) -> None:
        elapsed = time.monotonic() - self.t0
        if elapsed < config.STATS_INTERVAL_SEC:
            return
        log.info(
            "mobile_stats",
            extra={
                "session": sid,
                "fps": round(self.frames / elapsed, 1),
                "kb_per_frame": round(self.bytes / max(1, self.frames) / 1024, 1),
                "bad_frames": self.bad,
            },
        )
        self.frames = self.bad = self.bytes = 0
        self.t0 = time.monotonic()


@router.websocket("/ws/mobile/{sid}")
async def ws_mobile(ws: WebSocket, sid: str) -> None:
    if not await _accept(ws, sid):
        return
    r: aioredis.Redis = ws.app.state.redis
    hub = _hub(ws)
    peer = Peer(ws, sid, "mobile")
    old = hub.set_mobile(peer)
    if old is not None:
        log.info("mobile_replaced", extra={"session": sid})
        await old.close(CLOSE_REPLACED)
    log.info("mobile_connected", extra={"session": sid})
    await hub.broadcast_status(sid)

    stats = _MobileStats()
    channel = channels.frames(sid)

    async def on_frame(data: bytes) -> None:
        gw_recv = now_ms()
        try:
            header, jpeg = unpack_mobile_frame(data)
        except ValueError as exc:
            stats.bad += 1
            log.warning("bad_frame", extra={"session": sid, "error": str(exc)})
            return
        capture = (
            None if header.capture_ts is None else peer.clock.to_server_time(header.capture_ts)
        )
        width, height = jpeg_size(jpeg) or (None, None)
        msg = FrameMsg(
            ts=gw_recv,
            seq=header.seq,
            jpeg_base64=base64.b64encode(jpeg).decode("ascii"),
            mirror=header.mirror,
            width=width,
            height=height,
            trace=Trace(capture=capture, gw_recv=gw_recv),
        )
        await r.publish(channel, msg.model_dump_json())
        await peer.send_msg(Ack(seq=header.seq))
        stats.frames += 1
        stats.total += 1
        stats.bytes += len(jpeg)
        stats.maybe_report(sid)

    async def on_text(msg: Pong | Pip) -> None:
        if isinstance(msg, Pong):
            await peer.on_pong(msg)

    async def cleanup() -> None:
        await _cancel(ping_task)
        if hub.remove_mobile(peer):
            await hub.broadcast_status(sid)
        log.info("mobile_disconnected", extra={"session": sid, "frames": stats.total})

    ping_task = asyncio.create_task(_ping_loop(peer, r))
    try:
        await _receive_loop(peer, on_frame, on_text)
    finally:
        await _run_cleanup(cleanup())


# ---------------------------------------------------------------- PC
async def _forward_results(peer: Peer, pubsub: PubSub) -> None:
    """landmarks·commands → PC 텍스트. 스키마에 맞지 않는 메시지는 경고 후 버린다."""
    async for m in pubsub.listen():
        if m["type"] != "message":
            continue
        channel = m["channel"].decode() if isinstance(m["channel"], bytes) else m["channel"]
        try:
            if channel.startswith(channels.LANDMARKS + ":"):
                text = forward_text("landmarks", LandmarksMsg.model_validate_json(m["data"]))
            else:
                text = forward_text("command", CommandMsg.model_validate_json(m["data"]))
        except ValidationError as exc:
            log.warning("bad_message", extra={"channel": channel, "error": str(exc)[:200]})
            continue
        await peer.send_text(text)


async def _forward_pip(peer: Peer, pubsub: PubSub) -> None:
    async for m in pubsub.listen():
        if m["type"] != "message":
            continue
        try:
            msg = FrameMsg.model_validate_json(m["data"])
            jpeg = base64.b64decode(msg.jpeg_base64)
        except (ValidationError, ValueError) as exc:
            log.warning("bad_message", extra={"channel": "frames", "error": str(exc)[:200]})
            continue
        await peer.send_bytes(pip_frame(msg, jpeg))


@router.websocket("/ws/pc/{sid}")
async def ws_pc(ws: WebSocket, sid: str) -> None:
    if not await _accept(ws, sid):
        return
    r: aioredis.Redis = ws.app.state.redis
    hub = _hub(ws)
    peer = Peer(ws, sid, "pc")

    results = r.pubsub()
    await results.subscribe(channels.landmarks(sid), channels.commands(sid))
    hub.pcs.setdefault(sid, set()).add(peer)
    await peer.send_msg(hub.status(sid))
    log.info("pc_connected", extra={"session": sid})

    # PiP: 켜질 때 frames 전용 pubsub을 만들고, 꺼지면 구독째 없앤다 (꺼진 동안 영상 미전송)
    pip: tuple[PubSub, asyncio.Task] | None = None

    async def stop_pip() -> None:
        nonlocal pip
        if pip is not None:
            pubsub, task = pip
            pip = None
            await _cancel(task)
            await _close_pubsub(pubsub)

    async def on_text(msg: Pong | Pip) -> None:
        nonlocal pip
        if isinstance(msg, Pong):
            await peer.on_pong(msg)
        elif msg.enabled and pip is None:
            pubsub = r.pubsub()
            await pubsub.subscribe(channels.frames(sid))
            pip = (pubsub, asyncio.create_task(_forward_pip(peer, pubsub)))
            log.info("pip_on", extra={"session": sid})
        elif not msg.enabled and pip is not None:
            await stop_pip()
            log.info("pip_off", extra={"session": sid})

    tasks = (
        asyncio.create_task(_forward_results(peer, results)),
        asyncio.create_task(_ping_loop(peer, r)),
    )

    async def cleanup() -> None:
        hub.pcs.get(sid, set()).discard(peer)
        if not hub.pcs.get(sid):
            hub.pcs.pop(sid, None)
        await _cancel(*tasks)
        await stop_pip()
        await _close_pubsub(results)
        log.info("pc_disconnected", extra={"session": sid})

    try:
        await _receive_loop(peer, None, on_text)
    finally:
        await _run_cleanup(cleanup())
