"""HandLandmarker 모델 파일(.task) 위치와 내려받기.

Docker 빌드 때와 로컬 개발 때 같은 방법으로 받는다 (services/vision 에서 실행):
    python vision/model.py
이미 받은 파일의 해시가 맞으면 다시 받지 않는다. 모델 파일은 커밋하지 않는다(.gitignore *.task).
"""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

from airstroke_shared.log import get_logger

# float16 v1 고정 — latest 를 쓰면 같은 이미지라도 빌드 시점마다 모델이 달라질 수 있다
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)
MODEL_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"
MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "hand_landmarker.task"

log = get_logger("vision")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_ready(path: Path = MODEL_PATH) -> bool:
    return path.is_file() and _sha256(path) == MODEL_SHA256


def download(path: Path = MODEL_PATH) -> Path:
    if is_ready(path):
        log.info("model_ready", extra={"path": str(path)})
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    urllib.request.urlretrieve(MODEL_URL, tmp)
    digest = _sha256(tmp)
    if digest != MODEL_SHA256:
        tmp.unlink()
        raise RuntimeError(f"model sha256 mismatch: {digest}")
    tmp.replace(path)
    log.info("model_downloaded", extra={"path": str(path), "bytes": path.stat().st_size})
    return path


if __name__ == "__main__":
    download()
