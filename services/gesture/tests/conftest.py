from __future__ import annotations

import json
from pathlib import Path

import pytest

from airstroke_shared.schemas import LandmarksMsg

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "landmarks"


def load_fixture(name: str) -> list[LandmarksMsg]:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return [LandmarksMsg.model_validate(m) for m in data["messages"]]


@pytest.fixture
def fixture_messages():
    return load_fixture
