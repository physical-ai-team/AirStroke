# AirStroke

휴대폰 카메라로 손을 찍으면 PC 브라우저 그림판에 손 뼈대(21개 랜드마크)가 표시되고, 손 모양에 따라 그리기·지우기를 원격으로 제어하는 웹 서비스입니다.

```
폰(/mobile) ──WebSocket──▶ gateway ──frames──▶ vision ──landmarks──▶ gesture ──commands──┐
                            ▲  (Redis pub/sub)                                          │
PC(/canvas) ◀──WebSocket────┴────────────────── landmarks · commands ◀──────────────────┘
```

| 서비스 | 담당 | 문서 |
|---|---|---|
| gateway (FastAPI, HTTPS) | 김세광 | [services/gateway/README.md](services/gateway/README.md) |
| redis (pub/sub, 세션·하트비트 키) | 김세광 | [docs/03-protocol.md](docs/03-protocol.md) (채널·키), [docker-compose.yml](docker-compose.yml) |
| 공통 스키마·개발 도구·인프라 (`shared/`, `tools/`, compose) | 김세광 | [docs/02-architecture.md](docs/02-architecture.md), [docs/08-dev-environment.md](docs/08-dev-environment.md) |
| vision (MediaPipe, CPU) | 김정윤 | [services/vision/README.md](services/vision/README.md) |
| gesture (제스처 분류) | 이기태 | [services/gesture/README.md](services/gesture/README.md) |
| 폰 카메라 페이지 | 박민성 | `web/mobile/` |
| PC 그림판 UI | 조아람 | `web/canvas/` |

기획·설계 문서는 **[docs/](docs/README.md)** 에 있습니다(개요, 아키텍처, 프로토콜, 제스처, UI, 로드맵, 팀 규칙, 개발 환경, 시연, 결정 기록).
Claude Code가 따르는 작업 규칙은 [CLAUDE.md](CLAUDE.md)에 있습니다.

---

## 1. 준비물

- Windows + [Docker Desktop](https://www.docker.com/products/docker-desktop/) (WSL2 백엔드)
- [Miniforge](https://github.com/conda-forge/miniforge) 또는 Anaconda (conda)
- VS Code + Python 확장
- 같은 와이파이에 연결된 휴대폰과 PC

## 2. 로컬 개발 환경 (conda)

로컬 개발·테스트·도구 실행은 conda 환경 `airstroke`로 통일하고, 서비스 실행은 Docker로 합니다.

```powershell
# 최초 생성 (레포 루트에서)
conda env create -f environment.yml
conda activate airstroke

# requirements.txt 가 바뀐 PR을 받은 뒤 갱신
conda env update -f environment.yml --prune
```

**VS Code 인터프리터 선택**: `Ctrl+Shift+P` → `Python: Select Interpreter` → `airstroke` 선택.
목록에 없으면 `Enter interpreter path...`에서 `C:\Users\<사용자>\miniforge3\envs\airstroke\python.exe`를 지정합니다.

> 패키지 버전은 각 `requirements.txt` 한 곳에서만 관리합니다. 새 패키지가 필요하면 해당 서비스의 `requirements.txt`에 `==버전`으로 추가하고, PR 설명에 **"환경 갱신 필요"** 라고 적어 주세요.

## 3. 실행

```powershell
copy .env.example .env
python tools/gen_cert.py              # PC의 LAN IP를 목록에서 고르면 certs/ 생성 + .env 의 PUBLIC_HOST 설정
docker compose up -d --build
docker compose ps                     # redis, gateway, vision, gesture 모두 (healthy)
```

- PC 브라우저: `https://localhost:8443/`
- 폰: `https://<PUBLIC_HOST>:8443/mobile/` (2단계부터는 QR로 접속)
- 상태 확인: `curl.exe -k https://localhost:8443/health`
- 로그: `docker compose logs -f gateway vision gesture`
- 설정 변경(.env) 반영: `docker compose up -d` / 코드 변경 반영: `docker compose up -d --build`

### 테스트·린트
```powershell
pytest                    # 전체
pytest services/gesture   # 서비스 하나만
ruff check . ; ruff format .
```

## 4. 독립 개발 도구 (`tools/`)

conda 환경에서 레포 루트 기준으로 실행합니다. Redis가 떠 있어야 합니다(`docker compose up -d redis`). 기본 세션 ID는 `dev`입니다.

| 명령 | 용도 |
|---|---|
| `python tools/stream_frames.py [--source 0 \| 영상.mp4] [--show]` | 폰 없이 웹캠·영상 → `frames` |
| `python tools/record_landmarks.py --duration 10` | vision 출력 → `recordings/*.json` |
| `python tools/mock_landmarks.py [--file ...] [--loop]` | 랜드마크 JSON 재생 → `landmarks` (gesture 단독 개발) |
| `python tools/mock_commands.py` | 가짜 `commands` (그림판 UI 단독 개발) |
| `python tools/gen_synthetic_landmarks.py` | `tests/fixtures/landmarks/` 합성 fixture 재생성 |

Docker Desktop(Windows) 컨테이너에서는 웹캠을 쓸 수 없으므로, 웹캠 테스트는 반드시 로컬에서 `stream_frames.py`로 합니다.

---

## 5. 문제 해결

### 폰에서 PC에 접속이 안 될 때 (와이파이 기기 간 통신 차단)
공유기나 공용 와이파이의 "AP 격리(클라이언트 격리)" 기능 때문에 같은 와이파이에 있어도 기기끼리 통신이 막힐 수 있습니다. 이때는 **폰 핫스팟에 PC를 연결**하세요.
1. 폰에서 **모바일 핫스팟**을 켭니다(설정 → 연결 → 모바일 핫스팟 / iPhone: 설정 → 개인용 핫스팟).
2. PC를 그 핫스팟 와이파이에 연결합니다. 폰 자신은 핫스팟을 통해 PC에 바로 접속할 수 있습니다.
3. IP가 바뀌므로 아래 "IP가 바뀌었을 때" 절차를 따릅니다.
4. 핫스팟 네트워크는 Windows에서 "공용 네트워크"로 잡히는 경우가 많습니다. 아래 방화벽 규칙이 그 프로필에도 적용되는지 확인하세요.

### 네트워크나 IP가 바뀌었을 때 → `gen_cert.py` 재실행
인증서의 SAN과 QR 주소(`PUBLIC_HOST`)에 IP가 들어가 있으므로, 와이파이·핫스팟이 바뀌어 IP가 달라지면 다시 만들어야 합니다.
```powershell
ipconfig                              # 'Wi-Fi' 어댑터의 IPv4 주소 확인
python tools/gen_cert.py              # 목록에서 그 IP 선택 (vEthernet/WSL/Docker/VPN 어댑터는 고르지 말 것)
docker compose up -d                  # restart 말고 up -d (restart는 .env의 PUBLIC_HOST를 다시 읽지 않음)
```
폰에서는 새 인증서의 경고를 **다시 수락**해야 합니다.

### Windows 방화벽 8443 인바운드 허용
**관리자 권한 PowerShell**에서 다음을 실행합니다.
```powershell
New-NetFirewallRule -DisplayName "AirStroke 8443" -Direction Inbound -Protocol TCP -LocalPort 8443 -Action Allow -Profile Private,Public
# 확인 / 삭제
Get-NetFirewallRule -DisplayName "AirStroke 8443"
Remove-NetFirewallRule -DisplayName "AirStroke 8443"
```
GUI로 하려면: `Windows 보안` → `방화벽 및 네트워크 보호` → `고급 설정` → `인바운드 규칙` → `새 규칙` → 포트 → TCP 8443 → 연결 허용.
시연이 끝나면 `Public` 프로필 허용은 지우는 것을 권장합니다.

### 기타
| 증상 | 원인 / 해결 |
|---|---|
| 폰에서 카메라 권한 창이 안 뜸 | HTTPS가 아닙니다. `https://`로 접속했는지, `certs/`가 있는지 확인하세요(gateway 로그에 `cert_missing`이 있으면 인증서 없음) |
| `docker compose ps`에서 vision이 unhealthy | `docker compose logs vision`으로 Redis 연결 오류를 확인하세요 |
| 도구 실행 시 `Redis 연결 실패` | `docker compose up -d redis`를 실행하고, `.env`의 `REDIS_URL`과 `REDIS_HOST_PORT`를 확인하세요 |
| `cv2` import 오류 / 이상 동작 | OpenCV 패키지가 섞였습니다. `pip list \| findstr opencv` 결과가 `opencv-contrib-python` 하나여야 합니다 |
| 줄바꿈 때문에 컨테이너 스크립트 오류 | `.gitattributes`가 LF를 강제합니다. `git add --renormalize .`를 실행하세요 |

---

## 6. 시연 체크리스트 (Zoom 화면 공유)

시연은 Zoom으로 **PC 브라우저 창**을 공유하는 방식입니다. 같은 노트북에서 Zoom과 모든 추론(CPU)이 함께 돌아가므로 성능 여유를 최대한 확보합니다.

**하루 전**
- [ ] 시연 장소의 네트워크에서 폰 → PC 접속을 확인합니다(막히면 핫스팟). IP가 바뀌었으면 `gen_cert.py`를 재실행합니다.
- [ ] **폰에서 인증서 경고를 미리 수락**합니다(`https://<IP>:8443/mobile/` 접속 → 고급 → 계속).
- [ ] **예비용 시연 녹화 영상**을 준비합니다(라이브가 실패할 때 바로 재생할 수 있게 로컬 파일로).
- [ ] WSL 메모리 상한을 설정합니다(아래).

**시연 직전**
- [ ] **전원 어댑터를 연결**합니다(배터리 모드에서는 CPU 클럭이 떨어짐).
- [ ] Windows 전원 모드를 **"최고 성능"** 으로 바꿉니다: `설정` → `시스템` → `전원 및 배터리` → `전원 모드` → **최고 성능**.
- [ ] 불필요한 프로그램(브라우저 탭, 메신저, 동기화 앱)을 종료합니다.
- [ ] `docker compose ps`에서 모두 healthy인지 확인하고, 그림판에서 FPS와 지연시간 표시를 켭니다.
- [ ] Zoom은 **"화면 공유 → 브라우저 창만"** 선택합니다(전체 화면 공유 X — 알림·다른 창이 노출됨).
- [ ] **시연 중 Zoom 웹캠은 끕니다**(CPU 인코딩 부하 감소).
- [ ] 그림판의 **시연 모드**(굵은 커서·뼈대·제스처 라벨)를 켭니다. 시청자는 손을 볼 수 없으므로 손 뼈대 오버레이와 제스처 라벨로 손동작을 보여줍니다.
- [ ] 폰 카메라 **PiP 창은 기본값이 꺼짐**입니다. 실제 손 영상을 보여줄 때만 켜세요. 켜면 PC로 영상이 전송되어 부하가 늘어납니다.
- [ ] 버벅이면 `.env`에서 `CAMERA_FPS=10`, `CAMERA_WIDTH=480`/`CAMERA_HEIGHT=360`, `JPEG_QUALITY=60` 순으로 낮추고 `docker compose up -d`를 실행합니다.

### WSL 메모리 상한 (`.wslconfig`)
Docker Desktop(WSL2)은 기본적으로 메모리를 넉넉히 가져가므로 Zoom과 브라우저 몫을 남겨 둡니다. `%UserProfile%\.wslconfig`(예: `C:\Users\<사용자>\.wslconfig`)를 만들고 다음 내용을 넣습니다.
```ini
[wsl2]
memory=6GB
processors=6
swap=4GB
```
적용: Docker Desktop을 종료한 뒤 PowerShell에서 `wsl --shutdown`을 실행하고 Docker Desktop을 다시 켭니다.
확인: `docker info | findstr "Total Memory"`.

---

## 7. 기여 규칙

- 브랜치: `feat/gateway-*`, `feat/vision-*`, `feat/gesture-*`, `feat/mobile-*`, `feat/canvas-*`
- main에 직접 푸시하지 않습니다. PR 템플릿을 채워 리뷰를 받습니다.
- **자기 담당 폴더 밖, 특히 `shared/`는 팀장 확인 없이 수정하지 않습니다.**
- `.env`와 `certs/`는 커밋하지 않습니다.
