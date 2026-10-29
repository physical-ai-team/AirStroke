# gesture (담당: 이기태)

`landmarks:*`를 구독해 손 모양을 분류하고 커서 좌표를 다듬어 `commands:{sid}`로 publish합니다.

## 처리 흐름 (4단계)
1. **손가락 펴짐 판별**: 손목(0번)~끝마디 거리가 손목~PIP 거리보다 크면 펴진 것으로 봅니다(검지 8/6, 중지 12/10, 약지 16/14, 소지 20/18). 엄지는 집기(엄지·검지 끝이 가까움)와 엄지 세움만 따로 봅니다.
2. **제스처 분류**: 집기 → `pinch`/`select`(가장 먼저 판별), 엄지만 → `thumb_up`/`undo`(확정 순간 한 번만), 검지만 → `index`/`draw`, 검지+중지 → `index_middle`/`move`, 주먹 → `fist`/`idle`, 손바닥 → `palm`/`erase`
3. **디바운스**: 같은 제스처가 `DEBOUNCE_FRAMES` 프레임 연속으로 나와야 확정합니다. `thumb_up`만 `UNDO_DEBOUNCE_FRAMES`(더 길게).
4. **좌표 변환**: `mirror=true`(셀카)일 때만 x를 반전하고, 카메라 중앙 `ACTIVE_AREA`(70%)를 캔버스 0~1로 매핑합니다(범위 밖은 0~1로 자름). 프레임이 세로처럼 캔버스(`CAMERA_WIDTH:HEIGHT`)와 비율이 다르면 `landmarks`의 `width`·`height`로 중앙 영역을 캔버스 비율에 맞춥니다(D-018).
5. **스무딩**: One Euro Filter(`ONE_EURO_*`)
6. **새 선**: draw로 바뀔 때 `stroke_id`를 증가시키고 필터를 초기화합니다(엉뚱한 직선 방지).

- 디바운스 상태가 있으므로 프레임을 **버리지 않고 순서대로** 처리하고, 상태는 세션별로 둡니다.
- 판별·디바운스·필터·매핑은 Redis 없이 테스트할 수 있도록 `gesture/core/`에 순수 로직으로 작성하고 pytest를 붙입니다.

## 입출력
| 방향 | 채널 | 스키마 |
|---|---|---|
| 입력 | `landmarks:*` (PSUBSCRIBE) | `LandmarksMsg` |
| 출력 | `commands:{sid}` | `CommandMsg` (`trace.gesture_done` 채움) |
| 하트비트 | `health:gesture` | |

## 단독 실행 (vision·폰 없이)
```powershell
docker compose up -d redis
docker compose stop gesture
cd services/gesture ; python -m gesture
# 다른 터미널(레포 루트): 녹화/합성 랜드마크 재생
python tools/mock_landmarks.py --loop
python tools/mock_landmarks.py --file tests/fixtures/landmarks/gesture_palm.json
```
- 테스트: 레포 루트에서 `pytest services/gesture`
- fixture: `tests/fixtures/landmarks/`. `gesture_*.json`은 제스처별 정지 2초이고, `scenario_draw.json`은 주먹 → 원 그리기 → 이동 → 직선 → 손바닥 → 손 없음 순서입니다. 지금은 합성 데이터이므로, 실제 손은 `tools/record_landmarks.py`로 녹화해서 추가하세요.

## 설정 (.env)
`DEBOUNCE_FRAMES`, `UNDO_DEBOUNCE_FRAMES`, `PINCH_DISTANCE_RATIO`, `ACTIVE_AREA`, `CAMERA_WIDTH`·`CAMERA_HEIGHT`(캔버스 비율), `ONE_EURO_MIN_CUTOFF`, `ONE_EURO_BETA`, `ONE_EURO_D_CUTOFF`
