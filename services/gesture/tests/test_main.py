from gesture.core import GestureParams
from gesture.main import SessionRouter


def test_sessions_keep_separate_state(fixture_messages):
    router = SessionRouter(GestureParams())
    msgs = fixture_messages("gesture_index.json")
    for m in msgs[:3]:
        a = router.handle("a", m)
    b = router.handle("b", msgs[0])
    assert (a.gesture, a.stroke_id) == ("index", 1)
    assert b.gesture == "none"  # 세션 b는 디바운스를 처음부터 시작
    assert set(router.sessions) == {"a", "b"}
