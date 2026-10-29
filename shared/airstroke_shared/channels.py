"""Redis 채널·키 이름. 문자열을 직접 조립하지 말고 이 함수들을 쓸 것."""

FRAMES = "frames"
LANDMARKS = "landmarks"
COMMANDS = "commands"


def frames(session_id: str) -> str:
    return f"{FRAMES}:{session_id}"


def landmarks(session_id: str) -> str:
    return f"{LANDMARKS}:{session_id}"


def commands(session_id: str) -> str:
    return f"{COMMANDS}:{session_id}"


def pattern(prefix: str) -> str:
    """PSUBSCRIBE용 패턴. 예: pattern(FRAMES) == 'frames:*'"""
    return f"{prefix}:*"


def session_of(channel: str | bytes) -> str:
    if isinstance(channel, bytes):
        channel = channel.decode()
    return channel.split(":", 1)[1]


def session_key(session_id: str) -> str:
    return f"session:{session_id}"


def heartbeat_key(service: str) -> str:
    return f"health:{service}"
