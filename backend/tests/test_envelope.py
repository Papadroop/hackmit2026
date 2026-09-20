import json

import pytest

from auditor.envelope import Event, LogError, log_summary, parse_log

STARTED = {"t_ms": 0, "type": "analysis.started", "payload": {}}
COMPLETED = {"type": "analysis.completed", "payload": {}}


def lines(*events: dict) -> list[str]:
    return [json.dumps(e) for e in events]


def test_valid_log_assigns_seq_and_summarises():
    events = parse_log(lines(STARTED, {"t_ms": 10, "type": "claim.found", "payload": {"id": "C1"}}, {"t_ms": 20, **COMPLETED}))
    assert [e.seq for e in events] == [1, 2, 3]
    assert events[1].payload == {"id": "C1"}
    assert log_summary(events) == {
        "events": 3,
        "duration_ms": 20,
        "types": {"analysis.completed": 1, "analysis.started": 1, "claim.found": 1},
    }


def test_blank_lines_are_ignored():
    raw = lines(STARTED, {"t_ms": 5, **COMPLETED})
    assert len(parse_log(["", *raw, "   ", ""])) == 2


def test_explicit_seq_must_match_position():
    with pytest.raises(LogError, match=":2: seq is 5, expected 2"):
        parse_log(lines(STARTED, {"seq": 5, "t_ms": 5, **COMPLETED}))


@pytest.mark.parametrize(
    "bad, message",
    [
        ([{"t_ms": 0, "type": "stage.started", "payload": {"stage": "x"}}, {"t_ms": 1, **COMPLETED}], "first event must be analysis.started"),
        ([STARTED, {"t_ms": 1, "type": "claim.found", "payload": {}}], "last event must be analysis.completed or analysis.failed"),
        ([STARTED, {"t_ms": 1, **COMPLETED}, {"t_ms": 2, **COMPLETED}], "must be the last event"),
        ([STARTED, {"t_ms": 1, **STARTED}, {"t_ms": 2, **COMPLETED}], "may only appear first"),
        ([STARTED, {"t_ms": 5, "type": "a.b", "payload": {}}, {"t_ms": 4, **COMPLETED}], "earlier than the previous event"),
        ([STARTED, {"t_ms": 1, "type": "ClaimFound", "payload": {}}, {"t_ms": 2, **COMPLETED}], "namespace.verb"),
        ([STARTED, {"t_ms": 1, "type": "nodot", "payload": {}}, {"t_ms": 2, **COMPLETED}], "namespace.verb"),
        ([STARTED, {"t_ms": 1, "type": "analysis.failed", "payload": {}}], "needs a string 'error'"),
        ([STARTED, {"t_ms": 1, "type": "stage.started", "payload": {}}, {"t_ms": 2, **COMPLETED}], "needs a string 'stage'"),
        ([STARTED, {"t_ms": 1, "type": "a.b", "payload": {}, "extra": 1}, {"t_ms": 2, **COMPLETED}], "extra"),
        ([STARTED, {"t_ms": 1, "type": "a.b", "payload": "nope"}, {"t_ms": 2, **COMPLETED}], "payload"),
        ([STARTED, {"t_ms": -1, "type": "a.b", "payload": {}}, {"t_ms": 2, **COMPLETED}], "t_ms"),
    ],
)
def test_rule_violations_name_the_line(bad, message):
    with pytest.raises(LogError, match=message):
        parse_log(lines(*bad), source="f.jsonl")


def test_error_carries_source_and_line():
    with pytest.raises(LogError, match=r"^f\.jsonl:2: "):
        parse_log(lines(STARTED, {"t_ms": 1, "type": "nodot", "payload": {}}), source="f.jsonl")


def test_invalid_json_and_empty_log():
    with pytest.raises(LogError, match="not valid JSON"):
        parse_log(["{not json"])
    with pytest.raises(LogError, match="log is empty"):
        parse_log([])


def test_event_line_round_trips():
    event = Event(seq=1, t_ms=0, type="analysis.started", payload={"a": [1, "é"]})
    assert Event.model_validate_json(event.to_line()) == event
