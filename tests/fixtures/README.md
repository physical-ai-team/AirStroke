# tests/fixtures

| 경로 | 내용 |
|---|---|
| `landmarks/gesture_{index,index_middle,fist,palm}.json` | 합성 데이터: 제스처별 손 모양을 2초간 정지 (15fps, 30프레임) |
| `landmarks/scenario_draw.json` | 합성 시나리오: 주먹 → 검지로 원 → 두 손가락 이동 → 검지로 직선 → 손바닥 → 손 없음 |

- 형식: `{"meta": {...}, "messages": [LandmarksMsg, ...]}` — `tools/record_landmarks.py`로 녹화한 파일과 같습니다.
- 합성 데이터 재생성: `python tools/gen_synthetic_landmarks.py`
- 실제 손 녹화를 추가할 때는 `meta.synthetic=false`로 두고 파일명에 `real_` 접두사를 붙입니다(예: `real_draw_rear_cam.json`).
- 누구나 fixture를 추가할 수 있습니다. 기존 파일 수정과 삭제는 팀장 확인을 받으세요.
