"""환경변수(.env) 읽기 도우미. 기본값은 .env.example 과 같게 유지한다."""

from __future__ import annotations

import os
from pathlib import Path


def env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def env_int(name: str, default: int) -> int:
    return int(env_str(name, str(default)))


def env_float(name: str, default: float) -> float:
    return float(env_str(name, str(default)))


def env_bool(name: str, default: bool) -> bool:
    return env_str(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def redis_url() -> str:
    return env_str("REDIS_URL", "redis://localhost:6379/0")


def load_dotenv(path: str | Path = ".env") -> None:
    """로컬 도구용 최소 .env 로더. 이미 설정된 환경변수는 덮어쓰지 않는다."""
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())
