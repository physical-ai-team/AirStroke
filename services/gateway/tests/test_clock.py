import pytest

from gateway.clock import ClockEstimator


def test_offset_from_single_sample():
    c = ClockEstimator()
    pid = c.new_ping(now=1000.0)
    # 폰 시계가 5000ms 빠르고 왕복 20ms → 폰이 받은 순간은 gateway 1010
    best = c.on_pong(pid, t_client=1010.0 + 5000.0, now=1020.0)
    assert best.rtt_ms == pytest.approx(20.0)
    assert best.offset_ms == pytest.approx(5000.0)
    assert c.to_server_time(9000.0) == pytest.approx(4000.0)


def test_uses_sample_with_smallest_rtt():
    c = ClockEstimator()
    fast = c.new_ping(now=0.0)
    slow = c.new_ping(now=100.0)
    c.on_pong(fast, t_client=5.0 + 300.0, now=10.0)  # RTT 10, offset 300
    best = c.on_pong(slow, t_client=150.0 + 300.0 + 40.0, now=300.0)  # RTT 200, 비대칭 오차
    assert best.rtt_ms == pytest.approx(10.0)
    assert best.offset_ms == pytest.approx(300.0)


def test_window_drops_old_samples():
    c = ClockEstimator(window=2)
    for i, rtt in enumerate([5.0, 50.0, 60.0]):
        pid = c.new_ping(now=i * 1000.0)
        c.on_pong(pid, t_client=0.0, now=i * 1000.0 + rtt)
    assert c.best.rtt_ms == pytest.approx(50.0)  # 가장 좋았던 5ms 샘플은 창 밖으로 밀려남


def test_unknown_or_duplicate_pong_ignored():
    c = ClockEstimator()
    assert c.to_server_time(123.0) is None
    assert c.on_pong(99, t_client=0.0, now=1.0) is None
    pid = c.new_ping(now=0.0)
    assert c.on_pong(pid, t_client=0.0, now=2.0) is not None
    assert c.on_pong(pid, t_client=0.0, now=3.0) is None


def test_pending_pings_are_bounded():
    c = ClockEstimator(window=3)
    ids = [c.new_ping(now=float(i)) for i in range(5)]
    assert c.on_pong(ids[0], t_client=0.0, now=10.0) is None  # 너무 오래돼 버려짐
    assert c.on_pong(ids[-1], t_client=0.0, now=10.0) is not None
