# 6. 단계별 계획

각 단계가 끝나면 실행·확인 방법을 정리하고 이 문서의 진행 현황을 갱신합니다.

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | docker-compose 뼈대, 서비스 헬스체크, Redis 연결, shared 스키마, 개발 도구 | ✅ 완료 (2026-10-29) |
| 2 | QR 페어링, 폰 → gateway 프레임 스트리밍, 시계 차이 추정, PC PiP 영상 | 🚧 구현 완료 (PiP #11), 실제 폰 최종 확인 남음 |
| 3 | vision 연동, PC에 손 뼈대·제스처 라벨 표시, 전체 지연시간 표시 | 🚧 vision 연동·뼈대 오버레이(#10) 완료, 지연시간 표시 남음 |
| 4 | gesture 연동, 검지로 그리기 | 🚧 실제 폰으로 그리기 확인, 상태별 표현(#10) 완료, 시연 모드 남음 |
| 5 | 지우개, 색상 변경, 실행 취소, PNG 저장 | 🚧 그림판에 구현됨, 실제 손 확인 남음 |

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
1. ✅ gateway: `POST /api/sessions`, QR SVG, `/api/config`, `session:{sid}` 키
2. ✅ gateway: `/ws/pc/{sid}` — `landmarks`·`commands` 전달, PiP 켜기/끄기에 따른 `frames` 전달
3. ✅ gateway: `/ws/mobile/{sid}` — 바이너리 프레임 수신 → `frames` publish → ack
4. ✅ gateway: ping/pong 시계 차이 추정 (화면 표시는 3단계)
5. ✅ mobile: 카메라 페이지 (전면/후면 전환, 흐름 제어) — 박민성, #8
6. ✅ canvas: QR 표시 — 조아람, #6 / PiP 패널(기본 꺼짐, 모서리 이동, 크기 조절, mirror 반전) — 박민성, #11 (사전 합의로 박민성이 `web/canvas/pip.js`로 작업)

**작업 기록**
| 작업 | 담당 | PR |
|---|---|---|
| gateway 세션 API·WebSocket·시계 추정 | 김세광 | #2 |
| 폰 카메라 페이지 | 박민성 | #8 |
| 그림판 기본(2겹 캔버스, 세션 연결, 팔레트·굵기·실행 취소·PNG, 테스트 모드) | 조아람 | #6 |
| PiP 패널 (`web/canvas/pip.js`, `pip.css`) | 박민성 (사전 합의) | #11 |

**gateway 단독 확인**(1~4): `python tools/ws_client.py` — 세션 생성 → PC(PiP 켬)+폰 역할로 왕복하고 status·ack·PiP·시계 추정을 OK/NG로 출력합니다.

**확인 기록** (2026-10-29)
- `pytest` 57개 통과, `ruff check`/`ruff format --check` 통과
- `gen_cert.py`(Wi-Fi 192.168.45.89) → `docker compose up -d` → gateway HTTPS 기동, 4개 서비스 healthy
- `mobile_url`이 localhost·LAN IP 접속 모두 `https://192.168.45.89:8443/mobile/?s=…`
- `ws_client.py`(wss, 6초, skew 3000ms): 90장 송신·90장 ack·버림 0, ack p50 4.0ms, PiP 90장, 추정 offset 2990ms(RTT 2.5ms) — 4개 항목 OK
- 실제 폰(같은 Wi-Fi)에서 `https://192.168.45.89:8443/mobile/` 인증서 수락 후 보안 컨텍스트 확인(카메라 사용 가능 조건). Wi-Fi가 공용 프로필이지만 별도 방화벽 규칙 없이 접속됨
- 남은 확인: canvas PiP가 붙은 뒤 PiP 켜기/끄기 → 폰 송신 fps·버린 프레임 수

**통합 확인 기록** (2026-10-29, #5~#8 머지 후 main)
- `pytest` 104개 통과(1 skip: 로컬에 vision 모델 없음), `ruff` 통과. 4개 서비스 재빌드 후 healthy
- `ws_client.py`(합성 영상): 90장 송신·90장 ack, PC가 landmarks·command 각 89개, PiP 90장 수신 — 폰 → gateway → vision → gesture → PC 전체 경로 연결
- vision 처리: 약 14.7fps, 추론 평균 16ms(p95 22ms), gateway 수신 → vision 완료 평균 19ms
- **실제 폰**(같은 Wi-Fi, 전면): 그림판 QR 스캔 → 접속, 검지 그리기·지우개·정지 동작, 손을 오른쪽으로 움직이면 커서도 오른쪽(좌우 반전 정상)
- 세로 프레임 허용(D-018) 후 실제 폰 세로·가로로 그려 정상 동작 확인. `frames`·`landmarks`에 `width`·`height` 실림
- 참고: Docker(WSL2) 시계가 Windows보다 약 0.2~0.3초 늦어 `ws_client`의 시계 항목이 NG → 코드 문제 아님(README 문제 해결 참고). PC 그림판의 지연 표시는 PC로 오는 `clock`으로 보정해야 함

**확인 방법**: PC에서 QR 표시 → 폰으로 스캔 → PiP를 켜면 영상이 보이고, 끄면 PC 수신이 멈추는지 확인합니다. 폰 화면의 송신 fps와 버린 프레임 수도 확인합니다.

## 3단계 — 손 뼈대
- ✅ vision: 세션별 `HandLandmarker`(VIDEO 모드), `NUM_HANDS`, 모델 파일은 Docker 빌드 때 받습니다. — 김정윤, #7
- ✅ canvas: 뼈대 오버레이(좌표 변환 적용, D-018 세로 프레임 포함), 제스처 라벨 — 조아람, #10
- canvas: FPS·지연시간 표시(크게, 켜고 끌 수 있게) 남음
- **확인 방법**: `stream_frames.py`(웹캠)로 먼저 확인한 뒤 실제 폰으로 확인합니다. `record_landmarks.py`로 실제 손 fixture를 녹화합니다.

## 4단계 — 그리기
- ✅ gesture: `core/`(판별·분류·디바운스·매핑·One Euro·stroke_id)와 pytest — 이기태, #5
- ✅ canvas: draw 선 그리기(조아람, #6), 상태별 표현(검지 끝 강조, move일 때 흐리게 — 조아람, #10)
- canvas: 시연 모드 남음
- **확인 방법**: `pytest services/gesture`, `mock_landmarks.py`로 재생해 확인한 뒤 실제 손으로 그려 봅니다.

## 5단계 — 편집 기능
- 지우개, 색상 변경, 실행 취소(stroke 단위), PNG 저장
- 제스처 추가(D-019): 👌 집기 → 원형 팔레트 색 선택, 👍 엄지 세움 → 실행 취소(한 번만)
- **확인 방법**: `mock_commands.py`와 실제 손으로 각각 확인합니다.
