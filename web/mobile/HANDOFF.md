# HANDOFF — 폰 카메라 페이지 (박민성 담당, `web/mobile/`)

다른 PC에서 이어받을 때 **"남은 일" 절만 먼저** 읽는다. 기능 목록·측정 계획은 [PRD.md](PRD.md), 팀 규칙은 저장소 루트 `CLAUDE.md`.
(`docs/`와 루트 설정은 팀장 영역이라 내 기록은 이 폴더 안에만 둔다.)

## 현재 상태 (2026-10-29)
- 브랜치 `feat/mobile-camera` (origin에 push됨, **PR 없음, main 병합 없음**). 병합 전에는 팀 확인 필요.
- 구현됨: 카메라 시작/전환, `/api/config` 수신, 바이너리 프레임 송신, 흐름 제어(inflight 2), ping→pong, clock 표시, Wake Lock, 재연결(0.5→5초), close 4404/4409 처리, 상태 패널.
- 확인한 것: main 병합 후 `pytest` 57개·`ruff` 통과. 진짜 gateway 코드(fakeredis)에 `app.js`를 붙인 Node 하네스로 15fps·ack 1ms·4404·4409 확인.
- **확인 못 한 것**: 실제 폰 브라우저(카메라 권한, 전환, Wake Lock, 실제 Wi-Fi 수치), PC 그림판과의 통합(PiP). 측정값 아직 없음.

## 구조
| 파일 | 역할 |
|---|---|
| `index.html` / `style.css` | 미리보기 + 상태 패널 + 버튼 |
| `app.js` | 설정·WebSocket·캡처·인코딩·흐름 제어·시계 응답·Wake Lock |
| `PRD.md` | 요구사항(M-xx), 측정 계획, 팀장에게 물을 질문 |
| `README.md` | 동작 요약, 확인 방법 |

계약: `docs/03-protocol.md`(프레임 `[4B BE 헤더 길이][JSON {seq,capture_ts,mirror}][JPEG]`, ack, ping/pong/clock, close 4404/4409).

## 남은 일
1. **실제 폰 시험** — 아래 "시험하는 법". 송신 fps, 버린 비율, ack 왕복, 전면/후면 전환, 화면 꺼짐 방지를 확인하고 숫자를 PRD 7절에 기록.
2. PRD 보강 항목: M-13(오류 종류별 안내), M-14(마지막 카메라 방향 기억), M-26(백그라운드 탭 처리), M-42~44(프레임 크기·인코딩 시간·ack p50/p95), M-25(ack 타임아웃).
3. 3단계: M-45 측정 CSV 내보내기, 기기×네트워크×설정 측정표(PRD 7.2).
4. 팀장에게 물을 것(PRD 9절): Q1 세로 프레임 허용 여부, Q2 seq 규칙 명시, Q3 publish 오류 시 ack, Q6 포트 8443 충돌 안내.
5. main 병합이 필요해지면 **병합하지 말고 사용자에게 알려 팀 확인 메시지부터** 보낸다. PR 본문은 `.github/pull_request_template.md`, 제목은 `feat(mobile): …`.

## 시험하는 법
**A. Docker 있는 PC (정식)**: `copy .env.example .env` → `python tools/gen_cert.py`(LAN IP 선택) → `docker compose up -d --build` → PC 브라우저 `https://<LAN-IP>:8443/` 에서 QR 스캔. 또는 `curl.exe -k -X POST https://<LAN-IP>:8443/api/sessions` 로 세션을 만들고 폰에서 `mobile_url` 접속.

**B. Docker 없는 PC (폰 전용 시험)**: venv에 `requirements-dev.txt` 포함 설치 후, 아래 스크립트를 저장소 밖에 두고 실행. Redis 대신 fakeredis라 PC 그림판·vision은 없다.
```python
# run_gw.py  — 실행: python -I run_gw.py 9443 key.pem cert.pem
import sys
sys.path.insert(0, "<repo>/services/gateway")
import fakeredis.aioredis as fr, uvicorn
from gateway.main import create_app
uvicorn.run(create_app(fr.FakeRedis()), host="0.0.0.0", port=int(sys.argv[1]),
            log_level="warning", ssl_keyfile=sys.argv[2], ssl_certfile=sys.argv[3])
```
인증서: `openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 30 -subj "/CN=<IP>" -addext "subjectAltName=IP:<IP>,DNS:localhost"`. 서버 실행 후 `curl -k -X POST https://<IP>:9443/api/sessions` 로 세션을 만들면 응답의 `mobile_url`을 폰에서 연다(서버를 재시작하면 세션이 사라지니 다시 만든다). 폰에서 인증서 경고는 "고급 → 계속".

**gateway 단독 확인**: `python tools/ws_client.py` (팀장 도구, 세션 생성~왕복을 OK/NG로 출력).

## 교훈 / 함정
- 이 PC(`C:\Users\박민성`)는 **한글 사용자 경로 때문에 Miniconda 설치가 종료 코드 2로 실패** → Python 3.11 + `.venv`로 대체. (`.venv`는 `.gitignore`에 없어서 `.git/info/exclude`에 넣어 둠)
- 리그 오브 레전드 클라이언트가 로컬 **8443**을 사용한다. 시연 PC에서는 끄거나 `.env`의 `GATEWAY_PORT` 변경(컨테이너 내부 포트는 고정).
- 모르는 세션(`?s=dev` 등 만들지 않은 ID)은 close 4404. 같은 세션에 폰 2대면 먼저 붙은 폰이 4409로 밀려나고 재접속하지 않는 게 맞다.
- Windows 방화벽 허용 창, 크롬 확장 미연결 등 시스템 설정은 사용자가 직접 한다.
- 이 PC git 작성자: `msungaffa <msung1012@gmail.com>` — 새 PC는 저장소에서 `git config user.name/user.email` 설정 필요.

## 이 PC 고유 정보 (다른 PC에선 달라질 수 있음)
- 저장소 `C:\dev\AirStroke`, LAN IP `192.168.0.7`, Python 3.11 `%LOCALAPPDATA%\Programs\Python\Python311`.
