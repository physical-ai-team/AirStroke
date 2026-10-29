# 3. 프로토콜

- **기준 코드**: [shared/airstroke_shared/schemas.py](../shared/airstroke_shared/schemas.py), [channels.py](../shared/airstroke_shared/channels.py). 이 문서와 코드가 다르면 코드가 맞습니다(그리고 문서를 고쳐 주세요).
- 시각은 모두 **epoch 밀리초(float), gateway 시계 기준**입니다.
- 모르는 필드는 무시합니다(`extra="ignore"`). 그래서 필드를 추가해도 기존 서비스가 깨지지 않습니다. 필드 삭제나 이름 변경은 모든 서비스에 영향을 주므로 팀장 확인이 필요합니다.

## Redis 채널

### `frames:{session_id}` — gateway → vision (+ PiP용으로 gateway 자신)
```jsonc
{"ts": 0, "seq": 0, "jpeg_base64": "...", "mirror": true, "trace": {...}}
```
- `mirror`: 전면(셀카) 카메라면 `true`입니다. gesture가 이 값을 보고 x좌표를 반전합니다.

### `landmarks:{session_id}` — vision → gesture, gateway(PC 전달)
```jsonc
{"ts": 0, "seq": 0, "mirror": true,
 "hands": [{"handedness": "Right", "score": 0.97, "points": [[x, y, z], ... 21개]}],
 "trace": {...}}
```
- 좌표는 **카메라 원본 기준**(반전·매핑 전)이고 x, y ∈ [0, 1]입니다. 손이 없으면 `hands: []`입니다.
- 점 순서는 MediaPipe 기준입니다: 0 손목, 1-4 엄지, 5-8 검지, 9-12 중지, 13-16 약지, 17-20 소지.

### `commands:{session_id}` — gesture → gateway(PC 전달)
```jsonc
{"ts": 0, "seq": 0, "gesture": "index", "action": "draw",
 "cursor": {"x": 0.4, "y": 0.6}, "stroke_id": 3, "trace": {...}}
```
- `gesture`: `index` | `index_middle` | `fist` | `palm` | `unknown` | `none`
- `action`: `draw` | `move` | `idle` | `erase`
- `cursor`: **캔버스 기준** 0~1입니다(반전·중앙영역 매핑 완료). 손이 없으면 `null`입니다.
- `stroke_id`: draw가 새로 시작될 때마다 증가합니다. draw가 아니면 `null`입니다. PC는 값이 바뀌면 이전 좌표를 버리고 새 선을 시작합니다.

### `trace` (모든 메시지 공통, 모든 필드 Optional)
```jsonc
{"capture": null, "gw_recv": null, "vision_done": null, "gesture_done": null}
```
각 서비스는 **자기 단계만 채우고** 나머지는 받은 그대로 넘깁니다.

### `seq`
- 세션별 프레임 번호입니다. 폰이 매기며 이후 단계는 그대로 이어받습니다.
- ack 처리와 프레임 버림 통계에 씁니다.

## Redis 키
| 키 | 값 | TTL |
|---|---|---|
| `session:{sid}` | 세션 정보(생성 시각 등, 2단계에서 확정) | `SESSION_TTL_SEC` |
| `health:{service}` | `{"ts", ...통계}` | 하트비트 주기 × 3 |

---

## 브라우저 ↔ gateway 계약 (2단계, 초안)

폰 페이지와 그림판은 이 계약을 기준으로 개발합니다. 바꾸려면 팀장 확인이 필요합니다.

### HTTP
| 메서드·경로 | 응답 |
|---|---|
| `GET /health` | `{"status", "redis", "services": {...}}` (1단계 구현 완료) |
| `POST /api/sessions` | `{"session_id", "mobile_url", "qr_url"}` |
| `GET /api/sessions/{sid}/qr.svg` | `mobile_url`을 담은 QR (SVG, 서버에서 생성) |
| `GET /api/config` | `{"camera": {"width","height","fps","jpeg_quality"}, "max_inflight_frames", "active_area"}` |

- `mobile_url` = `https://{PUBLIC_HOST 또는 요청 Host}:{포트}/mobile/?s={sid}`
- PC가 `https://<LAN-IP>:8443`으로 접속했다면 요청 Host를 그대로 쓰고, `localhost`로 접속했다면 `PUBLIC_HOST`를 씁니다.

### 폰 WebSocket — `wss://…/ws/mobile/{sid}`
- **폰 → gateway (바이너리 메시지, 프레임 1장)**
  ```
  [4바이트 big-endian 헤더 길이 N][N바이트 UTF-8 JSON 헤더][JPEG 바이트]
  ```
  헤더: `{"seq": 12, "capture_ts": <폰 시계 ms>, "mirror": true}`
- **gateway → 폰**: `{"type":"ack","seq":12}`. Redis publish를 마친 뒤 보냅니다.
  - 폰은 ack를 받지 않은 프레임이 `max_inflight_frames`장이면 새 프레임을 버립니다.

### PC WebSocket — `wss://…/ws/pc/{sid}`
- **gateway → PC (텍스트 JSON)**
  - `{"type":"landmarks","data":<LandmarksMsg>}`
  - `{"type":"command","data":<CommandMsg>}`
  - `{"type":"status","mobile_connected":true|false}`
- **gateway → PC (바이너리)**: PiP용 JPEG 바이트입니다. **PiP가 켜진 동안에만** 보냅니다.
- **PC → gateway**: `{"type":"pip","enabled":true|false}`. 연결 직후의 기본값은 `false`입니다.

### 시계 동기화 (폰·PC 공통)
1. gateway → 클라이언트: `{"type":"ping","id":n,"t_server":<gateway ms>}`
2. 클라이언트는 **즉시** `{"type":"pong","id":n,"t_server":<받은 값>,"t_client":<자기 시계 ms>}`로 답합니다.
3. gateway는 pong 도착 시각으로 `RTT = now - t_server`, `offset = t_client - (t_server + RTT/2)`를 계산합니다. 최근 여러 번의 측정 중 **RTT가 가장 작은 값**을 씁니다.
4. gateway → 클라이언트: `{"type":"clock","offset_ms":…,"rtt_ms":…}`
5. 클라이언트 시각을 gateway 시계로 바꾸는 식: `gateway_ts = client_ts - offset_ms`

### 그림판 단독 개발
gateway의 PC WebSocket이 생기면 다음 두 도구를 같은 세션으로 실행해 vision·gesture·폰 없이 UI를 띄울 수 있습니다.
```powershell
python tools/mock_commands.py --session <sid>
python tools/mock_landmarks.py --session <sid> --loop
```
