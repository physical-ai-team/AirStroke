# gateway (담당: 김세광)

FastAPI + WebSocket. 폰 카메라 페이지와 PC 그림판 페이지를 HTTPS(자체 서명)로 서빙하고, 폰 프레임을 Redis에 넣고, 처리 결과를 PC로 전달합니다.

## 역할
- `/mobile/`, `/canvas/` 정적 서빙 (`web/` 폴더, 개발 중에는 볼륨 마운트)
- `GET /health`: Redis ping + vision·gesture 하트비트 상태
- (2단계) 세션 생성·QR(SVG) 발급, 폰 WebSocket(바이너리 JPEG) 수신, 흐름 제어(최대 2프레임 in-flight), ping/pong 시계 차이 추정
- (2~3단계) PC WebSocket으로 `landmarks`·`commands` 전달. `frames`(PiP 영상)는 PC가 `{"type":"pip","enabled":true}`를 보낸 동안에만 전달하고, 기본값은 보내지 않음
- 브라우저와 주고받는 메시지 형식: [CLAUDE.md §3-1](../../CLAUDE.md)

## 입출력
| 방향 | 채널 / 경로 | 비고 |
|---|---|---|
| 입력 | 폰 WebSocket | 바이너리 JPEG + 헤더 (2단계) |
| 출력 | `frames:{sid}` | `FrameMsg`, `trace.capture`(환산), `trace.gw_recv` 채움 |
| 입력 | `frames:{sid}`, `landmarks:{sid}`, `commands:{sid}` | 구독해서 PC WebSocket으로 전달 |
| 키 | `session:{sid}`, `health:*` | 세션 TTL, 하트비트 조회 |

## 단독 실행
```powershell
docker compose up -d redis
cd services/gateway
python -m gateway          # certs/ 가 있으면 HTTPS, 없으면 경고 후 HTTP
```
- `https://localhost:8443/health`
- 테스트: 레포 루트에서 `pytest services/gateway` (fakeredis 사용, Redis 불필요)

## 설정 (.env)
`GATEWAY_PORT`, `PUBLIC_HOST`, `SESSION_TTL_SEC`, `MAX_INFLIGHT_FRAMES`, `CAMERA_*`, `JPEG_QUALITY`
