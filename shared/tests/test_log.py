import json
import logging

from airstroke_shared.log import JsonFormatter


def test_json_formatter_includes_extra_fields():
    record = logging.LogRecord("vision", logging.INFO, __file__, 1, "frame_processed", None, None)
    record.session = "abc"
    record.infer_ms = 12.5
    data = json.loads(JsonFormatter("vision").format(record))
    assert data["service"] == "vision"
    assert data["event"] == "frame_processed"
    assert data["session"] == "abc"
    assert data["infer_ms"] == 12.5
