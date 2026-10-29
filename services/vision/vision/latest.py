from __future__ import annotations

import asyncio


class LatestSlots:
    """세션별로 가장 최근 메시지 하나만 보관한다.

    구독 쪽이 put()으로 계속 덮어쓰고, 추론 루프는 get()으로 꺼낸다.
    추론이 느리면 그 사이 들어온 프레임은 덮어써져 버려진다 (dropped 증가).
    여러 세션이 있으면 dict 삽입 순서대로 돌아가며 꺼낸다 (pop 후 재삽입 → 맨 뒤).
    """

    def __init__(self) -> None:
        self._slots: dict[str, bytes] = {}
        self._event = asyncio.Event()
        self.dropped = 0

    def put(self, session_id: str, raw: bytes) -> None:
        if session_id in self._slots:
            self.dropped += 1
        self._slots[session_id] = raw
        self._event.set()

    async def get(self) -> tuple[str, bytes]:
        while not self._slots:
            self._event.clear()
            await self._event.wait()
        session_id = next(iter(self._slots))
        return session_id, self._slots.pop(session_id)

    def __len__(self) -> int:
        return len(self._slots)
