"""Hermetic tests for the OpenCode JSONL event parser.

These tests verify the parser's extraction logic against representative OpenCode
`run --format json` event shapes. They do not spend worker tokens. The claim
that real OpenCode output matches these shapes is verified separately by running
OpenCode against a throwaway repo (see
docs/status/recon-receipt-opencode-event-integration.md).
"""
from control_plane.opencode_events import parse_opencode_run_jsonl


def _jsonl(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def test_parses_typical_opencode_events():
    text = _jsonl(
        '{"type":"session","sessionID":"ses_abc","modelID":"stepfun/step-3.7-flash"}',
        '{"type":"tool","name":"read","input":{"filePath":"src/app.py"}}',
        '{"type":"tool","name":"write","input":{"filePath":"src/app.py"}}',
        '{"type":"tool","name":"bash","input":{"command":"pytest -q"}}',
        '{"type":"step-finish","tokens":{"input":1200,"output":340,"total":1540},"cost":0.0021}',
    )
    summary = parse_opencode_run_jsonl(text)

    assert summary.parsed is True
    assert summary.event_count == 5
    assert summary.session_id == "ses_abc"
    assert summary.model == "stepfun/step-3.7-flash"
    assert summary.input_tokens == 1200
    assert summary.output_tokens == 340
    assert summary.total_tokens == 1540
    assert summary.cost == 0.0021
    tool_names = [call.name for call in summary.tool_calls]
    assert tool_names == ["read", "write", "bash"]
    # Only write-class tools count as changed files; read/bash do not.
    assert summary.changed_files == ["src/app.py"]


def test_snake_case_and_usage_container():
    text = _jsonl(
        '{"session_id":"s2"}',
        '{"usage":{"input_tokens":10,"output_tokens":5}}',
    )
    summary = parse_opencode_run_jsonl(text)
    assert summary.session_id == "s2"
    assert summary.input_tokens == 10
    assert summary.output_tokens == 5
    # total derived from input+output when not explicitly present
    assert summary.total_tokens == 15


def test_nested_session_id_and_cost_object():
    text = _jsonl(
        '{"session":{"id":"s3"}}',
        '{"cost":{"amount":0.5}}',
    )
    summary = parse_opencode_run_jsonl(text)
    assert summary.session_id == "s3"
    assert summary.cost == 0.5


def test_changed_files_dedupe_and_multiedit():
    text = _jsonl(
        '{"type":"tool","name":"write","input":{"path":"a.py"}}',
        '{"type":"tool","name":"write","input":{"path":"a.py"}}',
        '{"type":"tool","name":"multiedit","args":{"file":"b.py"}}',
    )
    summary = parse_opencode_run_jsonl(text)
    assert summary.changed_files == ["a.py", "b.py"]


def test_tolerates_malformed_and_non_dict_lines():
    text = _jsonl(
        "not json at all",
        "[1, 2, 3]",
        '{"type":"session","sessionID":"ses_ok"}',
        "",
    )
    summary = parse_opencode_run_jsonl(text)
    assert summary.session_id == "ses_ok"
    assert summary.event_count == 1
    assert summary.invalid_line_count == 2


def test_empty_input_is_empty_summary():
    summary = parse_opencode_run_jsonl("")
    assert summary.parsed is False
    assert summary.is_empty() is True
    assert summary.to_dict()["tool_calls"] == []


def test_error_signal_detection():
    text = _jsonl(
        '{"type":"step-finish","tokens":{"total":5}}',
        '{"level":"ERROR","message":"database is locked"}',
    )
    summary = parse_opencode_run_jsonl(text)
    assert "database is locked" in summary.error_signals


def test_tool_object_form():
    text = _jsonl(
        '{"type":"tool_use","tool":{"name":"edit","id":"t1"},"input":{"filePath":"x.py"}}',
    )
    summary = parse_opencode_run_jsonl(text)
    assert [c.name for c in summary.tool_calls] == ["edit"]
    assert summary.changed_files == ["x.py"]


def test_parses_real_opencode_1_17_part_nested_structure():
    # Verified against real OpenCode 1.17.9 output: tool/token/cost data is
    # nested under "part" (part.tool, part.tokens, part.cost).
    text = _jsonl(
        '{"type":"tool_use","sessionID":"ses_real","part":{"type":"tool","tool":"read","state":{"status":"completed","input":{"filePath":"TASKSPEC.json"}}}}',
        '{"type":"tool_use","sessionID":"ses_real","part":{"type":"tool","tool":"skill","state":{"status":"completed","input":{"name":"rdgoal"}}}}',
        '{"type":"tool_use","sessionID":"ses_real","part":{"type":"tool","tool":"write","state":{"status":"completed","input":{"filePath":"hello.txt"}}}}',
        '{"type":"step_finish","sessionID":"ses_real","part":{"type":"step-finish","tokens":{"total":24927,"input":634,"output":101},"cost":0.0012}}',
    )
    summary = parse_opencode_run_jsonl(text)
    assert summary.session_id == "ses_real"
    assert summary.total_tokens == 24927
    assert summary.cost == 0.0012
    names = [c.name for c in summary.tool_calls]
    assert "read" in names and "skill" in names and "write" in names
    # Only the write tool counts as a changed file; read/skill do not.
    assert summary.changed_files == ["hello.txt"]
