# CLAUDE.md — AirStroke

휴대폰 카메라로 찍은 손을 인식해, PC 브라우저 그림판에 손 뼈대를 표시하고 제스처로 그리기·지우기를 원격 제어하는 웹 서비스.
Docker Compose 기반 마이크로서비스. **팀원 5명이 각자 Claude Code로 작업**하므로 아래 담당 영역 규칙을 반드시 지킨다.

---

## 1. 담당 영역 (가장 중요한 규칙)

| 담당 | 영역 | 폴더 |
|---|---|---|
| 김세광 (팀장) | 아키텍처, compose, Redis, 공통 스키마, gateway 백엔드, 통합 | `docker-compose.yml`, `shared/`, `services/gateway/`, `tools/`, 루트 설정 파일 |
| 김정윤 | vision 서비스 | `services/vision/` |
| 이기태 | gesture 서비스 | `services/gesture/` |
| 박민성 | 폰 카메라 페이지, 디바이스·네트워크 테스트, 지연시간·FPS 측정 | `web/mobile/` |
| 조아람 | PC 그림판 UI | `web/canvas/` |

- **자기 담당 폴더 밖은 수정하지 않는다. 특히 `shared/`는 팀장 확인 없이 절대 수정하지 않는다.**
  - Claude Code로 작업할 때: 담당 밖 파일을 고쳐야 할 것 같으면 **수정하지 말고 사용자에게 알리고 멈출 것.**
  - 스키마 변경이 필요하면 팀장에게 요청 (이슈 또는 PR 설명에 제안).
- 담당 밖 변경이 꼭 필요한 PR은 해당 담당자를 리뷰어로 지정한다.
- `tests/fixtures/`: 누구나 fixture **추가**는 가능, 기존 파일 수정·삭제는 팀장 확인.
- 루트 설정(`.env.example`, `environment.yml`, `requirements-dev.txt`, `pyproject.toml`)은 팀장 영역. 새 설정값이 필요하면 PR에 제안.

## 2. 아키텍처

```
 [폰 브라우저 /mobile]                                     [PC 브라우저 /canvas]
   getUserMedia → JPEG                                     캔버스 2겹 + PiP 영상
        │ WebSocket(바이너리)                                    ▲ WebSocket
        ▼                                                       │
   ┌─────────┐  frames:{sid}   ┌────────┐ landmarks:{sid} ┌─────────┐ commands:{sid}
   │ gateway │ ──────────────▶ │ vision │ ──────────────▶ │ gesture │ ───────┐
   │ FastAPI │                 └────────┘        │        └─────────┘        │
   │ HTTPS   │ ◀─────────────────────────────────┴───────────────────────────┘
   └─────────┘      (gateway가 landmarks·commands 구독 → PC로 전달)
          └──────────────── redis (pub/sub) ────────────────┘
```

| 서비스 | 역할 |
|---|---|
| gateway | 세션 생성·QR 페어링, `/mobile`·`/canvas` 정적 서빙(HTTPS, 자체 서명), 폰 프레임 수신 → `frames` publish, `landmarks`·`commands` 구독 → PC로 전달(`frames`는 PC가 PiP를 켰을 때만), 폰·PC 시계 차이 추정 |
| vision | `frames:*` 구독 → MediaPipe Tasks `HandLandmarker`(CPU) → `landmarks` publish. **밀린 프레임은 버리고 최신만 처리** |
| gesture | `landmarks:*` 구독 → 손가락 펴짐 판별(손목 기준 거리 비교) → 제스처 분류 → 디바운스(N프레임) + One Euro Filter → `commands` publish. **프레임을 버리지 않고 순서대로 처리** |
| redis | pub/sub 브로커. 세션 키·하트비트 키도 저장 |

### 확정된 설계 결정
- **전송**: 폰 → gateway는 WebSocket **바이너리**(JPEG 바이트 + 작은 헤더). gateway가 `jpeg_base64` JSON으로 바꿔 Redis에 publish한다. WebRTC는 쓰지 않는다.
- **흐름 제어**: 폰은 응답(ack)을 받지 않은 상태로 **최대 `MAX_INFLIGHT_FRAMES`(=2)장**까지 보낼 수 있다. ack 대기 중인 프레임이 이미 2장이면 새로 찍은 프레임은 **버린다** (큐에 쌓지 않음).
- **시계 동기화**: gateway가 폰·PC와 WebSocket ping/pong을 주고받아 각 기기의 시계 차이(offset)를 추정한다(NTP 방식). 모든 trace 시각은 **gateway 시계**로 환산한다. 2단계에서는 추정까지 구현하고, 전체 지연시간 화면 표시는 3단계에서 붙인다.
- **세션 발견**: vision·gesture는 `PSUBSCRIBE frames:*` / `landmarks:*` 로 세션을 자동으로 찾는다. 세션 정보는 `session:{sid}` 키(TTL `SESSION_TTL_SEC`)에 저장한다.
- **vision**: 세션마다 `HandLandmarker` 인스턴스를 따로 만든다. VIDEO 모드는 타임스탬프가 단조 증가해야 하기 때문이다. `VISION_SESSION_IDLE_SEC` 동안 프레임이 없으면 인스턴스를 해제한다. `num_hands`는 `.env`의 `NUM_HANDS`(기본 1)로 정한다.
  - MediaPipe 1.x에는 예전 `mp.solutions`가 **없다**. `mediapipe.tasks.python.vision.HandLandmarker`만 쓴다.
- **좌표 변환은 gesture가 기준**: 셀카(`mirror=true`)일 때만 x를 반전하고, 카메라 중앙 `ACTIVE_AREA`(70%)를 캔버스 0~1로 매핑한다. PC는 손 뼈대를 그릴 때 같은 변환을 써야 커서와 맞는다. gateway가 `/api/config`로 파라미터를 내려준다(2단계).
- **새 선 시작**: gesture는 draw가 새로 시작될 때마다 `stroke_id`를 증가시킨다. PC는 `stroke_id`가 바뀌면 이전 좌표를 버린다(엉뚱한 직선 방지). 실행 취소(5단계)도 stroke 단위로 한다.
- **헬스체크**: gateway는 `GET /health`를 제공한다(Redis ping + vision·gesture 하트비트). vision·gesture는 Redis 키 `health:{service}`(TTL)를 주기적으로 갱신하고, Docker healthcheck는 `python -m airstroke_shared.health <service>`로 확인한다.

## 3. 메시지 채널 스키마

정의: [shared/airstroke_shared/schemas.py](shared/airstroke_shared/schemas.py). 채널명은 [channels.py](shared/airstroke_shared/channels.py)의 함수로만 만든다.
모든 시각은 **epoch 밀리초(float), gateway 시계 기준**이다. 모르는 필드는 무시(`extra="ignore"`)하므로 필드를 추가해도 기존 코드가 깨지지 않는다.

```jsonc
// frames:{session_id}
{"ts": 0, "seq": 0, "jpeg_base64": "...", "mirror": true, "trace": {...}}

// landmarks:{session_id}  — 좌표는 카메라 원본 기준(반전·매핑 전), x,y ∈ [0,1]
{"ts": 0, "seq": 0, "mirror": true,
 "hands": [{"handedness": "Right", "score": 0.97, "points": [[x,y,z], ... 21개]}],
 "trace": {...}}

// commands:{session_id}  — cursor는 캔버스 기준 0~1 (반전·중앙영역 매핑 완료). 손이 없으면 null
{"ts": 0, "seq": 0, "gesture": "index", "action": "draw",
 "cursor": {"x": 0.4, "y": 0.6}, "stroke_id": 3, "trace": {...}}

// trace — 모든 필드 Optional. 각 서비스는 자기 단계만 채우고 나머지는 그대로 넘긴다
{"capture": null, "gw_recv": null, "vision_done": null, "gesture_done": null}
// PC 표시 시각은 브라우저에서 측정 (메시지에 없음)
```

| gesture | 손 모양 | action |
|---|---|---|
| `index` | 검지만 | `draw` |
| `index_middle` | 검지 + 중지 | `move` (펜 들기) |
| `fist` | 주먹 | `idle` |
| `palm` | 손바닥 | `erase` |
| `unknown` / `none` | 판별 불가 / 손 없음 | `idle` |

## 3-1. 브라우저 ↔ gateway 계약 (2단계, 초안 — 변경은 팀장 확인)

폰 페이지(박민성)와 그림판(조아람)은 이 계약을 기준으로 개발한다. 시각은 모두 epoch ms다.

### HTTP
| 메서드·경로 | 응답 |
|---|---|
| `POST /api/sessions` | `{"session_id", "mobile_url", "qr_url"}` |
| `GET /api/sessions/{sid}/qr.svg` | `mobile_url`을 담은 QR (SVG) |
| `GET /api/config` | `{"camera": {"width","height","fps","jpeg_quality"}, "max_inflight_frames", "active_area"}` |

`mobile_url` = `https://{PUBLIC_HOST 또는 요청 Host}:{포트}/mobile/?s={sid}`

### 폰 WebSocket `wss://…/ws/mobile/{sid}`
- **폰 → gateway (바이너리, 프레임)**: `[4바이트 big-endian 헤더 길이 N][N바이트 UTF-8 JSON 헤더][JPEG 바이트]`
  - 헤더: `{"seq": 12, "capture_ts": <폰 시계>, "mirror": true}`
- **gateway → 폰** `{"type":"ack","seq":12}` — publish를 마친 뒤 보낸다. 폰은 ack를 받지 않은 프레임이 `max_inflight_frames`장이면 새 프레임을 **버린다**.

### PC WebSocket `wss://…/ws/pc/{sid}`
- gateway → PC (텍스트 JSON):
  - `{"type":"landmarks","data":LandmarksMsg}`
  - `{"type":"command","data":CommandMsg}`
  - `{"type":"status","mobile_connected":bool}`
- gateway → PC (바이너리): PiP용 JPEG 바이트. **PiP가 켜진 동안에만** 보낸다.
- PC → gateway: `{"type":"pip","enabled":true|false}` (기본 false)

### 시계 동기화 (폰·PC 공통)
- gateway → 클라이언트 `{"type":"ping","id":n,"t_server":…}` → 클라이언트는 **즉시** `{"type":"pong","id":n,"t_server":…,"t_client":<자기 시계>}`로 답한다.
- gateway는 RTT와 offset(`t_client - (t_server + RTT/2)`)을 추정하고, 여러 번 측정한 값 중 RTT가 가장 작은 쪽을 쓴다. 결과는 `{"type":"clock","offset_ms":…,"rtt_ms":…}`로 클라이언트에 알려준다.
- 클라이언트 시각을 gateway 시계로 바꾸는 식: `gateway_ts = client_ts - offset_ms`. PC 화면 표시 지연(3단계)도 이 식으로 환산한다.

### 그림판 단독 개발
gateway의 PC WebSocket이 생기면 `python tools/mock_commands.py`와 `python tools/mock_landmarks.py --loop`를 `--session <sid>`로 실행해 vision·gesture·폰 없이 UI를 띄울 수 있다.

## 4. 설정 (.env)

- 모든 설정값은 `.env`에 둔다. 템플릿은 [.env.example](.env.example)이고, **`.env`는 커밋하지 않는다.**
- 코드에서는 `airstroke_shared.settings.env_int/env_float/env_str`로 읽는다. 기본값은 `.env.example`과 똑같이 유지한다.
- 새 설정을 추가할 때는 `.env.example`에도 설명과 함께 추가한다(팀장 PR).
- **성능 관련 값**(`CAMERA_WIDTH/HEIGHT/FPS`, `JPEG_QUALITY`, `NUM_HANDS`)은 Zoom 시연 중에 바로 낮출 수 있어야 한다. 하드코딩하지 말 것.
- compose 안의 서비스는 `REDIS_URL=redis://redis:6379/0`으로 덮어쓴다. `.env`의 `localhost` 값은 로컬 도구용이다.

## 5. 개발 환경

### conda (로컬 개발·테스트·도구 실행)
```powershell
conda env create -f environment.yml                 # 최초 1회
conda env update -f environment.yml --prune         # requirements 변경 후
conda activate airstroke
```
- VS Code: `Ctrl+Shift+P` → **Python: Select Interpreter** → `airstroke` 선택 (`...\envs\airstroke\python.exe`).
- `environment.yml`은 python·pip만 conda로 설치하고, 나머지는 `-r <requirements.txt>`로 불러온다. `shared`는 `-e ./shared`(editable)로 설치한다.

### 버전 규칙
- Python **3.11** 고정 (Dockerfile `python:3.11-slim-bookworm` = conda `python=3.11`).
- **패키지 버전의 기준은 각 `requirements.txt` 하나뿐이다.** `environment.yml`에는 버전을 적지 않는다. 같은 패키지를 두 파일에 적지 않는다.
  - `shared/requirements.txt`: pydantic, redis (모든 서비스 공통)
  - `services/<svc>/requirements.txt`: 서비스 전용
  - `requirements-dev.txt`: pytest, ruff, httpx, fakeredis, cryptography, psutil (컨테이너에는 설치하지 않음)
- **새 패키지가 필요하면** 해당 서비스의 `requirements.txt`에 `==버전`으로 추가하고, **PR 설명에 "환경 갱신 필요"**라고 적는다. 리뷰어와 팀원은 머지 후 `conda env update -f environment.yml --prune`을 실행한다.

### OpenCV — `opencv-contrib-python` 하나만
- MediaPipe가 `opencv-contrib-python`에 의존하므로 레포 전체에서 이 패키지 하나만 쓴다(`services/vision/requirements.txt`에 버전 고정).
- **`opencv-python`이나 `opencv-python-headless`를 추가하지 말 것.** 여러 개가 함께 설치되면 `cv2`가 서로 덮어써서 깨진다.
- gateway·gesture에는 OpenCV가 필요 없다. 로컬 도구(`tools/stream_frames.py`)는 conda 환경의 contrib 패키지를 쓴다.
- vision 이미지에는 `libgl1`, `libglib2.0-0`, `libportaudio2`(MediaPipe가 import할 때 sounddevice를 불러옴)를 설치한다.

## 6. 실행

```powershell
copy .env.example .env
python tools/gen_cert.py            # LAN IP 선택 → certs/ 생성 + .env PUBLIC_HOST 반영
docker compose up -d --build
docker compose ps                   # 모두 healthy 인지
curl.exe -k https://localhost:8443/health
docker compose logs -f vision       # JSON 로그
```
- 서비스 단독 실행(conda): Redis만 띄우고(`docker compose up -d redis`) **각 서비스 폴더에서** 실행한다.
  - `cd services/gateway; python -m gateway`처럼 실행한다. vision·gesture도 같은 방식이다.
  - 로컬 실행 시 `.env`는 자동으로 읽지 않으며 코드 기본값(`.env.example`과 같음)을 쓴다. 바꾸려면 `$env:NUM_HANDS=2`처럼 지정한다.
  - 같은 서비스를 compose와 로컬에서 동시에 띄우지 말 것(`docker compose stop vision` 후 로컬 실행).
- 테스트: 레포 루트에서 `pytest`(전체) 또는 `pytest services/gesture`. 린트: `ruff check .`, `ruff format .`

### 독립 개발 도구 (`tools/`, conda에서 실행)
| 스크립트 | 용도 |
|---|---|
| `gen_cert.py` | 자체 서명 인증서 + `PUBLIC_HOST` 설정. IP는 **후보 목록에서 사람이 고른다** (자동 선택 금지) |
| `stream_frames.py` | 폰 없이 웹캠·영상 파일 → `frames` (vision·PC 개발용) |
| `record_landmarks.py` | 실제 vision 출력 → JSON 녹화 |
| `mock_landmarks.py` | 녹화/fixture JSON → `landmarks` 재생 (gesture 단독 개발) |
| `mock_commands.py` | 가짜 `commands` 시나리오 (그림판 UI 단독 개발) |
| `gen_synthetic_landmarks.py` | `tests/fixtures/landmarks/` 합성 fixture 재생성 |

- 기본 세션 ID는 `dev`(`--session`으로 변경).
- Docker Desktop(Windows) 컨테이너는 웹캠에 접근할 수 없으므로 웹캠 도구는 반드시 로컬에서 실행한다.

## 7. 코딩 규칙

- **Python**: 3.11 문법, 타입 힌트 사용, `ruff check` / `ruff format` 통과(line-length 100). 모듈 상단에 docstring으로 역할과 실행 방법을 적는다.
- **메시지**: 반드시 `airstroke_shared.schemas`의 Pydantic 모델로 만들고 검증한다(`model_dump_json` / `model_validate_json`). dict를 직접 조립하지 않는다.
- **채널·키 이름**: `airstroke_shared.channels` 함수만 쓴다.
- **로그**: `airstroke_shared.log.get_logger(<service>)`로 표준 출력에 JSON을 남긴다. `print` 금지(tools 제외). 이벤트명은 snake_case로 하고 값은 `extra={...}`로 넘긴다.
  ```python
  log.info("frame_processed", extra={"session": sid, "infer_ms": 12.3})
  ```
- **trace**: 각 서비스는 자기 단계의 시각(`now_ms()`)만 채우고, 받은 trace의 나머지 필드는 그대로 다음으로 넘긴다.
- **테스트**: 서비스별 `services/<svc>/tests/`. gesture의 판별·디바운스·필터·매핑 로직은 Redis 없이 테스트할 수 있는 순수 함수/클래스(`gesture/core/`)로 만들고 pytest를 작성한다. 공용 샘플 데이터는 `tests/fixtures/`에 둔다.
- **패키지 이름**: 서비스 패키지는 `gateway`, `vision`, `gesture`로, 이름이 서로 겹치지 않게 한다(루트 `pytest` 한 번으로 전부 실행하기 위함).
- **프론트엔드**: 바닐라 JS, 빌드 도구 없이 작성한다. 외부 라이브러리가 필요하면 `web/<영역>/vendor/`에 파일로 넣는다(CDN 의존 금지 — 시연 중 네트워크 문제 방지).
- **줄바꿈**: `.gitattributes`가 `*.sh`, `Dockerfile`, `*.py`, `*.yml`을 LF로 강제한다. Windows 편집기 설정과 무관하게 유지된다.
- **비밀·인증서**: `.env`, `certs/*`는 커밋 금지(.gitignore 처리됨).

## 8. Git / PR 규칙

- 브랜치: `feat/gateway-*`, `feat/vision-*`, `feat/gesture-*`, `feat/mobile-*`, `feat/canvas-*` (공통·인프라는 `feat/gateway-*` 또는 `chore/*`)
- **main 직접 푸시 금지.** 모든 변경은 PR로 올리고 리뷰를 받는다(GitHub 브랜치 보호 규칙으로 강제).
- PR 템플릿: [.github/pull_request_template.md](.github/pull_request_template.md). 담당 영역 밖 수정 여부, "환경 갱신 필요" 여부, 실행·확인 방법을 반드시 적는다.
- 각 서비스 폴더의 `README.md`(역할, 입출력 채널, 단독 실행 방법)는 인터페이스가 바뀌면 함께 갱신한다.

## 9. 시연 환경 (Zoom 화면 공유)

시연은 집에서 하며, Zoom으로 **PC 브라우저 창만** 공유한다. 시청자는 발표자의 손을 볼 수 없다. Zoom이 같은 노트북(Ryzen 7 5700U, 16GB, 내장 그래픽, **CPU 추론**)에서 함께 돌아간다.

그림판 UI 요구사항 (조아람·박민성 참고):
- **기본 시각 요소는 손 뼈대 오버레이**다. 위쪽 캔버스에 21점과 연결선을 매 프레임 그린다. 좌표는 gesture와 같은 변환(반전 + 중앙 `ACTIVE_AREA` 매핑)을 적용한다.
  - **제스처 라벨**: 손 옆(손목 또는 검지 끝 근처)에 현재 상태를 표시한다. `commands.action` 기준:

    | action | 라벨 |
    |---|---|
    | `draw` | ✏️ 그리기 |
    | `move` | ✌️ 이동 |
    | `erase` | ✋ 지우개 |
    | `idle` | ✊ 대기 (손이 없으면 라벨 숨김) |
  - **상태별 표현**:
    - `draw`: **검지 끝(8번)을 강조**한다(크고 진한 점이나 펜 색 링).
    - `move`(펜 든 상태): **뼈대를 흐리게** 그린다(투명도를 낮춤).
    - `erase`: 지우개 범위를 원으로 보여준다.
- **폰 카메라 영상 PiP 패널은 선택 기능이고 기본값은 꺼짐**이다.
  - 켜기/끄기와 위치 변경(모서리 이동 또는 드래그)이 가능해야 한다. 2단계의 "PC에 원본 영상 표시"를 이 패널로 구현한다.
  - **꺼져 있으면 gateway는 영상을 PC로 보내지 않는다.** PC가 `{"type":"pip","enabled":true}`를 보낸 동안에만 `frames`를 전달한다. vision으로 가는 `frames` publish는 PiP와 관계없이 항상 한다.
- **FPS·지연시간 표시**: 화면 공유 화질에서도 읽히도록 **크게** 표시하고 켜고 끌 수 있게 한다.
- **시연 모드 토글**: 커서·손 뼈대·제스처 라벨을 굵고 크게 그린다.
- 성능 값(해상도·fps·`NUM_HANDS`·JPEG 품질)은 `.env`로 조절한다 → `docker compose up -d`로 재기동.

시연 체크리스트와 네트워크 문제 해결 방법은 [README.md](README.md)의 "문제 해결"과 "시연 체크리스트" 섹션을 따른다(핫스팟, IP 변경 시 `gen_cert.py` 재실행, 방화벽 8443, `.wslconfig`).

## 10. 단계별 진행 현황

- [x] 1단계: compose 뼈대, 헬스체크, Redis 연결, shared 스키마, 도구, fixture
- [ ] 2단계: QR 페어링, 폰 → gateway 프레임 스트리밍(최대 2프레임 in-flight), 시계 차이 추정, PC PiP 영상
- [ ] 3단계: vision(MediaPipe) 연동, 손 뼈대 표시, 전체 지연시간 표시
- [ ] 4단계: gesture 연동, 검지로 그리기
- [ ] 5단계: 지우개, 색상 변경, 실행 취소, PNG 저장
