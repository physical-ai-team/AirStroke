# web/mobile — 폰 카메라 페이지 (담당: 박민성)

폰 카메라 영상을 JPEG로 인코딩해 gateway(`/ws/mobile/{sid}`)로 보냅니다. 계약은 [docs/03-protocol.md](../../docs/03-protocol.md), 요구사항은 [docs/05-ui.md](../../docs/05-ui.md)에 있습니다.

| 파일 | 역할 |
|---|---|
| `index.html` | 미리보기, 상태 표시, 시작·전환 버튼 |
| `app.js` | 설정 수신, WebSocket, 캡처·인코딩·흐름 제어, ping/pong, Wake Lock |
| `style.css` | 화면 스타일 |

## 동작
- URL `?s={sid}`로 세션을 받습니다. 세션이 없거나 HTTPS가 아니면 안내 문구를 보여줍니다.
- `GET /api/config`의 `camera.width/height/fps/jpeg_quality`, `max_inflight_frames`를 씁니다(실패하면 2초마다 재시도).
- 인코딩 크기는 카메라 비율을 유지한 채 설정 해상도 안에 맞춥니다(세로 화면이면 480x640처럼 뒤집어 맞춤).
- 프레임 형식: `[4바이트 BE 헤더 길이][JSON 헤더][JPEG]`, 헤더 `{"seq","capture_ts","mirror"}`.
  - `mirror`는 실제 열린 카메라의 `facingMode`가 `user`(전면)일 때만 `true`입니다. 미리보기만 좌우 반전하고, 보내는 프레임은 원본입니다.
  - `seq`는 실제로 보낸 프레임에만 매깁니다. 폰에서 버린 프레임은 "버린 프레임" 수로 따로 셉니다.
- 흐름 제어: ack 전 프레임(인코딩 중 포함)이 `max_inflight_frames`장이면 이번 프레임을 버립니다. 재연결하면 대기 목록을 비웁니다.
- 연결이 끊기면 0.5초부터 최대 5초까지 늘려 가며 재연결합니다.

## 화면 표시 (디바이스·네트워크 테스트용)
연결 상태, 카메라(전면/후면, 실제 해상도·fps), 송신 fps, 보낸/버린 프레임, ack 대기 수, ack 왕복 평균(최근 30개), 시계 차이/RTT(gateway `clock` 메시지), 화면 꺼짐 방지 상태.

## 확인 방법
1. `docker compose up -d --build` 후 PC에서 `https://<LAN-IP>:8443/canvas/` → QR을 폰으로 스캔
2. 또는 폰에서 직접 `https://<LAN-IP>:8443/mobile/?s=dev`
3. "카메라 시작" → 상태가 "연결됨", 송신 fps가 설정값(기본 15) 근처인지, 전면/후면 전환이 되는지 확인
