# vision (담당: 김정윤)

`frames:*`를 구독해 MediaPipe Tasks **HandLandmarker**(CPU)로 손 랜드마크 21개를 추출하고 `landmarks:{sid}`로 publish합니다.

## 역할과 규칙
- **최신 프레임만 처리**: 구독 루프가 세션별 슬롯 하나를 계속 덮어쓰고([latest.py](vision/latest.py)), 추론 루프는 그 슬롯에서 꺼냅니다. 추론이 밀리면 중간 프레임은 버려지고, 버린 수는 `dropped` 통계로 남깁니다.
- **세션별 HandLandmarker 인스턴스**: VIDEO 모드는 타임스탬프가 단조 증가해야 하므로 세션마다 따로 만듭니다. `VISION_SESSION_IDLE_SEC` 동안 프레임이 없으면 해제합니다. (3단계)
- 좌표는 **카메라 원본 기준**(반전·매핑 전)으로 내보냅니다. 반전과 매핑은 gesture가 담당합니다. 받은 `mirror`·`width`·`height`와 `trace`는 그대로 넘기고 `trace.vision_done`만 채웁니다.
- MediaPipe 1.x에는 `mp.solutions`가 없습니다. `mediapipe.tasks.python.vision`만 사용합니다.

## 입출력
| 방향 | 채널 | 스키마 |
|---|---|---|
| 입력 | `frames:*` (PSUBSCRIBE) | `FrameMsg` |
| 출력 | `landmarks:{sid}` | `LandmarksMsg` |
| 하트비트 | `health:vision` | 통계(`processed`, `fps`, `dropped`) 포함 |

## 주의: handedness
MediaPipe는 입력이 셀카처럼 **좌우 반전된 이미지**라고 가정하고 `Left`/`Right`를 정합니다. vision은 원본 프레임을 반전하지 않고 넣으므로(좌표 원본 유지 규칙), `handedness`가 실제 손과 반대로 나올 수 있습니다. 값은 MediaPipe가 준 그대로 내보냅니다. 현재 gesture는 `handedness`를 쓰지 않습니다. 쓰게 되면 `mirror`와 카메라 방향을 고려해야 하므로 팀장과 계약을 먼저 정합니다.

## 단독 실행
```powershell
docker compose up -d redis
docker compose stop vision                 # compose의 vision과 동시에 띄우지 않기
cd services/vision
python vision/model.py                     # 최초 1회: models/hand_landmarker.task 받기 (해시 확인)
python -m vision
# 다른 터미널(레포 루트): 웹캠 프레임 흘려보내기
python tools/stream_frames.py --show
# 출력 확인 / 녹화
python tools/record_landmarks.py --duration 10
```
- 테스트: 레포 루트에서 `pytest services/vision`

## 설정 (.env)
`NUM_HANDS`(기본 1), `MIN_HAND_DETECTION_CONFIDENCE`, `MIN_HAND_PRESENCE_CONFIDENCE`, `MIN_TRACKING_CONFIDENCE`, `VISION_SESSION_IDLE_SEC`, `STATS_INTERVAL_SEC`

## 모델
- `hand_landmarker.task` float16 v1을 쓰고, URL과 SHA-256은 [model.py](vision/model.py)에 고정되어 있습니다. Docker는 빌드할 때 받고, 로컬은 위 명령으로 받습니다. 파일은 커밋하지 않습니다(`*.task`는 gitignore에 등록됨).
- 시작할 때 모델이 없거나 해시가 다르면 vision이 바로 종료됩니다.

## CPU 튜닝
- 운영 중에는 `stats` 로그의 `decode_ms`·`infer_ms`·`lag_ms`(gateway 수신 → vision 완료, 큐 대기 포함) 평균/p95를 봅니다. `dropped`가 늘면 추론이 프레임 속도를 못 따라가는 것입니다.
- 벤치마크(`python -m vision.bench <손 사진·영상>`, 사용법은 [bench.py](vision/bench.py))로 조합별 시간을 잴 수 있습니다.
- **측정 결과** (2026-10-29, vision 컨테이너, 640×480 JPEG q70, MediaPipe 공식 손 샘플 사진 2장 + 손 없는 화면, 각 60프레임)

  | 조건 | `--cpus=2` 디코드+추론 평균 | `--cpus=1` |
  |---|---|---|
  | 손 있음, `NUM_HANDS=1`, 640 | 19 ms | 19~20 ms |
  | 손 있음, `NUM_HANDS=1`, 320으로 축소 | 18 ms | 17~18 ms |
  | 손 있음, `NUM_HANDS=2` | 33~37 ms | 37~62 ms (흔들림 큼) |
  | 손 없음 (매 프레임 손 검출) | 19~21 ms | 20~25 ms |

- **결론**
  - 추론 전에 해상도를 줄여도 이득이 약 1 ms(디코드)뿐입니다. MediaPipe가 내부에서 모델 입력 크기로 줄이기 때문입니다. 그래서 추론 해상도 설정은 추가하지 않습니다(`decode_jpeg(max_width=...)`는 벤치마크용으로만 둡니다).
  - **`NUM_HANDS`가 가장 큰 손잡이입니다.** 2로 하면 손이 있을 때 추론 시간이 약 2배가 되므로 기본 1을 유지합니다.
  - "모델 복잡도"는 MediaPipe Tasks에 없습니다(예전 `mp.solutions`의 `model_complexity`). 공식 모델은 float16 하나입니다.
  - CPU 1개에서도 프레임당 약 20 ms라 `CAMERA_FPS=15`(프레임 간격 66 ms)에 여유가 큽니다. 지연이 생기면 vision보다 폰 인코딩, 네트워크, 같은 노트북의 다른 부하(PiP, Zoom)를 먼저 의심합니다.
  - 세션의 첫 프레임은 모델 로드 때문에 약 2초 걸립니다(스레드에서 돌아서 다른 세션은 막히지 않음).

## 의존성 주의
- OpenCV는 `opencv-contrib-python` 하나만 씁니다(MediaPipe 의존성). 다른 OpenCV 패키지를 추가하지 마세요.
- Docker 이미지에는 `libgl1`, `libglib2.0-0`, `libportaudio2`(MediaPipe를 import할 때 sounddevice를 불러옴), `libegl1`, `libgles2`(MediaPipe Tasks가 CPU 전용이어도 링크함)가 필요합니다.
