# CLAUDE.md — AirStroke

휴대폰 카메라로 찍은 손을 인식해, PC 브라우저 그림판에 손 뼈대를 표시하고 제스처로 그리기·지우기를 원격 제어하는 웹 서비스다. Docker Compose 기반 마이크로서비스(gateway · vision · gesture · redis)로 되어 있다.
**팀원 5명이 각자 Claude Code로 작업**하므로 이 파일의 규칙을 반드시 지킨다. 자세한 기획과 설계는 [docs/](docs/README.md)에 있다.

## 0. 문서 지도 — 작업 전에 해당 문서를 읽을 것

| 작업 | 먼저 읽을 문서 |
|---|---|
| 처음 / 전체 파악 | [docs/01-overview.md](docs/01-overview.md), [docs/02-architecture.md](docs/02-architecture.md) |
| 메시지·채널·WebSocket을 다룰 때 | [docs/03-protocol.md](docs/03-protocol.md) + [shared/airstroke_shared/schemas.py](shared/airstroke_shared/schemas.py) |
| gesture 로직 / 커서·뼈대 좌표 | [docs/04-gestures.md](docs/04-gestures.md) |
| 그림판·폰 페이지 UI | [docs/05-ui.md](docs/05-ui.md) |
| 지금 몇 단계인지, 다음 할 일 | [docs/06-roadmap.md](docs/06-roadmap.md) |
| 환경·버전·도구 | [docs/08-dev-environment.md](docs/08-dev-environment.md) |
| 왜 이렇게 설계했는지 | [docs/decisions.md](docs/decisions.md) |

## 1. 담당 영역 (가장 중요한 규칙)

| 담당 | 영역 | 폴더 |
|---|---|---|
| 김세광 (팀장) | 아키텍처, compose, Redis, 공통 스키마, gateway 백엔드, 통합, 문서 | `docker-compose.yml`, `shared/`, `services/gateway/`, `tools/`, `docs/`, 루트 설정 파일 |
| 김정윤 | vision 서비스 | `services/vision/` |
| 이기태 | gesture 서비스 | `services/gesture/` |
| 박민성 | 폰 카메라 페이지, 디바이스·네트워크 테스트, 지연시간·FPS 측정 | `web/mobile/` |
| 조아람 | PC 그림판 UI | `web/canvas/` |

- **자기 담당 폴더 밖은 수정하지 않는다. 특히 `shared/`는 팀장 확인 없이 절대 수정하지 않는다.**
  - 담당 밖 파일을 고쳐야 할 것 같으면 **수정하지 말고 사용자에게 알리고 멈춘다.** 어느 파일을 왜 고쳐야 하는지 설명한다.
  - 스키마나 계약([docs/03-protocol.md](docs/03-protocol.md)) 변경은 팀장에게 제안한다.
- `tests/fixtures/`: 추가는 누구나 할 수 있다. 기존 파일 수정과 삭제는 팀장 확인을 받는다.
- 루트 설정(`.env.example`, `environment.yml`, `requirements-dev.txt`, `pyproject.toml`)과 `docs/`는 팀장 영역이다.
- 큰 설계 결정(새 프로토콜, 새 서비스, 라이브러리 교체 등)은 임의로 정하지 말고 **선택지를 제시한다.** 확정되면 [docs/decisions.md](docs/decisions.md)에 기록한다.
- 상세: [docs/07-team.md](docs/07-team.md)

## 2. 반드시 지킬 설계 제약 (요약)

자세한 내용과 이유는 [docs/02-architecture.md](docs/02-architecture.md), [docs/decisions.md](docs/decisions.md)에 있다.

- 서비스끼리는 **Redis pub/sub으로만** 통신한다. 채널은 `frames:{sid}` → `landmarks:{sid}` → `commands:{sid}`이다.
- **모든 시각은 epoch ms, gateway 시계 기준**이다. 각 서비스는 `trace`에서 자기 단계만 채우고 나머지는 그대로 넘긴다.
- 폰 → gateway는 WebSocket 바이너리로 보낸다. 응답 대기 중인 프레임은 **최대 `MAX_INFLIGHT_FRAMES`(2)장**이고, 넘치면 새 프레임은 버린다.
- **vision**: 밀린 프레임은 버리고 최신만 처리한다. **세션별 `HandLandmarker`**(VIDEO 모드), `NUM_HANDS`는 `.env`(기본 1). MediaPipe 1.x에는 `mp.solutions`가 **없다** → Tasks API만 쓴다.
- **gesture**: 메시지를 버리지 않고 순서대로 처리하며, 상태는 세션별로 둔다. 좌표 변환(셀카일 때만 x 반전 + 중앙 `ACTIVE_AREA` 매핑)의 **기준은 gesture**다. `landmarks`는 원본 좌표로 둔다.
- **새 선**: draw가 시작될 때마다 `stroke_id`가 증가한다. PC는 값이 바뀌면 이전 좌표를 버린다.
- **그림판**: 기본 시각 요소는 **손 뼈대 오버레이 + 제스처 라벨**이다. **PiP 영상은 기본 꺼짐**이고, 꺼져 있으면 gateway가 PC로 영상을 보내지 않는다.
- 설정값(포트, 해상도, fps, JPEG 품질, `NUM_HANDS`, 디바운스 등)은 **전부 `.env`** 로 둔다. 하드코딩하지 않는다. 새 키는 `.env.example`에 설명과 함께 추가한다(팀장 PR).

## 3. 개발 명령

```powershell
conda env create -f environment.yml       # 최초 (환경 이름: airstroke)
conda env update -f environment.yml --prune   # requirements 변경 후
conda activate airstroke                  # VS Code: Python: Select Interpreter → airstroke

copy .env.example .env
python tools/gen_cert.py                  # LAN IP 선택 → certs/ + PUBLIC_HOST
docker compose up -d --build ; docker compose ps
curl.exe -k https://localhost:8443/health

pytest                                    # 레포 루트에서 전체 / pytest services/gesture
ruff check . ; ruff format .
```
- 서비스 단독 실행: `docker compose up -d redis`, `docker compose stop <svc>`를 한 뒤 `cd services/<svc>; python -m <svc>`로 실행한다.
- 독립 개발 도구: `tools/mock_landmarks.py`(gesture용), `tools/mock_commands.py`(그림판용), `tools/stream_frames.py`(폰 없이 웹캠), `tools/record_landmarks.py`(녹화). 기본 세션은 `dev`.
- 상세: [docs/08-dev-environment.md](docs/08-dev-environment.md)

## 4. 버전·환경 규칙

- Python **3.11** 고정 (Docker `python:3.11-slim-bookworm` = conda `python=3.11`).
- **패키지 버전의 기준은 각 `requirements.txt` 하나뿐이다.** `environment.yml`에는 버전을 적지 않는다. 같은 패키지를 두 파일에 적지 않는다(pydantic·redis는 `shared/requirements.txt`).
- **새 패키지가 필요하면** 해당 서비스의 `requirements.txt`에 `==버전`으로 추가하고, **PR 설명에 "환경 갱신 필요"**라고 적는다.
- **OpenCV는 `opencv-contrib-python` 하나만 쓴다**(MediaPipe 의존성). `opencv-python`이나 `opencv-python-headless`를 추가하지 말 것 — `cv2`가 충돌한다.
- Dockerfile은 CPU 전용 slim 이미지를 쓰고, 빌드 컨텍스트는 레포 루트다(`shared/`를 복사하기 위함).

## 5. 코딩 규칙

- **Python**: 3.11 문법, 타입 힌트 사용, `ruff check`/`ruff format` 통과(line-length 100). 모듈 상단 docstring에 역할과 실행 방법을 적는다.
- **메시지**: 반드시 `airstroke_shared.schemas`의 Pydantic 모델로 만들고 검증한다. dict를 직접 조립하지 않는다.
- **채널·키 이름**: `airstroke_shared.channels` 함수만 쓴다.
- **설정**: `airstroke_shared.settings.env_int/env_float/env_str`로 읽고, 기본값은 `.env.example`과 똑같이 유지한다.
- **로그**: `airstroke_shared.log.get_logger(<service>)`로 표준 출력에 JSON을 남긴다. `print` 금지(tools 제외). 이벤트명은 snake_case로 하고 값은 `extra={...}`로 넘긴다.
  ```python
  log.info("frame_processed", extra={"session": sid, "infer_ms": 12.3})
  ```
- **테스트**: `services/<svc>/tests/`에 둔다. gesture 로직은 Redis 없이 테스트할 수 있는 순수 코드(`gesture/core/`)로 만들고 pytest를 작성한다. 공용 샘플 데이터는 `tests/fixtures/`에 있다.
- **프론트엔드**: 바닐라 JS, 빌드 도구 없음. 외부 라이브러리는 `web/<영역>/vendor/`에 파일로 넣는다(CDN 금지).
- **줄바꿈**: `.gitattributes`가 `*.sh`, `Dockerfile`, `*.py`, `*.yml`을 LF로 강제한다.
- **비밀**: `.env`, `certs/*`는 커밋 금지.

## 6. Git / PR / 문서

- 브랜치: `feat/gateway-*`, `feat/vision-*`, `feat/gesture-*`, `feat/mobile-*`, `feat/canvas-*`. **main에 직접 푸시하지 않는다.**
- **PR 제목과 커밋 메시지는 `<type>(<scope>): <설명>` 형식**이다(Conventional Commits). 설명은 한국어로 쓴다.
  - type: `feat`(기능) · `fix`(버그) · `docs`(문서) · `refactor` · `test` · `perf` · `chore`(설정·의존성·빌드) · `ci`
  - scope: `gateway` · `vision` · `gesture` · `mobile` · `canvas` · `shared` · `tools` · `infra` (여러 영역이면 생략 가능)
  - 예: `feat(gesture): 검지 펴짐 판별과 디바운스 추가`, `fix(canvas): stroke_id 변경 시 직선 생기는 문제 수정`
  - main에는 **Squash and merge**로 합친다. PR 제목이 그대로 main의 커밋 메시지가 된다.
- PR은 [.github/pull_request_template.md](.github/pull_request_template.md)를 채운다. 담당 밖 변경 여부, "환경 갱신 필요" 여부, 실행·확인 방법을 반드시 적는다.
- 인터페이스(채널·스키마·설정·WebSocket 계약)가 바뀌면 서비스 README와 해당 `docs/` 문서도 함께 갱신한다(docs 수정은 팀장 리뷰).
- 단계를 마치면 [docs/06-roadmap.md](docs/06-roadmap.md)의 진행 현황을 갱신한다.
- 시연 준비와 문제 해결(핫스팟, IP가 바뀌면 `gen_cert.py` 재실행, 방화벽 8443, `.wslconfig`)은 [README.md](README.md)와 [docs/09-demo.md](docs/09-demo.md)에 있다.
