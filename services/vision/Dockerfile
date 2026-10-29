# 빌드 컨텍스트: 레포 루트. CPU 전용 (GPU/CUDA 미사용)
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# opencv-contrib-python: libGL, glib / mediapipe가 import 시 sounddevice를 불러옴: PortAudio
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY shared/requirements.txt shared/requirements.txt
COPY services/vision/requirements.txt services/vision/requirements.txt
RUN pip install --no-cache-dir -r shared/requirements.txt -r services/vision/requirements.txt

COPY shared shared
RUN pip install --no-cache-dir --no-deps ./shared

# 모델은 코드보다 먼저 받아 레이어 캐시를 살린다 (model.py 가 바뀔 때만 다시 받음)
WORKDIR /app/services/vision
COPY services/vision/vision/model.py vision/model.py
RUN python vision/model.py

COPY services/vision/vision vision
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-m", "airstroke_shared.health", "vision"]
CMD ["python", "-m", "vision"]
