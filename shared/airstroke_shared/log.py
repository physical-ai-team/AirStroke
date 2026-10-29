"""표준 출력 JSON 구조화 로그.

    log = get_logger("vision")
    log.info("frame_processed", extra={"session": sid, "infer_ms": 12.3})
→ {"ts": "...", "level": "INFO", "service": "vision", "logger": "vision",
   "event": "frame_processed", "session": "...", "infer_ms": 12.3}

핸들러는 root 로거에 한 번만 붙이므로 uvicorn 등 라이브러리 로그도 같은 JSON 형식으로 나간다.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from .settings import env_str

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                data[key] = value
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def get_logger(service: str) -> logging.Logger:
    root = logging.getLogger()
    if not any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter(service))
        root.handlers = [handler]
        root.setLevel(env_str("LOG_LEVEL", "INFO").upper())
    return logging.getLogger(service)
