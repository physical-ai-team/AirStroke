# AirStroke 문서

기획, 설계, 규칙 문서 모음입니다. 처음 합류했다면 1 → 2 → 7 → 8 순서로 읽으세요.

| # | 문서 | 내용 | 주로 볼 사람 |
|---|---|---|---|
| 1 | [01-overview.md](01-overview.md) | 프로젝트 개요, 사용자 흐름, 시연 형태, 개발 환경 제약 | 전원 |
| 2 | [02-architecture.md](02-architecture.md) | 컨테이너 구성, 데이터 흐름, 처리 정책(프레임 버리기·흐름 제어·시계 동기화) | 전원 |
| 3 | [03-protocol.md](03-protocol.md) | Redis 채널 스키마, Redis 키, 브라우저 ↔ gateway 계약(HTTP·WebSocket) | 전원 |
| 4 | [04-gestures.md](04-gestures.md) | 손가락 판별, 제스처 규칙, 디바운스, 좌표 변환, 스무딩 | gesture, canvas |
| 5 | [05-ui.md](05-ui.md) | PC 그림판·폰 카메라 페이지 요구사항 | canvas, mobile |
| 6 | [06-roadmap.md](06-roadmap.md) | 단계별 구현 계획, 산출물, 확인 방법, 진행 현황 | 전원 |
| 7 | [07-team.md](07-team.md) | 담당 영역, 수정 규칙, 브랜치·PR 규칙 | 전원 |
| 8 | [08-dev-environment.md](08-dev-environment.md) | conda, 버전 고정, OpenCV 규칙, Docker, 개발 도구 | 전원 |
| 9 | [09-demo.md](09-demo.md) | Zoom 시연 환경, 성능 조절, 시연 진행 | 전원 |
| — | [decisions.md](decisions.md) | 설계 결정 기록 (선택지·결정·이유) | 전원 |

- 문제 해결과 시연 체크리스트는 루트 [README.md](../README.md)에 있습니다.
- 서비스별 입출력과 단독 실행 방법은 각 `services/<svc>/README.md`에 있습니다.

## 문서 관리 규칙
- `docs/`는 팀장(김세광)이 관리합니다. 수정이 필요하면 PR로 제안하세요.
- 설계가 바뀌면 코드 PR에 해당 문서 수정도 함께 넣고, [decisions.md](decisions.md)에 결정을 한 줄 이상 추가합니다.
- 코드가 기준인 내용(스키마 필드 등)은 문서에 옮겨 적기보다 소스 파일 링크를 우선합니다.
