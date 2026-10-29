"""세션 생성·QR·설정 HTTP API. 세션은 Redis 키 session:{sid} = {"created": ms} (TTL)."""

from __future__ import annotations

import io
import json
import secrets
from urllib.parse import urlsplit

import redis.asyncio as aioredis
import segno
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from airstroke_shared import channels
from airstroke_shared.log import get_logger
from airstroke_shared.schemas import now_ms

from . import config

log = get_logger("gateway")
router = APIRouter()

LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}


def new_session_id() -> str:
    return secrets.token_urlsafe(6)  # URL·채널 이름에 안전한 8자


def mobile_url(scheme: str, host_header: str, public_host: str, sid: str) -> str:
    """폰이 열 주소. PC가 localhost로 접속했으면 hostname만 PUBLIC_HOST로 바꾼다.

    포트는 요청 Host의 포트를 그대로 쓴다(컨테이너 안에서는 호스트 쪽 포트를 알 수 없음).
    """
    parts = urlsplit(f"//{host_header}")
    netloc = host_header
    if parts.hostname in LOCAL_HOSTNAMES:
        if public_host:
            netloc = f"{public_host}:{parts.port}" if parts.port else public_host
        else:
            log.warning("public_host_missing", extra={"hint": "tools/gen_cert.py 실행 필요"})
    return f"{scheme}://{netloc}/mobile/?s={sid}"


def _mobile_url_for(request: Request, sid: str) -> str:
    host = request.headers.get("host") or f"localhost:{config.PORT}"
    return mobile_url(request.url.scheme, host, config.PUBLIC_HOST, sid)


async def session_exists(r: aioredis.Redis, sid: str) -> bool:
    return bool(await r.exists(channels.session_key(sid)))


@router.post("/api/sessions")
async def create_session(request: Request):
    r: aioredis.Redis = request.app.state.redis
    sid = new_session_id()
    info = {"created": now_ms()}
    await r.set(channels.session_key(sid), json.dumps(info), ex=config.SESSION_TTL_SEC)
    url = _mobile_url_for(request, sid)
    log.info("session_created", extra={"session": sid, "mobile_url": url})
    return {"session_id": sid, "mobile_url": url, "qr_url": f"/api/sessions/{sid}/qr.svg"}


@router.get("/api/sessions/{sid}/qr.svg")
async def session_qr(sid: str, request: Request):
    if not await session_exists(request.app.state.redis, sid):
        raise HTTPException(status_code=404, detail="unknown session")
    buf = io.BytesIO()
    segno.make(_mobile_url_for(request, sid), error="m").save(buf, kind="svg", scale=8, border=2)
    return Response(buf.getvalue(), media_type="image/svg+xml")


@router.get("/api/config")
async def client_config():
    return {
        "camera": {
            "width": config.CAMERA_WIDTH,
            "height": config.CAMERA_HEIGHT,
            "fps": config.CAMERA_FPS,
            "jpeg_quality": config.JPEG_QUALITY,
        },
        "max_inflight_frames": config.MAX_INFLIGHT_FRAMES,
        "active_area": config.ACTIVE_AREA,
    }
