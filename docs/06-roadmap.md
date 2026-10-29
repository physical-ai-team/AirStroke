# 6. 단계별 계획

각 단계가 끝나면 실행·확인 방법을 정리하고 이 문서의 진행 현황을 갱신합니다.

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | docker-compose 뼈대, 서비스 헬스체크, Redis 연결, shared 스키마, 개발 도구 | ✅ 완료 (2026-10-29) |
| 2 | QR 페어링, 폰 → gateway 프레임 스트리밍, 시계 차이 추정, PC PiP 영상 | ⏳ 다음 |
| 3 | vision 연동, PC에 손 뼈대·제스처 라벨 표시, 전체 지연시간 표시 | |
| 4 | gesture 연동, 검지로 그리기 | |
| 5 | 지우개, 색상 변경, 실행 취소, PNG 저장 | |

---

## 1단계 — 뼈대 ✅
**산출물**
- `docker-compose.yml` (redis, gateway, vision, gesture). 모든 서비스에 healthcheck가 있습니다.
- `shared/`: 메시지 스키마, 채널, 설정, JSON 로그, 하트비트
- gateway: `/health`, 정적 서빙, 인증서 유무에 따른 HTTPS/HTTP 기동
- vision: `frames:*` 구독, 최신 프레임 슬롯 / gesture: `landmarks:*` 구독 (처리 로직은 다음 단계)
- tools: `gen_cert`, `stream_frames`, `record_landmarks`, `mock_landmarks`, `mock_commands`, `gen_synthetic_landmarks`
- 합성 fixture, conda `environment.yml`, CLAUDE.md, README, PR 템플릿, `docs/`

**확인 방법**
```powershell
python tools/gen_cert.py
docker compose up -d --build
docker compose ps                          # 모두 (healthy)
curl.exe -k https://localhost:8443/health
python tools/mock_landmarks.py             # /health 에서 gesture.processed 증가
pytest ; ruff check .
```

## 2단계 — 페어링과 스트리밍
**구현 순서** (팀원 작업이 막히지 않도록 gateway 엔드포인트를 먼저 만듭니다)
1. gateway: `POST /api/sessions`, QR SVG, `/api/config`, `session:{sid}` 키
2. gateway: `/ws/pc/{sid}` — `landmarks`·`commands` 전달, PiP 켜기/끄기에 따른 `frames` 전달
3. gateway: `/ws/mobile/{sid}` — 바이너리 프레임 수신 → `frames` publish → ack
4. gateway: ping/pong 시계 차이 추정 (화면 표시는 3단계)
5. mobile: 카메라 페이지 (전면/후면 전환, 흐름 제어)
6. canvas: QR 표시, PiP 패널(기본 꺼짐, 위치 변경)

**확인 방법**: PC에서 QR 표시 → 폰으로 스캔 → PiP를 켜면 영상이 보이고, 끄면 PC 수신이 멈추는지 확인합니다. 폰 화면의 송신 fps와 버린 프레임 수도 확인합니다.

## 3단계 — 손 뼈대
- vision: 세션별 `HandLandmarker`(VIDEO 모드), `NUM_HANDS`, 모델 파일은 Docker 빌드 때 받습니다.
- canvas: 뼈대 오버레이(좌표 변환 적용), 제스처 라벨 자리, FPS·지연시간 표시(크게, 켜고 끌 수 있게)
- **확인 방법**: `stream_frames.py`(웹캠)로 먼저 확인한 뒤 실제 폰으로 확인합니다. `record_landmarks.py`로 실제 손 fixture를 녹화합니다.

## 4단계 — 그리기
- gesture: `core/`(판별·분류·디바운스·매핑·One Euro·stroke_id)와 pytest
- canvas: draw 선 그리기, 상태별 표현(검지 끝 강조, move일 때 흐리게), 시연 모드
- **확인 방법**: `pytest services/gesture`, `mock_landmarks.py`로 재생해 확인한 뒤 실제 손으로 그려 봅니다.

## 5단계 — 편집 기능
- 지우개, 색상 변경, 실행 취소(stroke 단위), PNG 저장
- **확인 방법**: `mock_commands.py`와 실제 손으로 각각 확인합니다.
