# HANDOFF — 폰 카메라 페이지 (박민성 담당, `web/mobile/`)

다른 PC에서 이어받을 때 **"남은 일" 절만 먼저** 읽는다. 기능 목록·측정 계획은 [PRD.md](PRD.md), 팀 규칙은 저장소 루트 `CLAUDE.md`.
(`docs/`와 루트 설정은 팀장 영역이라 내 기록은 이 폴더 안에만 둔다.)

## 현재 상태 (2026-10-29)
- **PR #8로 main 병합됨 (2026-10-29, `57a8ff1`)**. 이후 작업도 `feat/mobile-camera`에서 하고 PR로 올린다.
- 구현됨: 카메라 시작/전환, `/api/config` 수신, 바이너리 프레임 송신, 흐름 제어(inflight 2), ping→pong, clock 표시, Wake Lock, 재연결(0.5→5초), close 4404/4409 처리, 상태 패널.
- 확인한 것: main 병합 후 `pytest` 57개·`ruff` 통과. 진짜 gateway 코드(fakeredis)에 `app.js`를 붙인 Node 하네스로 15fps·ack 1ms·4404·4409 확인.
- 2026-10-29 오후(두 번째 PC) 추가: M-13 오류별 안내, M-14 카메라 방향 기억, M-25 ack 3초 타임아웃, M-26 백그라운드 일시정지·재개, M-42~44 프레임 크기·대역폭·인코딩 시간·ack p50/p95, **M-45 측정 CSV 저장**. Q3 해결(gateway는 publish 오류 시 연결을 닫음).
  - 확인: headless Chrome(가짜 카메라) + 진짜 gateway(fakeredis)로 15fps, ack p50/p95 1/3ms, 7KB·105KB/s, 인코딩 8ms, 백그라운드 때 송신 0 → 복귀 시 재개, 새로고침 후 후면 유지, CSV 저장까지 확인. `ruff` 통과.
  - `services/gateway/tests/test_ws.py::test_pip_frames_only_while_enabled`가 가끔 실패하거나 멈춘다 — **원래 main 코드에서도** 멈춤을 확인(팀장 영역, 내 변경은 JS·문서뿐). 팀장에게 알릴 것.
- **실제 폰 시험 1차 (2026-10-29, Galaxy, 학교 Wi-Fi)**: 연결·전면/후면·15fps 송신 확인, 버린 비율 0.8~2.7%, ack p95 34~50ms → 기준 통과(PRD 7.4). 미리보기가 어둡던 버그(`#notice` 검은 막이 hidden이어도 덮음) 수정 `580d342`. 브라우저 카메라는 정상 노출이었음(ISO 50, 밝은 형광등).
- 2026-10-29 (세 번째 세션): main(#6 그림판, #7 vision) 병합 — 충돌 없음. **M-46 시연 모드·M-47 배터리** 구현. headless Chrome(가짜 카메라)+fakeredis gateway로 시연 모드 중 14~15fps 송신 유지, 새로고침 후 유지, CSV에 배터리 열 확인. 폰에서는 아직 안 봄.
  - 병합 전 점검: main 대비 뒤처짐 0, `pytest` 103 통과(1 skip)·`ruff` 통과. 브라우저 통합: 그림판 "새 세션" → QR 표시 → 폰 페이지 15fps 송신 → QR 숨김, 두 번째 폰 접속 시 첫 폰 4409 안내 확인(headless, fakeredis).
- **확인 못 한 것**: 백그라운드 복귀·권한 거부 안내·Wake Lock·CSV 저장을 폰에서 따로 확인 안 함, 기종 기록, PC 그림판과의 통합(PiP).

## 구조
| 파일 | 역할 |
|---|---|
| `index.html` / `style.css` | 미리보기 + 상태 패널 + 버튼 |
| `app.js` | 설정·WebSocket·캡처·인코딩·흐름 제어·시계 응답·Wake Lock |
| `PRD.md` | 요구사항(M-xx), 측정 계획, 팀장에게 물을 질문 |
| `README.md` | 동작 요약, 확인 방법 |

계약: `docs/03-protocol.md`(프레임 `[4B BE 헤더 길이][JSON {seq,capture_ts,mirror}][JPEG]`, ack, ping/pong/clock, close 4404/4409).

## 남은 일
1. **실제 폰 시험 나머지** — 기본 송신은 1차 통과. 남은 것: 백그라운드 갔다 오기, 권한 거부 안내, 화면 꺼짐 방지, "측정 CSV 저장", 시연 모드·배터리 표시, 기종 기록. 4409 확인(폰 두 대로 같은 주소 열기).
2. 기기×네트워크×설정 측정표(PRD 7.2) — CSV를 이 폴더 `measurements/`에 모으고 요약은 `measurements.md`에.
3. (5단계) 10분 연속 시험(시연 모드로, CSV의 배터리 열로 소모량 확인), 시연 체크리스트 폰 항목 검토. (M-46·47은 구현 완료)
4. 팀장에게 물을 것(PRD 9절): Q1 세로 프레임 허용 여부, Q2 seq 규칙 명시, Q6 포트 8443 충돌 안내, gateway 테스트 멈춤(위 "현재 상태"). (Q3은 해결)
5. 다음 변경도 PR로 올린다(본문은 `.github/pull_request_template.md`, 제목은 `feat(mobile): …`). 병합은 사용자가 지시할 때만.

## 시험하는 법
**A. Docker 있는 PC (정식)**: `copy .env.example .env` → `python tools/gen_cert.py`(LAN IP 선택) → `docker compose up -d --build` → PC 브라우저 `https://<LAN-IP>:8443/` 에서 QR 스캔. 또는 `curl.exe -k -X POST https://<LAN-IP>:8443/api/sessions` 로 세션을 만들고 폰에서 `mobile_url` 접속.

**B. Docker 없는 PC (폰 전용 시험)**: venv에 `requirements-dev.txt` 포함 설치 후, 아래 스크립트를 저장소 밖에 두고 실행. Redis 대신 fakeredis라 PC 그림판·vision은 없다.
```python
# run_gw.py  — 실행: python -I run_gw.py 9443 key.pem cert.pem
import sys

sys.path.insert(0, "<repo>/services/gateway")
import fakeredis.aioredis as fr, uvicorn
from gateway.main import create_app

uvicorn.run(
    create_app(fr.FakeRedis()),
    host="0.0.0.0",
    port=int(sys.argv[1]),
    log_level="warning",
    ssl_keyfile=sys.argv[2],
    ssl_certfile=sys.argv[3],
)
```
인증서: `openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 30 -subj "/CN=<IP>" -addext "subjectAltName=IP:<IP>,DNS:localhost"`. 서버 실행 후 `curl -k -X POST https://<IP>:9443/api/sessions` 로 세션을 만들면 응답의 `mobile_url`을 폰에서 연다(서버를 재시작하면 세션이 사라지니 다시 만든다). 폰에서 인증서 경고는 "고급 → 계속".

**C. 폰 없이 브라우저 자동 확인**: B의 `run_gw.py`를 `127.0.0.1`·http(인증서 없이)로 띄우면 localhost는 보안 컨텍스트라 카메라가 허용된다. Chrome을 `--headless=new --use-fake-device-for-media-stream --use-fake-ui-for-media-stream --remote-debugging-port=9333`로 열고 CDP로 버튼 클릭·`state` 값을 확인한다(스크립트는 저장소 밖에 둔다).

**gateway 단독 확인**: `python tools/ws_client.py` (팀장 도구, 세션 생성~왕복을 OK/NG로 출력).

## 교훈 / 함정
- 이 PC(`C:\Users\박민성`)는 **한글 사용자 경로 때문에 Miniconda 설치가 종료 코드 2로 실패** → Python 3.11 + `.venv`로 대체. (`.venv`는 `.gitignore`에 없어서 `.git/info/exclude`에 넣어 둠)
- 리그 오브 레전드 클라이언트가 로컬 **8443**을 사용한다. 시연 PC에서는 끄거나 `.env`의 `GATEWAY_PORT` 변경(컨테이너 내부 포트는 고정).
- 모르는 세션(`?s=dev` 등 만들지 않은 ID)은 close 4404. 같은 세션에 폰 2대면 먼저 붙은 폰이 4409로 밀려나고 재접속하지 않는 게 맞다.
- Windows 방화벽 허용 창, 크롬 확장 미연결 등 시스템 설정은 사용자가 직접 한다.
- 이 PC git 작성자: `msungaffa <msung1012@gmail.com>` — 새 PC는 저장소에서 `git config user.name/user.email` 설정 필요.

## 이 PC 고유 정보 (다른 PC에선 달라질 수 있음)
- 첫 PC(`C:\Users\박민성`): 저장소 `C:\dev\AirStroke`, LAN IP `192.168.0.7`, Python 3.11 `%LOCALAPPDATA%\Programs\Python\Python311` + `.venv`.
- 두 번째 PC(`C:\Users\박성빈`): 저장소 `C:\dev\AirStroke`. Miniforge가 `C:\miniforge3`라 한글 경로 문제 없이 **conda `airstroke` 환경 생성됨**(`C:\miniforge3\envs\airstroke\python.exe`). Docker 있음(아직 안 씀).
