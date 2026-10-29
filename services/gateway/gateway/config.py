from pathlib import Path

from airstroke_shared.settings import env_int, env_str

# 로컬: <repo>/services/gateway/gateway/config.py → <repo>
# 컨테이너: /app/services/gateway/gateway/config.py → /app
REPO_ROOT = Path(__file__).resolve().parents[3]

WEB_DIR = Path(env_str("WEB_DIR", str(REPO_ROOT / "web")))
CERT_DIR = Path(env_str("CERT_DIR", str(REPO_ROOT / "certs")))
CERT_FILE = CERT_DIR / "cert.pem"
KEY_FILE = CERT_DIR / "key.pem"

PORT = env_int("GATEWAY_PORT", 8443)

# /health 에서 하트비트를 확인할 서비스
WATCHED_SERVICES = ("vision", "gesture")
