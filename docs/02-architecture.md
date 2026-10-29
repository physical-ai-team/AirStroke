# 2. 아키텍처

## 전체 구조

```
 [폰 브라우저 /mobile]                                     [PC 브라우저 /canvas]
   getUserMedia → JPEG                                     캔버스 2겹 (+ 선택: PiP)
        │ WebSocket(바이너리)                                    ▲ WebSocket
        ▼                                                       │
   ┌─────────┐  frames:{sid}   ┌────────┐ landmarks:{sid} ┌─────────┐ commands:{sid}
   │ gateway │ ──────────────▶ │ vision │ ──────────────▶ │ gesture │ ───────┐
   │ FastAPI │                 └────────┘        │        └─────────┘        │
   │ HTTPS   │ ◀─────────────────────────────────┴───────────────────────────┘
   └─────────┘      (gateway가 landmarks·commands 구독 → PC로 전달)
          └──────────────── redis (pub/sub) ────────────────┘
```

Docker Compose 기반 마이크로서비스입니다. 서비스끼리는 **Redis pub/sub으로만** 통신하고 서로를 직접 호출하지 않습니다. 그래서 각 서비스를 따로 실행하고 따로 테스트할 수 있습니다.

## 컨테이너
| 서비스 | 기술 | 역할 | 담당 |
|---|---|---|---|
| gateway | FastAPI, uvicorn, WebSocket | 세션·QR 페어링, `/mobile`·`/canvas` 정적 서빙(HTTPS), 폰 프레임 수신 → `frames` publish, `landmarks`·`commands` 구독 → PC로 전달(`frames`는 PiP가 켜졌을 때만), 폰·PC 시계 차이 추정 | 김세광 |
| vision | MediaPipe Tasks `HandLandmarker` (CPU) | `frames:*` 구독 → 손 랜드마크 21개 추출 → `landmarks` publish | 김정윤 |
| gesture | 순수 Python | `landmarks:*` 구독 → 손가락 판별 → 제스처 분류 → 디바운스 + One Euro Filter → `commands` publish | 이기태 |
| redis | redis:7.4 | pub/sub 브로커, 세션 키, 하트비트 키 | 김세광 |

프론트엔드(`web/mobile`, `web/canvas`)는 gateway가 서빙하는 바닐라 JS 정적 파일입니다. 개발 중에는 볼륨 마운트를 쓰므로 새로고침만 하면 수정이 반영됩니다.

## 한 프레임의 여정과 타임스탬프

| 단계 | 위치 | 기록 필드 | 시계 |
|---|---|---|---|
| ① 촬영 | 폰 | `trace.capture` | 폰 시계 → gateway가 offset으로 환산 |
| ② 수신 | gateway | `trace.gw_recv` | gateway |
| ③ 추론 완료 | vision | `trace.vision_done` | 서버 (같은 호스트) |
| ④ 분류 완료 | gesture | `trace.gesture_done` | 서버 |
| ⑤ 화면 표시 | PC 브라우저 | (메시지에 없음, 브라우저에서 계산) | PC 시계 → offset으로 환산 |

전체 지연 = ⑤ − ①. 구간별 지연(예: 추론 시간 = ③ − ②)도 같은 방식으로 구합니다. PC 화면에는 FPS와 전체 지연(ms)을 표시합니다(3단계).

## 처리 정책

### 폰 → gateway 흐름 제어
- 폰은 ack를 받지 않은 프레임을 **최대 `MAX_INFLIGHT_FRAMES`(기본 2)장**까지 보낼 수 있습니다.
- 이미 2장이 응답을 기다리는 중이면 새로 찍은 프레임은 **버립니다**(큐에 쌓지 않음). 네트워크가 느려도 지연이 쌓이지 않고, 최신 화면 위주로 전송됩니다.

### vision: 최신 프레임만 처리
- 구독 루프는 세션별 "최신 프레임 슬롯" 하나를 계속 덮어쓰고, 추론 루프는 그 슬롯에서 꺼냅니다([latest.py](../services/vision/vision/latest.py)).
- 추론이 느리면 중간 프레임은 자동으로 버려지고, 버린 수는 `dropped` 통계로 남습니다.
- **세션마다 `HandLandmarker` 인스턴스를 따로 만듭니다.** VIDEO 모드는 타임스탬프가 단조 증가해야 하기 때문입니다. 일정 시간(`VISION_SESSION_IDLE_SEC`) 동안 프레임이 없으면 인스턴스를 해제합니다.

### gesture: 모든 메시지를 순서대로 처리
- 디바운스와 필터에 상태가 있으므로 메시지를 버리지 않습니다. 상태는 세션별로 둡니다. 랜드마크 메시지는 작고 처리가 가벼워서 밀릴 일이 거의 없습니다.

### 시계 동기화
- gateway가 폰·PC와 WebSocket ping/pong을 주고받아 각 기기의 시계 차이(offset)를 추정합니다(NTP 방식). 모든 trace 시각은 **gateway 시계 기준**입니다.
- 2단계에서는 추정까지 구현하고, 전체 지연시간 화면 표시는 3단계에서 붙입니다. 프로토콜은 [03-protocol.md](03-protocol.md)에 있습니다.

### 세션
- PC가 세션을 만들면 `session:{sid}` 키가 TTL(`SESSION_TTL_SEC`)과 함께 Redis에 저장됩니다. gateway를 재시작해도 세션이 남습니다.
- vision과 gesture는 `PSUBSCRIBE frames:*` / `landmarks:*`로 세션을 자동으로 찾습니다. 세션 등록 절차는 따로 없습니다.

### PiP 영상 전달
- 기본값은 꺼짐입니다. PC가 PiP를 켰다고 알린 동안에만 gateway가 `frames`를 PC로 보냅니다.
- vision으로 가는 `frames` publish는 PiP와 관계없이 항상 합니다.

## 헬스체크와 로그
- gateway는 `GET /health`를 제공합니다. Redis ping 결과와 vision·gesture 하트비트(처리 수, fps, 버린 수)를 함께 보여줍니다.
- vision과 gesture는 HTTP 서버가 없으므로 Redis 키 `health:{service}`(TTL)를 주기적으로 갱신합니다. Docker healthcheck는 `python -m airstroke_shared.health <service>`로 이 키를 확인합니다.
- 모든 서비스는 표준 출력에 **JSON 구조화 로그**를 남깁니다(`airstroke_shared.log`).

## HTTPS
- 폰의 `getUserMedia`는 HTTPS가 필수이므로 gateway가 자체 서명 인증서로 HTTPS를 제공합니다.
- `tools/gen_cert.py`가 인증서를 만들고 `.env`의 `PUBLIC_HOST`도 함께 설정합니다. LAN IP는 후보 목록에서 **사람이 고릅니다**(Windows에는 가상 어댑터가 많아서 자동 선택하지 않음).
- 인증서가 없으면 gateway는 경고를 남기고 HTTP로 기동합니다. 이 경우 폰 카메라는 동작하지 않지만, 다른 서비스 개발에는 지장이 없습니다.
