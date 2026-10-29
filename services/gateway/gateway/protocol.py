"""브라우저 ↔ gateway WebSocket 메시지 (docs/03-protocol.md "브라우저 ↔ gateway 계약").

Redis 채널 메시지는 airstroke_shared.schemas, 여기는 WebSocket 위의 메시지만 다룬다.

바이너리 프레임 (폰 → gateway, gateway → PC PiP 공통):
    [4바이트 big-endian 헤더 길이 N][N바이트 UTF-8 JSON 헤더][JPEG 바이트]
"""

from __future__ import annotations

import json
import struct
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from airstroke_shared.schemas import FrameMsg, Trace

_LEN = struct.Struct(">I")
MAX_HEADER_BYTES = 64 * 1024
JPEG_MAGIC = b"\xff\xd8"


class _WsMsg(BaseModel):
    model_config = ConfigDict(extra="ignore")


# ---------- 클라이언트 → gateway ----------
class MobileFrameHeader(_WsMsg):
    seq: int
    capture_ts: float | None = None  # 폰 시계 ms
    mirror: bool = False


class Pong(_WsMsg):
    type: Literal["pong"]
    id: int
    t_server: float | None = None  # gateway는 자기가 기록한 값을 쓴다
    t_client: float


class Pip(_WsMsg):
    type: Literal["pip"]
    enabled: bool


ClientMsg = TypeAdapter(Annotated[Pong | Pip, Field(discriminator="type")])


def parse_client_text(text: str) -> Pong | Pip | None:
    """모르는 type이나 형식 오류는 None (호출 쪽에서 로그 후 무시)."""
    try:
        return ClientMsg.validate_json(text)
    except ValidationError:
        return None


# ---------- gateway → 클라이언트 ----------
class Ping(_WsMsg):
    type: Literal["ping"] = "ping"
    id: int
    t_server: float


class Clock(_WsMsg):
    type: Literal["clock"] = "clock"
    offset_ms: float
    rtt_ms: float


class Ack(_WsMsg):
    type: Literal["ack"] = "ack"
    seq: int


class Status(_WsMsg):
    type: Literal["status"] = "status"
    mobile_connected: bool


class PipFrameHeader(_WsMsg):
    """gateway → PC PiP 바이너리의 헤더. mirror=True면 PC가 좌우 반전해서 보여준다."""

    ts: float
    seq: int
    mirror: bool
    trace: Trace


def forward_text(kind: Literal["landmarks", "command"], data: BaseModel) -> str:
    """PC로 보낼 {"type": kind, "data": <메시지>} 텍스트."""
    return json.dumps({"type": kind, "data": data.model_dump(mode="json")}, ensure_ascii=False)


# ---------- 바이너리 프레이밍 ----------
def pack_frame(header: BaseModel, jpeg: bytes) -> bytes:
    raw = header.model_dump_json().encode("utf-8")
    return _LEN.pack(len(raw)) + raw + jpeg


def unpack_mobile_frame(data: bytes) -> tuple[MobileFrameHeader, bytes]:
    """형식이 틀리면 ValueError."""
    if len(data) < _LEN.size:
        raise ValueError("frame too short")
    (n,) = _LEN.unpack_from(data)
    if n > MAX_HEADER_BYTES or _LEN.size + n > len(data):
        raise ValueError(f"bad header length {n}")
    try:
        header = MobileFrameHeader.model_validate_json(data[_LEN.size : _LEN.size + n])
    except ValidationError as exc:
        raise ValueError(f"bad header: {exc.errors()[0]['msg']}") from exc
    jpeg = data[_LEN.size + n :]
    if not jpeg.startswith(JPEG_MAGIC):
        raise ValueError("payload is not JPEG")
    return header, jpeg


def jpeg_size(jpeg: bytes) -> tuple[int, int] | None:
    """SOF 마커에서 (width, height)만 읽는다 (디코드 없음). 못 찾으면 None."""
    i = 2
    while i + 9 <= len(jpeg):
        if jpeg[i] != 0xFF:
            return None
        marker = jpeg[i + 1]
        if marker == 0xFF:  # 채움 바이트
            i += 1
            continue
        # SOF0~SOF15 (DHT·JPG·DAC 제외)
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack_from(">HH", jpeg, i + 5)
            return (width, height) if width and height else None
        i += 2 + int.from_bytes(jpeg[i + 2 : i + 4], "big")
    return None


def pip_frame(msg: FrameMsg, jpeg: bytes) -> bytes:
    header = PipFrameHeader(ts=msg.ts, seq=msg.seq, mirror=msg.mirror, trace=msg.trace)
    return pack_frame(header, jpeg)
