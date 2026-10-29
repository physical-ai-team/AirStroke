"""gateway WebSocket 확인용 클라이언트 — 브라우저 페이지 없이 폰·PC 역할을 흉내 낸다.

    python tools/ws_client.py                          # 세션 생성 → PC(PiP 켬)+폰 왕복 확인 (10초)
    python tools/ws_client.py --seconds 30 --skew 3000 --source 0
    python tools/ws_client.py pc --session <sid> --pip # PC 수신 통계 (mock_commands 와 함께)
    python tools/ws_client.py mobile --session <sid>   # 폰 역할만 (합성 영상 또는 --source 0)

- 폰 역할: [4B 헤더 길이][JSON 헤더][JPEG] 전송, max_inflight_frames 흐름 제어, ping → 즉시 pong.
  --skew 로 폰 시계를 일부러 어긋나게 해서 gateway의 시계 차이 추정(clock.offset_ms)을 확인한다.
- PC 역할: status / landmarks / command / PiP 바이너리 수신 수를 센다.
- 주소 기본값: certs/ 가 있으면 https, 없으면 http. 포트는 .env 의 GATEWAY_PORT.
"""

from __future__ import annotations

import argparse
import json
import ssl
import struct
import sys
import threading
import time
import urllib.request
from collections import Counter

import cv2
import numpy as np
from _common import ROOT
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import ClientConnection, connect

from airstroke_shared.schemas import now_ms
from airstroke_shared.settings import env_int

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE  # 자체 서명 인증서


def default_base() -> str:
    scheme = "https" if (ROOT / "certs" / "cert.pem").exists() else "http"
    return f"{scheme}://localhost:{env_int('GATEWAY_PORT', 8443)}"


def http_json(base: str, path: str, method: str = "GET") -> dict:
    req = urllib.request.Request(base + path, method=method)
    ctx = SSL_CTX if base.startswith("https") else None
    with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
        return json.loads(resp.read())


def ws_connect(base: str, path: str) -> ClientConnection:
    url = base.replace("https://", "wss://").replace("http://", "ws://") + path
    return connect(url, ssl=SSL_CTX if url.startswith("wss") else None, max_size=None)


def pack_frame(header: dict, jpeg: bytes) -> bytes:
    raw = json.dumps(header).encode("utf-8")
    return struct.pack(">I", len(raw)) + raw + jpeg


class FrameSource:
    """웹캠/영상 파일, 없으면 움직이는 원을 그린 합성 영상."""

    def __init__(self, source: str | None, width: int, height: int, quality: int) -> None:
        self.size, self.quality, self.n = (width, height), quality, 0
        self.cap = None
        if source is not None:
            self.cap = cv2.VideoCapture(int(source) if source.isdigit() else source)
            if not self.cap.isOpened():
                raise SystemExit(f"소스를 열 수 없음: {source}")

    def next_jpeg(self) -> bytes:
        self.n += 1
        img = None
        if self.cap is not None:
            ok, img = self.cap.read()
            img = cv2.resize(img, self.size) if ok else None
        if img is None:
            w, h = self.size
            img = np.full((h, w, 3), 40, np.uint8)
            x = int(w / 2 + w / 3 * np.sin(self.n / 10))
            cv2.circle(img, (x, h // 2), 40, (0, 200, 255), -1)
            cv2.putText(img, f"seq {self.n}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,) * 3, 2)
        ok, jpeg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
        return jpeg.tobytes()

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()


class Mobile:
    def __init__(self, ws: ClientConnection, max_inflight: int, skew_ms: float) -> None:
        self.ws, self.max_inflight, self.skew = ws, max_inflight, skew_ms
        self.inflight: dict[int, float] = {}
        self.lock = threading.Lock()
        self.sent = self.acked = self.dropped = 0
        self.ack_ms: list[float] = []
        self.clock: dict | None = None
        self.close_code: int | None = None
        threading.Thread(target=self._read, daemon=True).start()

    def now(self) -> float:
        return now_ms() + self.skew  # 일부러 어긋난 폰 시계

    def _read(self) -> None:
        try:
            for raw in self.ws:
                msg = json.loads(raw)
                if msg["type"] == "ping":
                    pong = {"type": "pong", "id": msg["id"], "t_server": msg["t_server"]}
                    self.ws.send(json.dumps(pong | {"t_client": self.now()}))
                elif msg["type"] == "ack":
                    with self.lock:
                        t = self.inflight.pop(msg["seq"], None)
                    if t is not None:
                        self.acked += 1
                        self.ack_ms.append(now_ms() - t)
                elif msg["type"] == "clock":
                    self.clock = msg
        except ConnectionClosed as exc:
            self.close_code = exc.rcvd.code if exc.rcvd else None

    def send(self, seq: int, jpeg: bytes, mirror: bool) -> None:
        with self.lock:
            if len(self.inflight) >= self.max_inflight:
                self.dropped += 1  # 흐름 제어: 응답 대기 중인 프레임이 가득 차면 버린다
                return
            self.inflight[seq] = now_ms()
        self.ws.send(pack_frame({"seq": seq, "capture_ts": self.now(), "mirror": mirror}, jpeg))
        self.sent += 1

    def summary(self) -> str:
        ack = sorted(self.ack_ms)
        p50 = f"{ack[len(ack) // 2]:.1f}ms" if ack else "-"
        clock = "-"
        if self.clock:
            clock = f"offset {self.clock['offset_ms']:.1f}ms, rtt {self.clock['rtt_ms']:.1f}ms"
        return (
            f"[mobile] sent {self.sent}, acked {self.acked}, dropped {self.dropped}, "
            f"ack p50 {p50}, clock({clock})"
        )


class Pc:
    def __init__(self, ws: ClientConnection) -> None:
        self.ws = ws
        self.counts: Counter[str] = Counter()
        self.status: list[bool] = []
        self.pip_mirror: bool | None = None
        self.pip_delay_ms: list[float] = []  # 같은 PC라면 gateway 수신 → PiP 도착
        self.clock: dict | None = None
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        try:
            for raw in self.ws:
                if isinstance(raw, bytes):
                    (n,) = struct.unpack(">I", raw[:4])
                    header = json.loads(raw[4 : 4 + n])
                    self.counts["pip"] += 1
                    self.pip_mirror = header["mirror"]
                    if header["trace"].get("gw_recv"):
                        self.pip_delay_ms.append(now_ms() - header["trace"]["gw_recv"])
                    continue
                msg = json.loads(raw)
                self.counts[msg["type"]] += 1
                if msg["type"] == "ping":
                    pong = {"type": "pong", "id": msg["id"], "t_server": msg["t_server"]}
                    self.ws.send(json.dumps(pong | {"t_client": now_ms()}))
                elif msg["type"] == "status":
                    self.status.append(msg["mobile_connected"])
                elif msg["type"] == "clock":
                    self.clock = msg
        except ConnectionClosed:
            pass

    def pip(self, enabled: bool) -> None:
        self.ws.send(json.dumps({"type": "pip", "enabled": enabled}))

    def summary(self) -> str:
        delay = sorted(self.pip_delay_ms)
        p50 = f"{delay[len(delay) // 2]:.1f}ms" if delay else "-"
        return f"[pc] {dict(self.counts)}, status {self.status}, pip p50 {p50}"


def run_mobile(mobile: Mobile, src: FrameSource, fps: float, seconds: float, mirror: bool) -> None:
    interval, seq = 1.0 / fps, 0
    end = time.monotonic() + seconds
    next_t = time.monotonic()
    while time.monotonic() < end and mobile.close_code is None:
        mobile.send(seq, src.next_jpeg(), mirror)
        seq += 1
        next_t += interval
        time.sleep(max(0.0, next_t - time.monotonic()))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "role", nargs="?", default="roundtrip", choices=["roundtrip", "pc", "mobile"]
    )
    parser.add_argument("--base", default=default_base(), help="gateway 주소 (기본: %(default)s)")
    parser.add_argument(
        "--session", help="pc/mobile 역할에서 쓸 세션 ID (POST /api/sessions 로 생성)"
    )
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--skew", type=float, default=2000, help="폰 시계를 일부러 어긋나게 할 ms")
    parser.add_argument("--source", default=None, help="웹캠 번호/영상 파일 (기본: 합성 영상)")
    parser.add_argument("--mirror", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--pip", action="store_true", help="pc 역할: PiP 켜기")
    args = parser.parse_args()

    cfg = http_json(args.base, "/api/config")
    cam = cfg["camera"]

    if args.role == "roundtrip":
        session = http_json(args.base, "/api/sessions", method="POST")
        sid = session["session_id"]
        print(
            f"세션 {sid}\n  mobile_url {session['mobile_url']}\n  qr {args.base}{session['qr_url']}"
        )
    elif not args.session:
        parser.error("pc/mobile 역할은 --session 필요")
    else:
        sid = args.session

    pc = Pc(ws_connect(args.base, f"/ws/pc/{sid}")) if args.role in ("roundtrip", "pc") else None
    if pc is not None and (args.pip or args.role == "roundtrip"):
        pc.pip(True)
    if args.role == "pc":
        end = time.monotonic() + args.seconds
        try:
            while time.monotonic() < end:
                time.sleep(2)
                print(pc.summary())
        except KeyboardInterrupt:
            pass
        pc.ws.close()
        return 0

    mobile = Mobile(
        ws_connect(args.base, f"/ws/mobile/{sid}"), cfg["max_inflight_frames"], args.skew
    )
    src = FrameSource(args.source, cam["width"], cam["height"], cam["jpeg_quality"])
    print(f"폰 송신 {cam['width']}x{cam['height']} @ {cam['fps']}fps, {args.seconds:.0f}초, "
          f"skew {args.skew:.0f}ms")  # fmt: skip
    try:
        run_mobile(mobile, src, cam["fps"], args.seconds, args.mirror)
    except KeyboardInterrupt:
        pass
    finally:
        src.close()
    time.sleep(0.5)  # 마지막 ack·PiP 도착 대기
    mobile.ws.close()
    time.sleep(0.3)
    print(mobile.summary())
    if mobile.close_code is not None:
        print(f"[mobile] 서버가 연결을 닫음: code {mobile.close_code}")
    if pc is None:
        return 0

    print(pc.summary())
    pc.ws.close()
    checks = {
        "폰 연결/해제가 PC status로 전달": pc.status[:1] == [False] and True in pc.status
        and pc.status[-1] is False,
        "frames publish 후 ack": mobile.acked > 0,
        "PiP 영상 수신 (mirror 포함)": pc.counts["pip"] > 0 and pc.pip_mirror == args.mirror,
        "시계 차이 추정 ≈ skew": mobile.clock is not None
        and abs(mobile.clock["offset_ms"] - args.skew) < 50 + mobile.clock["rtt_ms"],
    }  # fmt: skip
    for name, ok in checks.items():
        print(f"  {'OK ' if ok else 'NG '} {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
