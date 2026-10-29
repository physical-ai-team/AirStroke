# 3. 프로토콜

- **기준 코드**: [shared/airstroke_shared/schemas.py](../shared/airstroke_shared/schemas.py), [channels.py](../shared/airstroke_shared/channels.py). 이 문서와 코드가 다르면 코드가 맞습니다(그리고 문서를 고쳐 주세요).
- 시각은 모두 **epoch 밀리초(float), gateway 시계 기준**입니다.
- 모르는 필드는 무시합니다(`extra="ignore"`). 그래서 필드를 추가해도 기존 서비스가 깨지지 않습니다. 필드 삭제나 이름 변경은 모든 서비스에 영향을 주므로 팀장 확인이 필요합니다.

## Redis 채널

### `frames:{session_id}` — gateway → vision (+ PiP용으로 gateway 자신)
```jsonc
{"ts": 0, "seq": 0, "jpeg_base64": "...", "mirror": true, "width": 640, "height": 480, "trace": {...}}
```
- `mirror`: 전면(셀카) 카메라면 `true`입니다. gesture가 이 값을 보고 x좌표를 반전합니다.
- `width`, `height`: JPEG 크기(px)입니다. gateway가 JPEG 헤더에서 읽어 채웁니다. 폰을 세로로 들면 `width < height`입니다(세로 허용, D-018). 읽지 못하면 `null`이고, 이때는 `CAMERA_WIDTH:CAMERA_HEIGHT` 비율로 간주합니다.

### `landmarks:{session_id}` — vision → gesture, gateway(PC 전달)
```jsonc
{"ts": 0, "seq": 0, "mirror": true, "width": 640, "height": 480,
 "hands": [{"handedness": "Right", "score": 0.97, "points": [[x, y, z], ... 21개]}],
 "trace": {...}}
```
- 좌표는 **카메라 원본 기준**(반전·매핑 전)이고 x, y ∈ [0, 1]입니다. 손이 없으면 `hands: []`입니다.
- `width`, `height`: vision이 `frames` 값을 그대로 옮깁니다. 정규화 좌표를 px로 바꾸거나 화면 비율을 맞출 때 씁니다.
- 점 순서는 MediaPipe 기준입니다: 0 손목, 1-4 엄지, 5-8 검지, 9-12 중지, 13-16 약지, 17-20 소지.

### `commands:{session_id}` — gesture → gateway(PC 전달)
```jsonc
{"ts": 0, "seq": 0, "gesture": "index", "action": "draw",
 "cursor": {"x": 0.4, "y": 0.6}, "stroke_id": 3, "trace": {...}}
```
- `gesture`: `index` | `index_middle` | `fist` | `palm` | `pinch` | `thumb_up` | `unknown` | `none`
- `action`: `draw` | `move` | `idle` | `erase` | `select` | `undo`
  - `select`(`pinch`): 집고 있는 동안 매 프레임. 그림판은 시작 위치에 팔레트를 띄우고, `select`가 끝나는 순간 커서 방향의 색을 적용합니다.
  - `undo`(`thumb_up`): **확정되는 순간 한 번만** 옵니다. 계속 엄지를 들고 있으면 `gesture="thumb_up"`, `action="idle"`입니다.
- `cursor`: **캔버스 기준** 0~1입니다(반전·중앙영역 매핑 완료). 손이 없으면 `null`입니다. `pinch` 중에는 엄지·검지 끝의 가운데입니다.
- `stroke_id`: draw가 새로 시작될 때마다 증가합니다. draw가 아니면 `null`입니다. PC는 값이 바뀌면 이전 좌표를 버리고 새 선을 시작합니다.

### `trace` (모든 메시지 공통, 모든 필드 Optional)
```jsonc
{"capture": null, "gw_recv": null, "vision_done": null, "gesture_done": null}
```
각 서비스는 **자기 단계만 채우고** 나머지는 받은 그대로 넘깁니다.

### `seq`
- 세션별 프레임 번호입니다. 폰이 매기며 이후 단계는 그대로 이어받습니다.
- ack 처리와 프레임 버림 통계에 씁니다.
- 폰은 **실제로 보낸 프레임에만** 번호를 매깁니다. 흐름 제어로 버린 프레임은 번호를 쓰지 않으므로, 폰에서 버린 수는 `seq` 공백이 아니라 폰 페이지의 통계로 셉니다. `seq` 공백은 gateway 이후(vision의 최신 프레임 정책 등)에서 버려진 것입니다.
- 재접속하면 `seq`가 다시 0부터 시작할 수 있습니다.

## Redis 키
| 키 | 값 | TTL |
|---|---|---|
| `session:{sid}` | `{"created": <ms>}`. WebSocket이 연결된 동안 ping 주기마다 TTL을 연장 | `SESSION_TTL_SEC` |
| `health:{service}` | `{"ts", ...통계}` | 하트비트 주기 × 3 |

---

## 브라우저 ↔ gateway 계약 (2단계)

폰 페이지와 그림판은 이 계약을 기준으로 개발합니다. 바꾸려면 팀장 확인이 필요합니다. gateway 구현: [protocol.py](../services/gateway/gateway/protocol.py), [ws.py](../services/gateway/gateway/ws.py). 브라우저 없이 확인하려면 `python tools/ws_client.py`를 실행합니다.

### HTTP
| 메서드·경로 | 응답 |
|---|---|
| `GET /health` | `{"status", "redis", "services": {...}}` (1단계 구현 완료) |
| `POST /api/sessions` | `{"session_id", "mobile_url", "qr_url"}` (`qr_url`은 `/api/sessions/{sid}/qr.svg` 같은 상대 경로) |
| `GET /api/sessions/{sid}/qr.svg` | `mobile_url`을 담은 QR (SVG, 서버에서 생성). 모르는 세션이면 404 |
| `GET /api/config` | `{"camera": {"width","height","fps","jpeg_quality"}, "max_inflight_frames", "active_area"}` |

- `mobile_url` = `{요청 스킴}://{PUBLIC_HOST 또는 요청 Host}:{요청 Host의 포트}/mobile/?s={sid}`
- PC가 `https://<LAN-IP>:8443`으로 접속했다면 요청 Host를 그대로 쓰고, `localhost`(`127.0.0.1`, `::1`)로 접속했다면 hostname만 `PUBLIC_HOST`로 바꿉니다. 포트는 요청 Host의 포트를 씁니다(컨테이너 안에서는 호스트 쪽 포트를 알 수 없음).
- `PUBLIC_HOST`가 비어 있으면 요청 Host를 그대로 쓰고 `public_host_missing` 경고 로그를 남깁니다.

### WebSocket 공통
- 세션 확인: `POST /api/sessions`로 만들지 않았거나 TTL이 만료된 세션이면 연결을 수락한 직후 **close 4404**로 닫습니다.
- 접속 직후부터 `CLOCK_PING_INTERVAL_SEC`(기본 2초)마다 gateway가 ping을 보냅니다(아래 "시계 동기화").
- 모르는 `type`이나 형식이 틀린 텍스트 메시지는 무시합니다.

### 폰 WebSocket — `wss://…/ws/mobile/{sid}`
- **폰 → gateway (바이너리 메시지, 프레임 1장)**
  ```
  [4바이트 big-endian 헤더 길이 N][N바이트 UTF-8 JSON 헤더][JPEG 바이트]
  ```
  헤더: `{"seq": 12, "capture_ts": <폰 시계 ms>, "mirror": true}`
  - 프레임은 가로·세로 모두 됩니다. 폰은 영상 비율을 유지해 보내고, gateway가 JPEG에서 크기를 읽어 `frames`의 `width`·`height`에 넣습니다.
  - gateway는 `trace.capture = capture_ts - offset_ms`로 환산합니다. **첫 시계 추정(첫 pong) 전에는 `trace.capture = null`** 입니다. `ts`와 `trace.gw_recv`는 gateway 수신 시각입니다.
  - 형식이 틀린 프레임(헤더 길이·JSON·`seq` 누락, JPEG가 아님)은 경고 로그만 남기고 버리며 **ack도 보내지 않습니다.**
- **gateway → 폰**: `{"type":"ack","seq":12}`. Redis publish를 마친 뒤 보냅니다.
  - 폰은 ack를 받지 않은 프레임이 `max_inflight_frames`장이면 새 프레임을 버립니다.
- 같은 세션에 폰이 새로 접속하면 **새 연결이 이깁니다.** 기존 폰 연결은 **close 4409**로 닫히고, PC의 `mobile_connected`는 `true`로 유지됩니다. 4409를 받은 폰 페이지는 자동 재접속하지 않는 것이 좋습니다(두 폰이 서로 밀어내는 것을 방지).

### PC WebSocket — `wss://…/ws/pc/{sid}`
- **gateway → PC (텍스트 JSON)**
  - `{"type":"landmarks","data":<LandmarksMsg>}`
  - `{"type":"command","data":<CommandMsg>}`
  - `{"type":"status","mobile_connected":true|false}` — 연결 직후 1번, 이후 폰이 붙거나 떨어질 때마다
- **gateway → PC (바이너리)**: PiP 영상 1프레임입니다. **PiP가 켜진 동안에만** 보냅니다. 폰 프레임과 같은 형식입니다(D-015).
  ```
  [4바이트 big-endian 헤더 길이 N][N바이트 UTF-8 JSON 헤더][JPEG 바이트]
  ```
  헤더: `{"ts": …, "seq": 12, "mirror": true, "trace": {...}}`. `mirror=true`면 좌우를 반전해서 보여줍니다.
  ```js
  const n = new DataView(buf).getUint32(0);            // big-endian
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, n)));
  const jpeg = new Blob([new Uint8Array(buf, 4 + n)], {type: "image/jpeg"});
  ```
- **PC → gateway**: `{"type":"pip","enabled":true|false}`. 연결 직후의 기본값은 `false`입니다. 꺼지면 gateway는 `frames` 구독 자체를 해제합니다.
- 같은 세션에 PC가 여러 개 붙을 수 있고, PiP 상태는 PC 연결마다 따로 둡니다.

### 시계 동기화 (폰·PC 공통)
1. gateway → 클라이언트: `{"type":"ping","id":n,"t_server":<gateway ms>}`
2. 클라이언트는 **즉시** `{"type":"pong","id":n,"t_server":<받은 값>,"t_client":<자기 시계 ms>}`로 답합니다.
3. gateway는 pong 도착 시각으로 `RTT = now - t_server`, `offset = t_client - (t_server + RTT/2)`를 계산합니다. `t_server`는 pong에 실려 온 값이 아니라 gateway가 `id`별로 기록해 둔 값을 씁니다. 최근 `CLOCK_SAMPLES`(기본 10)번의 측정 중 **RTT가 가장 작은 값**을 씁니다.
4. gateway → 클라이언트: `{"type":"clock","offset_ms":…,"rtt_ms":…}` — pong을 받을 때마다 현재 최선값을 보냅니다.
5. 클라이언트 시각을 gateway 시계로 바꾸는 식: `gateway_ts = client_ts - offset_ms`

### close 코드
| 코드 | 의미 |
|---|---|
| 4404 | 모르는(또는 만료된) 세션 |
| 4409 | 같은 세션에 새 폰이 접속해 기존 폰 연결이 밀려남 |

### 그림판 단독 개발
`POST /api/sessions`로 세션을 만든 뒤(그림판이 QR을 띄울 때 만든 세션), 그 ID로 다음 두 도구를 실행하면 vision·gesture·폰 없이 UI를 띄울 수 있습니다.
```powershell
python tools/mock_commands.py --session <sid>
python tools/mock_landmarks.py --session <sid> --loop
python tools/ws_client.py mobile --session <sid> --seconds 60   # PiP 확인용 합성 영상
```
