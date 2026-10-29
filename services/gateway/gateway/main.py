from __future__ import annotations

import json
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from airstroke_shared import channels
from airstroke_shared.log import get_logger
from airstroke_shared.settings import redis_url

from .config import WATCHED_SERVICES, WEB_DIR

log = get_logger("gateway")


def create_app(redis_client: aioredis.Redis | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.redis = redis_client or aioredis.Redis.from_url(redis_url())
        log.info("startup", extra={"redis_url": redis_url(), "web_dir": str(WEB_DIR)})
        yield
        await app.state.redis.aclose()

    app = FastAPI(title="AirStroke gateway", lifespan=lifespan)

    @app.get("/health")
    async def health():
        r: aioredis.Redis = app.state.redis
        try:
            await r.ping()
        except Exception as exc:  # noqa: BLE001
            log.warning("redis_unreachable", extra={"error": str(exc)})
            return JSONResponse({"status": "error", "redis": str(exc)}, status_code=503)

        services = {"gateway": {"alive": True}}
        for name in WATCHED_SERVICES:
            raw = await r.get(channels.heartbeat_key(name))
            services[name] = {"alive": raw is not None, "last": json.loads(raw) if raw else None}
        return {"status": "ok", "redis": "ok", "services": services}

    @app.get("/")
    async def index():
        return RedirectResponse("/canvas/")

    app.mount("/canvas", StaticFiles(directory=WEB_DIR / "canvas", html=True), name="canvas")
    app.mount("/mobile", StaticFiles(directory=WEB_DIR / "mobile", html=True), name="mobile")
    return app


app = create_app()
