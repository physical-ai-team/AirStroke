"""Docker healthcheck: 자기 /health 호출. 스킴은 __main__ 과 같은 기준(인증서 유무)으로 고른다."""

import ssl
import sys
import urllib.request

from .config import CERT_FILE, KEY_FILE, PORT


def main() -> int:
    https = CERT_FILE.exists() and KEY_FILE.exists()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # 자체 서명 인증서
    url = f"{'https' if https else 'http'}://127.0.0.1:{PORT}/health"
    try:
        with urllib.request.urlopen(url, timeout=3, context=ctx if https else None) as resp:
            return 0 if resp.status == 200 else 1
    except Exception:  # noqa: BLE001
        return 1


if __name__ == "__main__":
    sys.exit(main())
