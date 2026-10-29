# 8. 개발 환경

로컬 개발·테스트·도구 실행은 **conda 환경 `airstroke`** 로, 서비스 실행은 **Docker**로 합니다.

## conda
```powershell
conda env create -f environment.yml                 # 최초 1회
conda env update -f environment.yml --prune         # requirements 변경 후
conda activate airstroke
```
- `environment.yml`은 python과 pip만 conda로 설치하고, 나머지는 각 `requirements.txt`를 `-r`로 불러옵니다. `shared`는 `-e ./shared`(editable)로 설치합니다.
- **VS Code 인터프리터**: `Ctrl+Shift+P` → `Python: Select Interpreter` → `airstroke` 선택. 목록에 없으면 `...\miniforge3\envs\airstroke\python.exe`를 직접 지정합니다.

## 버전 고정
- Python은 **3.11**입니다. Dockerfile은 `python:3.11-slim-bookworm`, conda는 `python=3.11`로 맞춥니다.
- **패키지 버전의 기준은 각 `requirements.txt` 하나뿐입니다.** `environment.yml`에는 버전을 적지 않고, 같은 패키지를 두 파일에 적지 않습니다.

| 파일 | 패키지 (2026-10-29 기준) |
|---|---|
| `shared/requirements.txt` | pydantic 2.14.1, redis 8.1.0 (모든 서비스 공통) |
| `services/gateway/requirements.txt` | fastapi 0.162.0, uvicorn[standard] 0.54.0, segno 1.6.6 |
| `services/vision/requirements.txt` | mediapipe 1.2.0, opencv-contrib-python 5.0.0.93, numpy 2.4.6 |
| `services/gesture/requirements.txt` | (추가 의존성 없음) |
| `requirements-dev.txt` | pytest, ruff, httpx, fakeredis, cryptography, psutil (컨테이너에는 설치하지 않음) |

- 새 패키지는 해당 서비스의 `requirements.txt`에 `==버전`으로 추가하고, PR에 "환경 갱신 필요"를 적습니다.

## OpenCV — `opencv-contrib-python` 하나만
- MediaPipe가 `opencv-contrib-python`에 의존하므로 레포 전체에서 이 패키지 하나만 씁니다.
- **`opencv-python`이나 `opencv-python-headless`를 추가하지 마세요.** 여러 개가 함께 설치되면 `cv2`가 서로 덮어써서 깨집니다. 확인: `pip list | findstr opencv`
- gateway와 gesture에는 OpenCV가 필요 없습니다.

## MediaPipe 1.x 주의
- 예전 `mp.solutions` API는 **없습니다**. `mediapipe.tasks.python.vision.HandLandmarker`만 씁니다.
- import할 때 `sounddevice`를 불러오므로 Linux 이미지에 `libportaudio2`가 필요합니다. OpenCV용으로 `libgl1`, `libglib2.0-0`도 설치합니다.

## Docker
- 모든 Dockerfile은 **레포 루트를 빌드 컨텍스트**로 써서 `shared/`를 함께 복사합니다. CPU 전용 slim 이미지입니다.
- `.env`의 값을 바꿨다면 `docker compose up -d`, 코드를 바꿨다면 `docker compose up -d --build`로 반영합니다.
- compose 안에서는 `REDIS_URL=redis://redis:6379/0`으로 덮어씁니다. `.env`의 `localhost` 값은 로컬 도구용입니다.
- Redis 포트는 `127.0.0.1`에만 열어 둡니다(LAN에 노출하지 않음).
- Docker Desktop(Windows) 컨테이너는 웹캠에 접근할 수 없습니다 → 웹캠 테스트는 로컬 도구로 합니다.

## 서비스 단독 실행 (conda)
```powershell
docker compose up -d redis
docker compose stop vision            # compose의 같은 서비스와 동시에 띄우지 않기
cd services/vision ; python -m vision # gateway, gesture 도 같은 방식
```
- 로컬 실행 시 `.env`를 자동으로 읽지 않고 코드 기본값(`.env.example`과 같음)을 씁니다. 값을 바꾸려면 `$env:NUM_HANDS=2`처럼 지정합니다.

## 개발 도구 (`tools/`)
레포 루트에서 conda 환경으로 실행합니다. 기본 세션 ID는 `dev`입니다(`--session`으로 변경).

| 스크립트 | 용도 |
|---|---|
| `gen_cert.py` | 자체 서명 인증서 + `.env`의 `PUBLIC_HOST`. LAN IP는 후보 목록에서 직접 고릅니다 |
| `stream_frames.py` | 폰 없이 웹캠·영상 파일 → `frames` |
| `record_landmarks.py` | vision 출력 → JSON 녹화 |
| `mock_landmarks.py` | 녹화/fixture JSON → `landmarks` 재생 (gesture 단독 개발) |
| `mock_commands.py` | 가짜 `commands` 시나리오 (그림판 단독 개발) |
| `gen_synthetic_landmarks.py` | `tests/fixtures/landmarks/` 합성 fixture 재생성 |

## 테스트·린트
```powershell
pytest                    # 전체 (루트에서)
pytest services/gesture   # 서비스 하나만
ruff check . ; ruff format .
```
- 서비스 패키지 이름은 `gateway`, `vision`, `gesture`로, 서로 겹치지 않게 했습니다. 그래서 루트에서 `pytest` 한 번으로 전부 실행할 수 있습니다.
- gateway 테스트는 fakeredis를 쓰므로 Redis가 없어도 됩니다.
