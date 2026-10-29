import struct

import pytest

from gateway.protocol import MobileFrameHeader, Pip, Pong, pack_frame, parse_client_text
from gateway.protocol import unpack_mobile_frame as unpack

JPEG = b"\xff\xd8fake-jpeg\xff\xd9"


def test_pack_unpack_roundtrip():
    data = pack_frame(MobileFrameHeader(seq=3, capture_ts=12.5, mirror=True), JPEG)
    header, jpeg = unpack(data)
    assert (header.seq, header.capture_ts, header.mirror) == (3, 12.5, True)
    assert jpeg == JPEG


@pytest.mark.parametrize(
    "data",
    [
        b"\x00\x00",  # 길이 필드도 안 됨
        struct.pack(">I", 100) + b"{}",  # 헤더 길이가 데이터보다 김
        struct.pack(">I", 2) + b"{}" + JPEG,  # seq 없음
        struct.pack(">I", 3) + b"{x}" + JPEG,  # JSON 아님
        struct.pack(">I", 10) + b'{"seq": 1}' + b"PNG...",  # JPEG 아님
    ],
)
def test_unpack_rejects_malformed(data):
    with pytest.raises(ValueError):
        unpack(data)


def test_parse_client_text():
    assert isinstance(parse_client_text('{"type":"pip","enabled":true}'), Pip)
    pong = parse_client_text('{"type":"pong","id":1,"t_server":5,"t_client":7}')
    assert isinstance(pong, Pong) and pong.t_client == 7
    assert parse_client_text('{"type":"hello"}') is None
    assert parse_client_text("not json") is None
