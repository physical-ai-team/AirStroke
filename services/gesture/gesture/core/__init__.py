"""gesture 순수 로직 (Redis 없이 테스트 가능).

landmarks → 손 선택 → 손가락 펴짐 판별 → 제스처 분류 → 디바운스
          → 좌표 변환(반전·중앙영역) → One Euro 스무딩 → stroke_id → commands
규칙: docs/04-gestures.md
"""

from .session import GestureParams, GestureSession

__all__ = ["GestureParams", "GestureSession"]
