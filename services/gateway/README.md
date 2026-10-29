# gateway (담당: 김세광)

FastAPI + WebSocket. 폰 카메라 페이지와 PC 그림판 페이지를 HTTPS(자체 서명)로 서빙하고, 폰 프레임을 Redis에 넣고, 처리 결과를 PC로 전달합니다.

## 역할
- `/mobile/`, `/canvas/` 정적 서빙 (`web/` 폴더, 개발 중에는 볼륨 마운트)
- `GET /health`: Redis ping + vision·gesture 하트비트 상태
- `POST /api/sessions`, `GET /api/sessions/{sid}/qr.svg`(segno), `GET /api/config`
- `/ws/mobile/{sid}`: 바이너리 프레임 수신 → `FrameMsg` → `frames:{sid}` publish → ack
- `/ws/pc/{sid}`: `landmarks`·`commands` 전달, `status`(mobile_connected). `frames`(PiP 영상)는 PC가 `{"type":"pip","enabled":true}`를 보낸 동안에만 구독해서 전달(기본 꺼짐)
- 폰·PC 모두 ping/pong으로 시계 차이 추정 → `{"type":"clock"}`
- 브라우저와 주고받는 메시지 형식과 close 코드(4404, 4409): [docs/03-protocol.md](../../docs/03-protocol.md)

## 코드
| 파일 | 내용 |
|---|---|
| `main.py` | 앱 조립, `/health`, 정적 서빙 |
| `sessions.py` | 세션·QR·설정 HTTP API, `mobile_url` 규칙 |
| `ws.py` | 폰·PC WebSocket, 연결 레지스트리(`Hub`, 프로세스 메모리) |
| `protocol.py` | WebSocket 메시지 모델, 바이너리 프레이밍 |
| `clock.py` | 시계 차이 추정 (순수 로직) |

## 입출력
| 방향 | 채널 / 경로 | 비고 |
|---|---|---|
| 입력 | 폰 WebSocket | `[4B 길이][JSON 헤더][JPEG]` |
| 출력 | `frames:{sid}` | `FrameMsg`, `trace.capture`(환산, 첫 추정 전에는 null), `trace.gw_recv` 채움 |
| 입력 | `landmarks:{sid}`, `commands:{sid}` | 구독해서 PC WebSocket으로 전달 |
| 입력 | `frames:{sid}` | PiP가 켜진 PC만 구독, 같은 바이너리 형식으로 전달 |
| 키 | `session:{sid}`, `health:*` | 세션 TTL(연결 중 연장), 하트비트 조회 |

## 단독 실행
```powershell
docker compose up -d redis
cd services/gateway
python -m gateway          # certs/ 가 있으면 HTTPS, 없으면 경고 후 HTTP
```
- `https://localhost:8443/health`
- 테스트: 레포 루트에서 `pytest services/gateway` (fakeredis 사용, Redis 불필요)
- 브라우저 없이 왕복 확인: `python tools/ws_client.py` (레포 루트, conda 환경)

## 설정 (.env)
`GATEWAY_PORT`, `PUBLIC_HOST`, `SESSION_TTL_SEC`, `MAX_INFLIGHT_FRAMES`, `CAMERA_*`, `JPEG_QUALITY`, `ACTIVE_AREA`, `CLOCK_PING_INTERVAL_SEC`, `CLOCK_SAMPLES`, `STATS_INTERVAL_SEC`
