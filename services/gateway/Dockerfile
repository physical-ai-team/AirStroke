# 빌드 컨텍스트: 레포 루트 (docker-compose.yml 참고)
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY shared/requirements.txt shared/requirements.txt
COPY services/gateway/requirements.txt services/gateway/requirements.txt
RUN pip install --no-cache-dir -r shared/requirements.txt -r services/gateway/requirements.txt

COPY shared shared
RUN pip install --no-cache-dir --no-deps ./shared

COPY services/gateway/gateway services/gateway/gateway
# 개발 중에는 compose가 ./web 을 볼륨으로 덮어쓴다
COPY web web

WORKDIR /app/services/gateway
EXPOSE 8443
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-m", "gateway.healthcheck"]
CMD ["python", "-m", "gateway"]
