from pathlib import Path

from airstroke_shared.settings import env_float, env_int, env_str

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

# 세션 / QR
PUBLIC_HOST = env_str("PUBLIC_HOST", "")
SESSION_TTL_SEC = env_int("SESSION_TTL_SEC", 3600)

# /api/config 로 브라우저에 내려주는 값
CAMERA_WIDTH = env_int("CAMERA_WIDTH", 640)
CAMERA_HEIGHT = env_int("CAMERA_HEIGHT", 480)
CAMERA_FPS = env_int("CAMERA_FPS", 15)
JPEG_QUALITY = env_int("JPEG_QUALITY", 70)
MAX_INFLIGHT_FRAMES = env_int("MAX_INFLIGHT_FRAMES", 2)
ACTIVE_AREA = env_float("ACTIVE_AREA", 0.7)

# 시계 동기화: ping 주기, RTT 최소값을 고를 최근 샘플 수
CLOCK_PING_INTERVAL_SEC = env_float("CLOCK_PING_INTERVAL_SEC", 2.0)
CLOCK_SAMPLES = env_int("CLOCK_SAMPLES", 10)

STATS_INTERVAL_SEC = env_float("STATS_INTERVAL_SEC", 5)
