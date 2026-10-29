"""python -m gateway — 인증서가 있으면 HTTPS, 없으면 경고 후 HTTP로 기동."""

import uvicorn

from .config import CERT_FILE, KEY_FILE, PORT
from .main import log


def main() -> None:
    ssl = {}
    if CERT_FILE.exists() and KEY_FILE.exists():
        ssl = {"ssl_certfile": str(CERT_FILE), "ssl_keyfile": str(KEY_FILE)}
    else:
        log.warning(
            "cert_missing",
            extra={
                "cert_file": str(CERT_FILE),
                "hint": "tools/gen_cert.py 실행 필요. HTTP로 기동 — 폰 카메라 사용 불가",
            },
        )
    log.info("listen", extra={"port": PORT, "https": bool(ssl)})
    uvicorn.run(
        "gateway.main:app",
        host="0.0.0.0",
        port=PORT,
        log_config=None,  # root의 JSON 핸들러를 그대로 쓰게 한다
        access_log=False,
        **ssl,
    )


if __name__ == "__main__":
    main()
