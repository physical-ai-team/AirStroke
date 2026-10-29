from vision.timing import LatencyWindow


def test_empty_window():
    assert LatencyWindow().flush() == (None, None)


def test_avg_and_p95_then_reset():
    w = LatencyWindow()
    for v in range(1, 101):  # 1..100
        w.add(float(v))
    assert w.flush() == (50.5, 95.0)
    assert w.flush() == (None, None)


def test_single_value():
    w = LatencyWindow()
    w.add(12.34)
    assert w.flush() == (12.3, 12.3)
