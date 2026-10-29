from vision.landmarker import SessionLandmarkers


class FakeLandmarker:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make(idle_sec: float = 30.0):
    clock = FakeClock()
    return SessionLandmarkers(FakeLandmarker, idle_sec, clock), clock


def test_creates_one_instance_per_session():
    sessions, _ = make()
    a1, _, created1 = sessions.acquire("a", 1000.0)
    a2, _, created2 = sessions.acquire("a", 1066.0)
    b1, _, created3 = sessions.acquire("b", 1000.0)
    assert (created1, created2, created3) == (True, False, True)
    assert a1 is a2 and a1 is not b1
    assert len(sessions) == 2


def test_timestamp_is_int_and_strictly_increasing():
    sessions, _ = make()
    assert sessions.acquire("a", 1000.7)[1] == 1000
    assert sessions.acquire("a", 1000.9)[1] == 1001  # 같은 ms → +1
    assert sessions.acquire("a", 900.0)[1] == 1002  # 되돌아간 ts → +1
    assert sessions.acquire("a", 2000.0)[1] == 2000


def test_timestamps_are_independent_per_session():
    sessions, _ = make()
    sessions.acquire("a", 5000.0)
    assert sessions.acquire("b", 1000.0)[1] == 1000


def test_reap_closes_only_idle_sessions():
    sessions, clock = make(idle_sec=30)
    a, _, _ = sessions.acquire("a", 0.0)
    b, _, _ = sessions.acquire("b", 0.0)
    clock.now = 20
    sessions.acquire("b", 1.0)
    clock.now = 30
    assert sessions.reap() == ["a"]
    assert a.closed and not b.closed
    assert "a" not in sessions and "b" in sessions


def test_reaped_session_is_recreated_with_fresh_timestamps():
    sessions, clock = make(idle_sec=30)
    old, _, _ = sessions.acquire("a", 5000.0)
    clock.now = 30
    sessions.reap()
    new, ts, created = sessions.acquire("a", 100.0)
    assert created and new is not old and ts == 100


def test_close_all():
    sessions, _ = make()
    a, _, _ = sessions.acquire("a", 0.0)
    b, _, _ = sessions.acquire("b", 0.0)
    sessions.close_all()
    assert a.closed and b.closed and len(sessions) == 0
