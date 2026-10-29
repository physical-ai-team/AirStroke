# 4. 제스처 규칙

gesture 서비스(이기태)가 기준을 정하고, 그림판(조아람)이 같은 규칙으로 화면을 그립니다. 아래 값 중 "초기안"이라고 표시한 것은 담당자가 실험해 보고 조정할 수 있습니다. 조정하면 이 문서와 `.env.example`도 함께 갱신하세요.

## 처리 순서
```
landmarks → ① 손 선택 → ② 손가락 펴짐 판별 → ③ 제스처 분류 → ④ 디바운스
          → ⑤ 좌표 변환(반전·중앙영역) → ⑥ One Euro 스무딩 → ⑦ stroke_id → commands
```

### ① 손 선택
- `NUM_HANDS` 기본값은 1입니다. 손이 여러 개 감지되면 `score`가 가장 높은 손 하나만 씁니다(초기안).
- 손이 없으면 `gesture="none"`, `action="idle"`, `cursor=null`입니다.

### ② 손가락 펴짐 판별 — 손목 기준 거리 비교
손목(0번)에서 끝마디(TIP)까지 거리가 손목에서 PIP 관절까지 거리보다 크면 **펴진 것**으로 봅니다.

| 손가락 | TIP | PIP |
|---|---|---|
| 검지 | 8 | 6 |
| 중지 | 12 | 10 |
| 약지 | 16 | 14 |
| 소지 | 20 | 18 |

- **엄지는 초기 분류에서 제외합니다**(초기안). 엄지는 손목 기준 거리 비교가 불안정해서, 손바닥 판별도 엄지를 뺀 네 손가락으로 합니다.
- 거리 계산에는 x, y만 씁니다(z는 노이즈가 큼).

### ③ 제스처 분류
| 펴진 손가락 | gesture | action | 그림판 라벨 |
|---|---|---|---|
| 검지만 | `index` | `draw` | ✏️ 그리기 |
| 검지 + 중지 | `index_middle` | `move` (펜 들기) | ✌️ 이동 |
| 없음 | `fist` | `idle` | ✊ 대기 |
| 네 손가락 모두 | `palm` | `erase` | ✋ 지우개 |
| 그 외 | `unknown` | `idle` | (라벨 숨김 또는 "?") |
| 손 없음 | `none` | `idle` | (라벨 숨김) |

### ④ 디바운스
- 같은 제스처가 **`DEBOUNCE_FRAMES`(기본 3) 프레임 연속**으로 나와야 확정합니다. 확정되기 전에는 이전에 확정된 제스처를 유지합니다.
- 커서 좌표는 디바운스와 관계없이 매 프레임 갱신합니다.

### ⑤ 좌표 변환
기준 점은 **검지 끝(8번)** 입니다.
1. `mirror=true`(셀카)이면 `x = 1 - x`로 반전합니다. 후면 카메라에서는 반전하지 않습니다.
2. 카메라 중앙 영역을 캔버스 전체로 매핑합니다. 중앙 영역은 **프레임 안에 들어가는 가장 큰 '캔버스 비율' 사각형의 `ACTIVE_AREA`(기본 0.7)배**입니다(D-018).
   ```
   fa = width / height                      # 프레임 비율 (landmarks 의 width·height, 없으면 ca)
   ca = CAMERA_WIDTH / CAMERA_HEIGHT        # 캔버스 비율 (/api/config 의 camera)
   w = ACTIVE_AREA * min(1, ca / fa)        # 중앙 영역 가로 (프레임 기준 0~1)
   h = ACTIVE_AREA * min(1, fa / ca)        # 중앙 영역 세로
   x' = clamp((x - (1 - w) / 2) / w, 0, 1)
   y' = clamp((y - (1 - h) / 2) / h, 0, 1)
   ```
   - 손을 화면 가장자리까지 뻗지 않아도 캔버스 끝까지 닿게 하기 위한 변환입니다.
   - 가로 4:3 프레임이면 `w = h = ACTIVE_AREA`입니다.
   - 폰을 세로(3:4)로 들면 `w = 0.7`, `h = 0.39`가 되어 가로·세로 배율이 같아집니다(손으로 그린 원이 타원이 되지 않음). 대신 영상 위아래 일부는 쓰지 않습니다.
- **그림판도 손 뼈대 21점에 같은 변환을 적용해야** 커서와 뼈대가 어긋나지 않습니다. `ACTIVE_AREA`와 캔버스 비율은 gateway의 `/api/config`로, 프레임 크기는 `landmarks`의 `width`·`height`로 받습니다. 구현: [mapping.py](../services/gesture/gesture/core/mapping.py)

### ⑥ 스무딩 — One Euro Filter
- x와 y에 각각 적용합니다. 파라미터는 `ONE_EURO_MIN_CUTOFF`(1.0), `ONE_EURO_BETA`(0.007), `ONE_EURO_D_CUTOFF`(1.0)입니다(초기안).
  - `min_cutoff`를 낮추면 정지 상태의 떨림이 줄고 반응이 느려집니다.
  - `beta`를 높이면 빠른 움직임을 더 잘 따라갑니다.
- 시간 간격은 메시지의 `ts` 차이로 계산합니다(프레임이 버려져 간격이 일정하지 않을 수 있음).

### ⑦ 새 선 시작 — `stroke_id`
- action이 draw가 **아닌 상태에서 draw로 바뀌는 순간** `stroke_id`를 1 증가시키고 One Euro 필터를 초기화합니다.
- 그림판은 `stroke_id`가 바뀌면 이전 좌표를 버립니다. 그래서 펜을 들었다 놓은 자리 사이에 엉뚱한 직선이 생기지 않습니다.
- 실행 취소(5단계)도 `stroke_id` 단위로 합니다.

## 테스트
- ②~⑦은 Redis 없이 테스트할 수 있도록 `services/gesture/gesture/core/`에 순수 함수와 클래스로 작성하고, pytest로 단위 테스트를 만듭니다.
- 샘플 데이터는 `tests/fixtures/landmarks/`에 있습니다. `gesture_*.json`은 제스처별 정지 2초, `scenario_draw.json`은 연속 시나리오입니다. 지금은 합성 데이터이고, 실제 손 녹화는 `tools/record_landmarks.py`로 추가합니다.
