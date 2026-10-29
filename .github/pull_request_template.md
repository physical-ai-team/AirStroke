<!-- PR 제목 형식: <type>(<scope>): <설명>   예) feat(gesture): 검지 펴짐 판별 추가
     type: feat | fix | docs | refactor | test | perf | chore | ci
     scope: gateway | vision | gesture | mobile | canvas | shared | tools | infra  (docs/07-team.md) -->

## 요약
<!-- 무엇을, 왜 바꿨는지 1~3줄 -->

## 담당 영역
- [ ] gateway / shared / 인프라 (김세광)
- [ ] vision (김정윤)
- [ ] gesture (이기태)
- [ ] mobile (박민성)
- [ ] canvas (조아람)

## 담당 영역 밖 변경
- [ ] 없음
- [ ] 있음 → 파일: <!-- 경로 --> / 해당 담당자 리뷰 요청함
- [ ] `shared/` 변경 있음 → **팀장 승인 필요**, 영향받는 서비스: <!-- vision, gesture, ... -->

## 환경 갱신 필요
- [ ] 아니오
- [ ] **예** — 추가/변경 패키지: <!-- 예: numpy==2.4.6 (services/vision/requirements.txt) -->
      머지 후 `conda env update -f environment.yml --prune` 및 `docker compose build` 필요
- [ ] `.env.example`에 새 설정 추가: <!-- 키 이름 -->

## 실행·확인 방법
<!-- 리뷰어가 그대로 따라 할 수 있게. 예: docker compose up -d --build → python tools/mock_landmarks.py → ... -->

## 체크리스트
- [ ] `pytest` 통과
- [ ] `ruff check .` / `ruff format --check .` 통과
- [ ] 메시지 스키마/채널을 바꿨다면 CLAUDE.md, 서비스 README 갱신
- [ ] `.env`, 인증서 등 비밀 파일 미포함
