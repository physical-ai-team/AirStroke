# 폰 카메라 페이지 — 코드 정리와 개선 방법 (`web/mobile/`)

담당 부분(폰 카메라 → gateway 송신)이 어떻게 짜여 있는지 짧게 정리하고, 성능(지연·fps·배터리)과 정확도(손 인식 품질)를 더 올릴 수 있는 방법을 모았다.
요구사항 ID(M-xx)는 [PRD.md](PRD.md), 진행 상황은 [HANDOFF.md](HANDOFF.md)를 본다.

## 1. 전체 흐름에서 이 페이지의 자리

```
폰 카메라 ──JPEG──▶ gateway ──Redis frames:*──▶ vision(MediaPipe) ──landmarks──▶ gesture(One Euro·매핑) ──commands──▶ PC 그림판
   ▲ 이 폴더               │
   └──── ack / ping·clock ◀┘
```

폰 페이지는 **영상을 일정한 속도로, 밀리지 않게** 보내는 일만 한다. 손 인식(vision)·제스처 판단(gesture)·그리기(canvas)는 다른 팀원 담당이다.

## 2. 파일 구성

| 파일 | 줄 수 | 역할 |
|---|---|---|
| `index.html` | 49 | 미리보기 `<video>`, 인코딩용 숨은 `<canvas>`, 상태 패널, 버튼(시작·전환·CSV·시연 모드) |
| `style.css` | 132 | 화면 스타일, 시연 모드(`body.demo`)에서 패널 접기·미리보기 축소 |
| `app.js` | 657 | 아래 3절의 모든 동작 |

빌드 도구·라이브러리 없이 바닐라 JS 하나로 되어 있다(PRD 5절). gateway가 `/mobile/`로 그대로 서빙한다.

## 3. `app.js` 구조 (위에서 아래 순서)

| 구역 | 주요 함수 | 하는 일 |
|---|---|---|
| 상수·상태 | `state` | 모든 실행 상태를 객체 하나에 모음(연결, 스트림, inflight, 통계 배열, 측정 기록) |
| 설정 기억 | `loadFacing`, `saveSetting`, `loadDemo` | 카메라 방향·시연 모드를 localStorage에 저장. 실패해도 기본값으로 동작(M-14) |
| 통계 | `percentile`, `mean`, `snapshot` | 최근 1초 송신 fps·KB/s, 인코딩 평균(30개), ack p50/p95(100개) |
| 화면 표시 | `renderStats` (250ms 주기) | 통계를 패널과 시연 모드 요약줄에 표시 |
| 측정 기록 | `logTick` (1초 주기), `downloadCsv` | 1초마다 한 줄씩 최대 1시간 쌓고, 기기·설정 `#` 머리줄과 함께 CSV로 저장(M-45) |
| 설정 | `loadConfig` | `GET /api/config`로 해상도·fps·품질·`max_inflight_frames` 수신, 실패 시 2초마다 재시도 |
| WebSocket | `connect` | `ping`→즉시 `pong`, `ack`→inflight 해제·왕복 시간 기록, `clock` 표시. 끊기면 0.5→5초 백오프 재연결, 4404/4409면 재연결 안 함 |
| 카메라 | `openCamera`, `cameraErrorText`, `encodeSize` | `getUserMedia`(설정값을 ideal로), 실제 `facingMode`로 `mirror` 결정, 오류별 안내(M-13), 비율 유지 인코딩 크기 |
| 프레임 송신 | `captureFrame`, `encodeFrame`, `loop` | 아래 3.1 |
| 화면 꺼짐 방지 | `requestWakeLock` | Screen Wake Lock 요청·상태 표시 |
| 배터리 | `initBattery`, `renderBattery` | Battery API(크롬 계열)로 잔량 표시, 20% 미만 경고 |
| 시작·중지 | `startCapture`, `stopCapture`, `visibilitychange` | 백그라운드로 가면 카메라 끄고, 돌아오면 같은 방향으로 재개(M-26) |

### 3.1 프레임 한 장이 나가는 과정
1. `loop()`가 목표 fps 간격으로 `captureFrame()`을 부른다. 다음 시각을 누적해서 잡아 드리프트가 쌓이지 않는다.
2. ack가 3초 넘게 안 온 프레임은 자리를 비우고 "ack 없음"으로 센다(M-25, 송신이 영원히 멈추는 것 방지).
3. **흐름 제어**: ack 대기(인코딩 중 포함)가 `max_inflight_frames`(기본 2)장이면 이번 프레임은 버린다. 네트워크·서버가 느리면 폰이 쌓아 두지 않고 최신 프레임만 보내게 된다.
4. 숨은 캔버스에 `drawImage` → `canvas.toBlob('image/jpeg', q)`로 인코딩.
5. `[4B big-endian 헤더 길이][JSON {seq, capture_ts, mirror}][JPEG]`로 묶어 `ws.send`. 보낸 시각을 inflight에 기록하고, ack가 오면 왕복 시간을 잰다.

### 3.2 설계에서 지킨 규칙
- 설정값(해상도·fps·품질·inflight)은 하드코딩하지 않고 `/api/config`에서 받는다. 페이지 내부 상수만 `app.js` 맨 위에 모음.
- 전면 카메라는 **미리보기만** 좌우 반전하고, 보내는 프레임은 원본이다. 반전은 gesture가 `mirror`를 보고 한다.
- `seq`는 실제로 보낸 프레임에만 매긴다. 폰에서 버린 것은 "버린 프레임" 수로 따로 센다.
- 통계 배열은 모두 길이 제한(`pushLimited`)이 있어 10분 이상 켜 둬도 메모리가 늘지 않는다.

### 3.3 지금까지 확인된 수치
| 환경 | 송신 fps | 버린 비율 | ack p50 / p95 | 프레임 크기 | 인코딩 |
|---|---|---|---|---|---|
| headless Chrome + gateway(fakeredis) | 15 | 0% | 1 / 3 ms | 7 KB (105 KB/s) | 8 ms |
| Galaxy 전면, 학교 Wi-Fi, 480x640·15fps·q70 | 15.0 | 0.8% | 13 / 50 ms | 17.2 KB (259 KB/s) | - |
| 같은 기기 후면 | 15.0 | 2.7% | 17 / 34 ms | - | - |

vision 쪽 측정(vision README): 프레임당 디코드+추론 약 20 ms(CPU 1개), `NUM_HANDS=2`면 약 2배. 15fps(66 ms 간격)에 여유가 크다.
→ **현재 병목 후보는 서버 추론보다 폰 인코딩·Wi-Fi·PC의 다른 부하** 쪽이다.

## 4. 성능 개선 방법

효과가 크고 쉬운 것부터. "범위"가 `mobile`이면 이 폴더만 고치면 되고, 그 외는 팀장·해당 담당과 상의가 필요하다.

| # | 방법 | 기대 효과 | 범위 | 비고 |
|---|---|---|---|---|
| P1 | **`requestVideoFrameCallback`으로 캡처** (지원 안 하면 지금의 `setTimeout` 유지) | 카메라가 새 프레임을 낸 순간에만 캡처 → 같은 프레임 중복 송신·불규칙 간격 제거, `capture_ts`가 실제 촬영 시각(`metadata.captureTime`)에 가까워짐 | mobile | 안드로이드 크롬·사파리 지원. 목표 fps보다 빠르게 오면 건너뛰기만 하면 됨 |
| P2 | **인코딩을 Worker로**: `createImageBitmap(video)` → Worker의 `OffscreenCanvas.convertToBlob` | 메인 스레드(미리보기·UI)가 인코딩에 막히지 않음. 저사양 폰에서 fps 안정 | mobile | 지원 안 하는 브라우저는 지금 방식으로 대체 |
| P3 | **적응형 품질/해상도**: 버린 비율·ack p95를 보고 단계적으로 낮췄다가 좋아지면 되돌림 | 약한 Wi-Fi에서도 끊기지 않음 | mobile (+팀장: 폰이 설정값을 바꿔도 되는지) | PRD 7.3 판단 규칙(버림 5%·p95 150ms, 해상도→fps→품질 순)을 자동화 |
| P4 | **해상도를 낮춰 보내기** (예: 480x360) | 프레임 크기·대역폭·인코딩 시간 감소 | `.env` | vision 측정상 MediaPipe가 내부에서 축소하므로 인식 영향이 작음. 단 손이 작게 찍히는 거리면 정확도 하락 → 7.2 측정표로 확인 |
| P5 | `encodeFrame`에서 JPEG를 `arrayBuffer`로 복사하지 않고 `ws.send(new Blob([헤더, jpegBlob]))` | 프레임당 메모리 복사 1회 감소 | mobile | 효과는 작음(수 KB). 계약 형식은 그대로 |
| P6 | 시연 모드에서 미리보기 끄기(또는 낮은 프레임으로) | 배터리·발열 감소 | mobile | 지금은 40% 크기로 줄이기만 함 |
| P7 | `track.applyConstraints({frameRate: {max: fps}})` | 카메라가 30fps로 돌며 쓰는 전력 감소 | mobile | 일부 기기는 무시함 |
| P8 | gateway→Redis 프레임을 base64 대신 바이너리로 | Redis 메시지 33% 감소, 인코딩/디코딩 비용 감소 | 팀장(계약 변경) | `frames:*`의 `jpeg_base64` 필드 변경이라 전 서비스 영향 |
| P9 | WebCodecs(`VideoEncoder`, H.264)로 영상 스트림 송신 | 대역폭 크게 감소 | 전체(계약·vision 디코더) | 지연·복잡도 증가, 지금 규모에선 비추천 |

**측정 방법**: CSV(M-45)의 `send_fps`·`dropped`·`encode_ms`·`ack_p95_ms`·`battery_pct`를 개선 전/후로 같은 위치·네트워크에서 2분씩 비교한다(PRD 7.2 조합).

## 5. 정확도(손 인식 품질) 개선 방법

폰 쪽에서 할 수 있는 건 결국 **vision에 들어가는 이미지를 좋게 만드는 것**과 **시각 정보를 정확히 넘기는 것**이다.

| # | 방법 | 왜 도움이 되나 | 범위 |
|---|---|---|---|
| A1 | **노출 시간 짧게/연속 초점**: `ImageCapture`·`applyConstraints`로 `focusMode: 'continuous'`, `exposureMode`/`exposureTime` 조절, 지원 시 `frameRate: {min: fps}` | 손을 빨리 움직일 때 모션 블러가 줄어 랜드마크가 덜 튐 | mobile (기기마다 지원 다름 → 지원 여부를 CSV 머리줄에 기록) |
| A2 | **JPEG 품질은 너무 낮추지 않기**(60 이상) | 손가락 경계의 블록 노이즈가 검출 점수를 떨어뜨림. 성능 때문에 낮출 땐 품질보다 해상도·fps를 먼저 | `.env` |
| A3 | **세로/가로 프레임 규칙 정하기**(PRD Q1) | 세로(480x640) 프레임이 오면 gesture의 `ACTIVE_AREA` 매핑·캔버스 비율이 어긋나 커서가 늘어나 보일 수 있음. 폰이 항상 가로로 맞추거나, 하류가 비율을 고려하도록 계약 | 팀장 + gesture |
| A4 | **정확한 `capture_ts`** (P1의 `captureTime`) | gesture의 One Euro 필터는 시간 간격으로 속도를 계산하므로 시각이 정확할수록 떨림 제거·반응성이 좋아짐 | mobile |
| A5 | **화면 안내(가이드)**: 미리보기에 `ACTIVE_AREA`(기본 0.7) 사각형을 그려 손을 그 안에 두게 함 | 손이 화면 가장자리에서 잘리면 검출 실패·좌표 튐 | mobile (`/api/config`의 `active_area` 사용) |
| A6 | **밝기 경고**: 인코딩용 캔버스에서 가끔 평균 밝기를 계산해 너무 어두우면 안내 | 어두우면 MediaPipe 검출 점수가 급락 | mobile |
| A7 | `handedness` 반전 문제 정리 | vision이 원본(반전 안 함)을 넣어서 `Left/Right`가 뒤집힐 수 있음. 폰은 `mirror`를 정확히 보내고 있으니 쓸 때 계약만 정하면 됨 | vision + gesture |
| A8 | One Euro 값 조정(`ONE_EURO_MIN_CUTOFF`, `ONE_EURO_BETA`) | 느리게 그릴 때 떨림 ↔ 빠르게 그릴 때 끌림의 균형. fps를 바꾸면 다시 맞춰야 함 | gesture `.env` |
| A9 | `MIN_*_CONFIDENCE` 조정 | 너무 높으면 손을 자주 놓치고, 낮으면 손 아닌 것을 잡음 | vision `.env` |

**측정 방법**: `tools/record_landmarks.py`로 같은 동작(원 그리기, 직선 긋기)을 녹화해 손 검출률(`hands`가 빈 프레임 비율)과 점 떨림(손을 멈췄을 때 검지 끝 좌표의 표준편차)을 개선 전/후로 비교한다.

## 6. 추천 순서
1. **P1 + A4** (`requestVideoFrameCallback`) — 이 폴더만 고치면 되고 성능·정확도 둘 다에 도움.
2. **A5 활성 영역 가이드** — 시연 때 사용자가 바로 체감.
3. 7.2 측정표를 채운 뒤 필요하면 **P3 적응형 품질**·**P4 해상도** 결정.
4. **A3 세로 프레임 규칙**은 팀장에게 질문(PRD Q1)으로 먼저 확정.
