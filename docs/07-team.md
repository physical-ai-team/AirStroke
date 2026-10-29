# 7. 팀과 작업 규칙

## 담당 영역
| 담당 | 역할 | 폴더 |
|---|---|---|
| 김세광 (팀장) | 아키텍처, docker-compose, Redis, 공통 스키마, gateway 백엔드, 통합 | `docker-compose.yml`, `shared/`, `services/gateway/`, `tools/`, `docs/`, 루트 설정 파일 |
| 김정윤 | vision 서비스 | `services/vision/` |
| 이기태 | gesture 서비스 | `services/gesture/` |
| 박민성 | 폰 카메라 페이지, 디바이스·네트워크 테스트, 지연시간·FPS 측정 | `web/mobile/` |
| 조아람 | PC 그림판 UI | `web/canvas/` |

## 수정 규칙
- **자기 담당 폴더 밖은 수정하지 않습니다. 특히 `shared/`는 팀장 확인 없이 절대 수정하지 않습니다.**
- 팀원 모두 Claude Code로 작업합니다. Claude는 담당 밖 파일을 고쳐야 할 것 같으면 수정하지 않고 사용자에게 알린 뒤 멈춥니다(CLAUDE.md에 명시).
- 스키마나 계약([03-protocol.md](03-protocol.md))을 바꿔야 하면 이슈나 PR로 팀장에게 제안합니다.
- 담당 밖 변경이 꼭 필요한 PR은 해당 담당자를 리뷰어로 지정합니다.
- `tests/fixtures/`: 누구나 fixture를 **추가**할 수 있습니다. 기존 파일 수정과 삭제는 팀장 확인을 받습니다.
- 루트 설정(`.env.example`, `environment.yml`, `requirements-dev.txt`, `pyproject.toml`)은 팀장 영역입니다. 새 설정값이 필요하면 PR로 제안합니다.

## 브랜치
| 접두사 | 영역 |
|---|---|
| `feat/gateway-*` | gateway, shared, 인프라 |
| `feat/vision-*` | vision |
| `feat/gesture-*` | gesture |
| `feat/mobile-*` | 폰 카메라 페이지 |
| `feat/canvas-*` | PC 그림판 |

- **main에 직접 푸시하지 않습니다.** 모든 변경은 PR로 올리고 리뷰를 받습니다(GitHub 브랜치 보호 규칙으로 강제).

## PR 제목·커밋 메시지
[Conventional Commits](https://www.conventionalcommits.org/ko/v1.0.0/) 형식: `<type>(<scope>): <설명>` (설명은 한국어)

| type | 용도 |
|---|---|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `docs` | 문서만 변경 |
| `refactor` | 동작 변화 없는 구조 개선 |
| `test` | 테스트 추가·수정 |
| `perf` | 성능 개선 |
| `chore` | 설정, 의존성, 빌드, 기타 |
| `ci` | CI 설정 |

- scope: `gateway`, `vision`, `gesture`, `mobile`, `canvas`, `shared`, `tools`, `infra`. 여러 영역에 걸치면 생략할 수 있습니다.
- 예시
  - `feat(vision): 세션별 HandLandmarker 추론 추가`
  - `fix(mobile): 전면 카메라 mirror 플래그 누락 수정`
  - `docs: 브라우저-gateway 계약 확정`
  - `chore(vision): mediapipe 버전 갱신` ← "환경 갱신 필요"
- main에는 **Squash and merge**로 합칩니다. PR 제목이 main 커밋 메시지가 되므로 PR 제목을 특히 규칙에 맞춥니다.

## PR
- 템플릿: [.github/pull_request_template.md](../.github/pull_request_template.md)
- 반드시 적을 것: 담당 영역 밖 변경 여부, **"환경 갱신 필요" 여부**, 실행·확인 방법
- 새 패키지를 추가했다면 PR 설명에 **"환경 갱신 필요"** 를 적습니다. 머지 후 팀원들은 `conda env update -f environment.yml --prune`을 실행합니다.
- 인터페이스(채널·스키마·설정)가 바뀌면 해당 서비스 README와 `docs/`를 함께 갱신합니다.

## 서비스 README
각 서비스 폴더의 `README.md`에 **역할, 입출력 채널, 단독 실행 방법**을 적고, 담당자가 관리합니다.
