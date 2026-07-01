"""Hermetic test that go-run agents absorb OpenCode JSONL execution data.

Verifies the wiring from worker-output.txt -> structured agent fields without
spending OpenCode tokens. Real-value confirmation is a documented manual step in
docs/status/recon-receipt-opencode-event-integration.md.
"""
from control_plane.go_dispatch import GoAgentDispatch, _apply_opencode_events


def _write_worker_output(packet_dir, text):
    (packet_dir / "worker-output.txt").write_text(text, encoding="utf-8")


def test_apply_opencode_events_fills_structured_fields(tmp_path):
    packet_dir = tmp_path / "packet"
    packet_dir.mkdir()
    _write_worker_output(
        packet_dir,
        "STDOUT\n"
        '{"type":"session","sessionID":"ses_xyz","modelID":"stepfun/step-3.7-flash"}\n'
        '{"type":"tool","name":"write","input":{"filePath":"src/main.py"}}\n'
        '{"type":"step-finish","tokens":{"input":900,"output":120,"total":1020},"cost":0.0015}\n'
        "\nSTDERR\n\n",
    )
    agent = GoAgentDispatch(
        agent_id="coding-agent-1",
        shard_index=1,
        shard_count=1,
        targets=["src/main.py"],
        target_bytes=10,
        packet_dir=str(packet_dir),
        task_spec_path=str(packet_dir / "TASKSPEC.json"),
        worker_command=["opencode", "run", "-m", "stepfun/step-3.7-flash", "--format", "json", "p"],
    )

    _apply_opencode_events(agent)

    assert agent.session_id == "ses_xyz"
    assert agent.input_tokens == 900
    assert agent.output_tokens == 120
    assert agent.total_tokens == 1020
    assert agent.cost == 0.0015
    assert {"name": "write", "target": "src/main.py"} in agent.tool_calls


def test_apply_opencode_events_skips_non_opencode_worker(tmp_path):
    packet_dir = tmp_path / "packet"
    packet_dir.mkdir()
    _write_worker_output(packet_dir, '{"type":"session","sessionID":"ses_xyz"}\n')
    agent = GoAgentDispatch(
        agent_id="a1",
        shard_index=1,
        shard_count=1,
        targets=[],
        target_bytes=0,
        packet_dir=str(packet_dir),
        task_spec_path="",
        worker_command=["python", "-m", "your_worker"],
    )

    _apply_opencode_events(agent)

    assert agent.session_id == ""
    assert agent.total_tokens == 0
    assert agent.tool_calls == []


def test_apply_opencode_events_no_output_file_is_noop(tmp_path):
    packet_dir = tmp_path / "packet"
    packet_dir.mkdir()
    agent = GoAgentDispatch(
        agent_id="a1",
        shard_index=1,
        shard_count=1,
        targets=[],
        target_bytes=0,
        packet_dir=str(packet_dir),
        task_spec_path="",
        worker_command=["opencode", "run"],
    )

    _apply_opencode_events(agent)

    assert agent.session_id == ""
    assert agent.cost == 0.0
