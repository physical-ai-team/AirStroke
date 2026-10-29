"""자체 서명 HTTPS 인증서 생성 + .env 의 PUBLIC_HOST 갱신.

    python tools/gen_cert.py                 # LAN IP 후보 목록에서 직접 선택
    python tools/gen_cert.py --ip 192.168.0.10

Windows에는 Docker/WSL/VPN 가상 어댑터가 많아 IP를 자동으로 고르지 않는다.
네트워크(와이파이·핫스팟)가 바뀌어 IP가 달라지면 다시 실행하고 gateway를 재시작할 것.
"""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import re
import shutil
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

import psutil
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[1]
CERT_DIR = ROOT / "certs"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"

VIRTUAL_HINTS = (
    "vethernet", "wsl", "docker", "virtual", "vmware", "virtualbox", "vbox", "hyper-v",
    "loopback", "tailscale", "zerotier", "vpn", "tap", "tun", "wireguard", "bluetooth",
)  # fmt: skip
WIFI_HINTS = ("wi-fi", "wifi", "wlan", "wireless", "무선")


@dataclass
class Candidate:
    adapter: str
    ip: str
    up: bool
    virtual: bool
    wifi: bool


def candidates() -> list[Candidate]:
    stats = psutil.net_if_stats()
    found = []
    for name, addrs in psutil.net_if_addrs().items():
        lowered = name.lower()
        st = stats.get(name)
        for addr in addrs:
            if addr.family != socket.AF_INET:
                continue
            ip = ipaddress.ip_address(addr.address)
            if ip.is_loopback or ip.is_link_local:
                continue
            found.append(
                Candidate(
                    adapter=name,
                    ip=addr.address,
                    up=bool(st and st.isup),
                    virtual=any(h in lowered for h in VIRTUAL_HINTS),
                    wifi=any(h in lowered for h in WIFI_HINTS),
                )
            )
    # 정렬만 할 뿐 자동 선택은 하지 않는다
    found.sort(key=lambda c: (not c.up, c.virtual, not c.wifi, c.adapter))
    return found


def choose_ip(cands: list[Candidate]) -> str:
    if not sys.stdin.isatty():
        raise SystemExit("대화형 터미널이 아닙니다. --ip <PC의 LAN IP> 로 지정하세요.")
    print("\nPC의 LAN IP 후보 (폰과 같은 와이파이/핫스팟에 연결된 어댑터를 고르세요)\n")
    for i, c in enumerate(cands, 1):
        notes = []
        if not c.up:
            notes.append("연결 안 됨")
        if c.virtual:
            notes.append("가상 어댑터일 가능성 높음")
        if c.wifi:
            notes.append("Wi-Fi")
        print(f"  [{i}] {c.ip:<16} {c.adapter:<40} {', '.join(notes)}")
    print("\n확실하지 않으면 PowerShell에서 `ipconfig` 로 'Wi-Fi' 어댑터의 IPv4 주소를 확인하세요.")
    while True:
        answer = input("번호 또는 IP 직접 입력: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(cands):
            return cands[int(answer) - 1].ip
        try:
            return str(ipaddress.IPv4Address(answer))
        except ValueError:
            print("  올바른 번호나 IPv4 주소가 아닙니다.")


def make_cert(ip: str, days: int = 365) -> tuple[bytes, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"AirStroke dev ({ip})")])
    now = dt.datetime.now(dt.UTC)
    san = x509.SubjectAlternativeName(
        [
            x509.IPAddress(ipaddress.IPv4Address(ip)),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            x509.DNSName("localhost"),
        ]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(san, critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    return cert.public_bytes(serialization.Encoding.PEM), key_pem


def set_env_value(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    line = f"{key}={value}"
    if pattern.search(text):
        return pattern.sub(line, text, count=1)
    return text.rstrip("\n") + f"\n{line}\n"


def update_env(ip: str) -> None:
    if not ENV_FILE.exists():
        shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
        print(f".env 가 없어 .env.example 에서 생성: {ENV_FILE}")
    text = ENV_FILE.read_text(encoding="utf-8")
    ENV_FILE.write_text(set_env_value(text, "PUBLIC_HOST", ip), encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--ip", help="인증서 SAN과 PUBLIC_HOST 에 넣을 PC의 LAN IP")
    parser.add_argument("--days", type=int, default=365)
    args = parser.parse_args()

    ip = str(ipaddress.IPv4Address(args.ip)) if args.ip else choose_ip(candidates())
    cert_pem, key_pem = make_cert(ip, args.days)
    CERT_DIR.mkdir(exist_ok=True)
    (CERT_DIR / "cert.pem").write_bytes(cert_pem)
    (CERT_DIR / "key.pem").write_bytes(key_pem)
    update_env(ip)

    port = "8443"
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("GATEWAY_PORT="):
            port = line.split("=", 1)[1].strip() or port
    print(f"\n인증서 생성 완료: {CERT_DIR / 'cert.pem'} (SAN: {ip}, 127.0.0.1, localhost)")
    print(f".env PUBLIC_HOST={ip}")
    print("\n다음 단계:")
    print("  1) docker compose up -d   (이미 떠 있으면: docker compose restart gateway)")
    print(f"  2) 폰에서 https://{ip}:{port}/mobile/ 접속 → 인증서 경고 '고급 → 계속' 수락")


if __name__ == "__main__":
    main()
