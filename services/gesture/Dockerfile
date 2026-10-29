# 빌드 컨텍스트: 레포 루트
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY shared/requirements.txt shared/requirements.txt
COPY services/gesture/requirements.txt services/gesture/requirements.txt
RUN pip install --no-cache-dir -r shared/requirements.txt -r services/gesture/requirements.txt

COPY shared shared
RUN pip install --no-cache-dir --no-deps ./shared

COPY services/gesture/gesture services/gesture/gesture

WORKDIR /app/services/gesture
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-m", "airstroke_shared.health", "gesture"]
CMD ["python", "-m", "gesture"]
