# vision (담당: 김정윤)

`frames:*`를 구독해 MediaPipe Tasks **HandLandmarker**(CPU)로 손 랜드마크 21개를 추출하고 `landmarks:{sid}`로 publish합니다.

## 역할과 규칙
- **최신 프레임만 처리**: 구독 루프가 세션별 슬롯 하나를 계속 덮어쓰고([latest.py](vision/latest.py)), 추론 루프는 그 슬롯에서 꺼냅니다. 추론이 밀리면 중간 프레임은 버려지고, 버린 수는 `dropped` 통계로 남깁니다.
- **세션별 HandLandmarker 인스턴스**: VIDEO 모드는 타임스탬프가 단조 증가해야 하므로 세션마다 따로 만듭니다. `VISION_SESSION_IDLE_SEC` 동안 프레임이 없으면 해제합니다. (3단계)
- 좌표는 **카메라 원본 기준**(반전·매핑 전)으로 내보냅니다. 반전과 매핑은 gesture가 담당합니다. 받은 `mirror`와 `trace`는 그대로 넘기고 `trace.vision_done`만 채웁니다.
- MediaPipe 1.x에는 `mp.solutions`가 없습니다. `mediapipe.tasks.python.vision`만 사용합니다.

## 입출력
| 방향 | 채널 | 스키마 |
|---|---|---|
| 입력 | `frames:*` (PSUBSCRIBE) | `FrameMsg` |
| 출력 | `landmarks:{sid}` | `LandmarksMsg` |
| 하트비트 | `health:vision` | 통계(`processed`, `fps`, `dropped`) 포함 |

## 단독 실행
```powershell
docker compose up -d redis
docker compose stop vision                 # compose의 vision과 동시에 띄우지 않기
cd services/vision ; python -m vision
# 다른 터미널(레포 루트): 웹캠 프레임 흘려보내기
python tools/stream_frames.py --show
# 출력 확인 / 녹화
python tools/record_landmarks.py --duration 10
```
- 테스트: 레포 루트에서 `pytest services/vision`

## 설정 (.env)
`NUM_HANDS`(기본 1), `MIN_HAND_DETECTION_CONFIDENCE`, `MIN_HAND_PRESENCE_CONFIDENCE`, `MIN_TRACKING_CONFIDENCE`, `VISION_SESSION_IDLE_SEC`, `STATS_INTERVAL_SEC`

## 의존성 주의
- OpenCV는 `opencv-contrib-python` 하나만 씁니다(MediaPipe 의존성). 다른 OpenCV 패키지를 추가하지 마세요.
- Docker 이미지에는 `libgl1`, `libglib2.0-0`, `libportaudio2`가 필요합니다(MediaPipe를 import할 때 sounddevice를 불러옴).
