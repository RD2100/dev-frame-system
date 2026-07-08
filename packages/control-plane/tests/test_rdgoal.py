from pathlib import Path
import json
import os
import shutil
import sys
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jsonschema import Draft202012Validator
from jsonschema.validators import validator_for
import yaml

from control_plane.backup_guard import BackupGuard
from control_plane.cli import main as devframe_cli_main
from control_plane.dashboard import build_dashboard_server
from control_plane.decision_engine import DecisionEngine, DecisionMode, OperationRequest
from control_plane.orchestrator import Orchestrator
from control_plane.project_contract import load_contract, render_contract_markdown
from control_plane.rdgoal import rdgoal
from control_plane.go_dispatch import run_go_dispatch
from control_plane.rdgoal_cli import main as rdgoal_cli_main
from control_plane.runtime_digest import build_runtime_digest, render_runtime_digest_markdown
from control_plane.runtime_store import JournalEvent, RuntimeStore
from control_plane.visual_state import build_visual_control_plane_state, render_visual_control_plane_state_html
from control_plane.skill_registry import list_methodology_skills
from control_plane.worker import AihubGoWorker, CommandWorker, LocalDryRunWorker


REPO_ROOT = Path(__file__).resolve().parents[3]


def write_contract(tmp_path: Path, project_id: str = "demo-project") -> Path:
    contract_path = tmp_path / f"{project_id}.md"
    contract_path.write_text(
        render_contract_markdown(project_id, "Build a working MVP prototype."),
        encoding="utf-8",
    )
    return contract_path


def load_schema(relative_path: str) -> dict:
    return json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8-sig"))


def validate_schema(relative_path: str, data: dict) -> None:
    schema = load_schema(relative_path)
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator_class(schema).validate(data)


def read_yaml_contract(contract_path: Path) -> dict:
    text = contract_path.read_text(encoding="utf-8")
    yaml_block = text.split("```yaml", 1)[1].split("```", 1)[0]
    return yaml.safe_load(yaml_block)


def test_contract_round_trip(tmp_path):
    contract_path = write_contract(tmp_path)

    contract = load_contract(contract_path)

    assert contract.project_id == "demo-project"
    assert contract.autonomy_level == "total_control"
    assert contract.decision_policy.direction_choice == "choose_recommended_path"
    assert contract.prototype_bias.prefer_working_mvp is True


def test_rendered_contract_matches_public_schema(tmp_path):
    contract_path = write_contract(tmp_path)

    validate_schema("schemas/project_contract.schema.json", read_yaml_contract(contract_path))


def test_direction_choice_is_recommend_execute(tmp_path):
    contract = load_contract(write_contract(tmp_path))
    decision = DecisionEngine().decide(
        contract,
        OperationRequest(operation="choose architecture direction"),
    )

    assert decision.mode == DecisionMode.RECOMMEND_EXECUTE
    assert decision.dispatch_allowed is True
    assert "existing architecture" in decision.recommended_path


def test_external_effect_becomes_draft_only(tmp_path):
    contract = load_contract(write_contract(tmp_path))
    decision = DecisionEngine().decide(
        contract,
        OperationRequest(operation="publish production release"),
    )

    assert decision.mode == DecisionMode.DRAFT_ONLY
    assert decision.dispatch_allowed is False


def test_secret_boundary_is_hard_stop(tmp_path):
    contract = load_contract(write_contract(tmp_path))
    decision = DecisionEngine().decide(
        contract,
        OperationRequest(operation="read .env token"),
    )

    assert decision.mode == DecisionMode.HARD_STOP
    assert decision.dispatch_allowed is False


def test_snapshot_execute_creates_rollback_archive(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    target = project_root / "obsolete.txt"
    target.write_text("old content", encoding="utf-8")

    contract = load_contract(write_contract(tmp_path))
    decision = DecisionEngine().decide(
        contract,
        OperationRequest(operation="delete obsolete local file", targets=["obsolete.txt"]),
    )
    guard = BackupGuard("demo-project", project_root, runtime_dir=runtime_dir)
    result = guard.guard(decision, ["obsolete.txt"])

    assert result.allowed is True
    assert result.snapshot is not None
    assert result.snapshot.ok is True
    assert (Path(result.snapshot.reference) / "obsolete.txt").read_text(encoding="utf-8") == "old content"
    assert guard.read_log()[0]["decision_mode"] == "snapshot_execute"


def test_snapshot_execute_requires_explicit_targets(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()

    contract = load_contract(write_contract(tmp_path))
    decision = DecisionEngine().decide(
        contract,
        OperationRequest(operation="delete obsolete local file"),
    )
    guard = BackupGuard("demo-project", project_root, runtime_dir=runtime_dir)
    result = guard.guard(decision, [])

    assert result.allowed is False
    assert "explicit target" in result.reason


def test_snapshot_execute_blocks_target_outside_project_before_snapshot_dir(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()

    contract = load_contract(write_contract(tmp_path))
    decision = DecisionEngine().decide(
        contract,
        OperationRequest(operation="delete obsolete local file", targets=["../outside.txt"]),
    )
    guard = BackupGuard("demo-project", project_root, runtime_dir=runtime_dir)
    result = guard.guard(decision, ["../outside.txt"])

    assert result.allowed is False
    assert result.snapshot is not None
    assert result.snapshot.ok is False
    assert not (runtime_dir / "demo-project" / "snapshots").exists()


def test_orchestrator_dispatch_digest_records_decision(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    contract_path = write_contract(tmp_path)

    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    orchestrator.register(contract_path, project_root)
    result = orchestrator.dispatch(
        project_id="demo-project",
        requirement="Build a working MVP prototype.",
        operation="choose architecture direction",
    )

    digest = orchestrator.build_digest()
    assert result.dispatch_ready is True
    assert result.packet is not None
    assert (Path(result.packet.packet_dir) / "packet.json").exists()
    assert (Path(result.packet.packet_dir) / "TASKSPEC.md").exists()
    assert (Path(result.packet.packet_dir) / "TASKSPEC.json").exists()
    assert digest["projects"][0]["project_id"] == "demo-project"
    assert digest["dispatches"][0]["decision_mode"] == "recommend_execute"
    assert digest["dispatches"][0]["packet_dir"] == result.packet.packet_dir


def test_rdgoal_default_contract_is_project_local(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")

    result = rdgoal(
        orchestrator,
        project_root,
        "Build a working MVP prototype.",
        operation="choose architecture direction",
    )

    assert Path(result.contract_path) == project_root / "rules" / "project-contracts" / "project.md"
    assert Path(result.contract_path).exists()


def test_rdgoal_apply_rdinit_without_bootstrap_assets_does_not_crash(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr("control_plane.rdgoal._candidate_bootstrap_paths", lambda: [])
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")

    result = rdgoal(
        orchestrator,
        project_root,
        "Build a working MVP prototype.",
        operation="choose architecture direction",
        apply_rdinit=True,
    )

    assert result.rdinit_action == "bootstrap_unavailable"
    assert result.dispatch.dispatch_ready is True
    assert any("bootstrap assets are unavailable" in note for note in result.notes)


def test_dispatch_packet_json_matches_public_schema(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    contract_path = write_contract(tmp_path)

    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    orchestrator.register(contract_path, project_root)
    result = orchestrator.dispatch(
        project_id="demo-project",
        requirement="Build a working MVP prototype.",
        operation="choose architecture direction",
    )
    packet = json.loads((Path(result.packet.packet_dir) / "packet.json").read_text(encoding="utf-8"))

    validate_schema("schemas/rdgoal_dispatch_packet.schema.json", packet)


def test_dispatch_packet_taskspec_json_matches_schema(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    contract_path = write_contract(tmp_path)

    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    orchestrator.register(contract_path, project_root)
    result = orchestrator.dispatch(
        project_id="demo-project",
        requirement="Build a working MVP prototype.",
        operation="choose architecture direction",
    )
    schema = load_schema("schemas/agent-runtime/task-spec.schema.json")
    task_spec = json.loads((Path(result.packet.packet_dir) / "TASKSPEC.json").read_text(encoding="utf-8"))

    Draft202012Validator(schema).validate(task_spec)


def test_orchestrator_ingests_execution_report(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    contract_path = write_contract(tmp_path)

    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    orchestrator.register(contract_path, project_root)
    result = orchestrator.dispatch(
        project_id="demo-project",
        requirement="Build a working MVP prototype.",
        operation="choose architecture direction",
    )
    report_path = tmp_path / "ExecutionReport.md"
    report_path.write_text(
        "\n".join([
            "## ExecutionReport: demo",
            "- **Status**: pass",
            "- **Changed Files**:",
            "- `src/app.py`",
            "- **Evidence**: pytest passed",
        ]),
        encoding="utf-8",
    )

    summary = orchestrator.ingest_report(result.packet.packet_dir, report_path)
    digest = orchestrator.build_digest()

    assert summary.status == "passed"
    assert summary.changed_files == ["src/app.py"]
    assert digest["reports"][0]["packet_id"] == result.packet.packet_id


def test_local_dry_run_worker_consumes_ready_packet(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    contract_path = write_contract(tmp_path)

    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    orchestrator.register(contract_path, project_root)
    result = orchestrator.dispatch(
        project_id="demo-project",
        requirement="Build a working MVP prototype.",
        operation="choose architecture direction",
    )

    worker_result = LocalDryRunWorker(runtime_dir=runtime_dir).run_packet(result.packet.packet_dir)

    assert worker_result.summary.status == "passed"
    assert Path(worker_result.report_path).exists()
    assert "Local dry-run worker consumed" in Path(worker_result.report_path).read_text(encoding="utf-8")


def test_runtime_digest_reads_worker_report_across_process_boundary(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    result = rdgoal(
        orchestrator,
        project_root,
        "Build a working MVP prototype.",
        operation="choose architecture direction",
    )

    LocalDryRunWorker(runtime_dir=runtime_dir).run_packet(result.dispatch.packet.packet_dir)
    digest = build_runtime_digest(runtime_dir)
    markdown = render_runtime_digest_markdown(digest)

    assert digest["dispatches"][0]["decision_mode"] == "recommend_execute"
    assert digest["reports"][0]["status"] == "passed"
    assert result.dispatch.packet.packet_id in markdown


def test_runtime_digest_cli_reports_worker_status(tmp_path, capsys):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    result = rdgoal(
        orchestrator,
        project_root,
        "Build a working MVP prototype.",
        operation="choose architecture direction",
    )
    LocalDryRunWorker(runtime_dir=runtime_dir).run_packet(result.dispatch.packet.packet_dir)

    exit_code = rdgoal_cli_main(["digest", "--runtime-dir", str(runtime_dir)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "## Execution Reports" in output
    assert "passed" in output


def test_visual_control_plane_state_reads_rdgoal_runtime(tmp_path):
    from control_plane.t3_adapter import build_t3_client_shell_from_state

    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    result = rdgoal(
        orchestrator,
        project_root,
        "Build a working MVP prototype.",
        operation="choose architecture direction",
    )
    LocalDryRunWorker(runtime_dir=runtime_dir).run_packet(result.dispatch.packet.packet_dir)

    state = build_visual_control_plane_state(runtime_dir)

    validate_schema("schemas/visual_control_plane_state.schema.json", state)
    assert state["projects"][0]["project_id"] == "project"
    assert state["projects"][0]["status"] == "completed"
    assert state["runs"][0]["entrypoint"] == "rdgoal"
    assert state["runs"][0]["status"] == "completed"
    assert state["runs"][0]["review_status"] == "pending"
    assert state["runs"][0]["packet_path"] == result.dispatch.packet.packet_dir
    assert state["runs"][0]["taskspec_path"].endswith("TASKSPEC.md")
    assert state["runs"][0]["taskspec_json_path"].endswith("TASKSPEC.json")
    assert state["runs"][0]["next_command"].startswith("rdgoal digest --runtime-dir")
    assert state["decisions"][0]["status"] == "executed"
    assert state["gates"][0]["next_action"].startswith("Confirm human approval")
    acceptance_gate = next(gate for gate in state["gates"] if gate["kind"] == "acceptance")
    assert acceptance_gate["status"] == "open"
    assert acceptance_gate["next_action"].startswith("Independent review required")
    shell = build_t3_client_shell_from_state(state)
    t3_acceptance_gate = next(gate for gate in shell["devframe"]["gates"] if gate["kind"] == "acceptance")
    assert t3_acceptance_gate["status"] == "open"
    assert state["next_actions"][0]["source_id"] == "human-gate"
    assert state["next_actions"][0]["label"].startswith("Confirm human approval")
    assert state["safety"]["remote_execution_default"] is False


def test_visual_control_plane_state_reads_go_runs(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    source_dir = project_root / "packages" / "control-plane" / "control_plane"
    source_dir.mkdir(parents=True)
    (source_dir / "cli.py").write_text("c" * 24, encoding="utf-8")
    (source_dir / "go_dispatch.py").write_text("g" * 24, encoding="utf-8")

    result = run_go_dispatch(
        project_root,
        "Build a Codex-like programming tool MVP.",
        runtime_dir=runtime_dir,
        agents=2,
        targets=[
            "packages/control-plane/control_plane/cli.py",
            "packages/control-plane/control_plane/go_dispatch.py",
        ],
    )
    state = build_visual_control_plane_state(runtime_dir)
    html = render_visual_control_plane_state_html(state, lang="zh-CN")

    validate_schema("schemas/visual_control_plane_state.schema.json", state)
    assert len(state["go_runs"]) == 1
    assert state["go_runs"][0]["go_run_id"] == result.go_run_id
    assert state["go_runs"][0]["status"] == "queued"
    assert state["go_runs"][0]["execute"] is False
    assert state["go_runs"][0]["status_command"] == (
        f'devframe code status "{result.go_run_id}" --runtime-dir "{runtime_dir}"'
    )
    assert state["go_runs"][0]["execute_command"] == (
        f'devframe code execute "{result.go_run_id}" --runtime-dir "{runtime_dir}"'
    )
    assert len(state["go_runs"][0]["agents"]) == 2
    assert state["go_runs"][0]["agents"][0]["targets"] == [
        "packages/control-plane/control_plane/cli.py"
    ]
    assert state["go_runs"][0]["agents"][0]["target_bytes"] == 24
    assert state["go_runs"][0]["agents"][1]["worker_command"][:4] == [
        "opencode",
        "run",
        "-m",
        "stepfun/step-3.7-flash",
    ]
    assert len(state["runs"]) == 2
    assert "/go 编码智能体" in html
    assert "目标字节数" in html
    assert "<code>24</code>" in html
    assert "状态命令" in html
    assert "执行命令" in html
    assert "devframe code status" in html
    assert "devframe code execute" in html
    assert result.go_run_id in html
    assert "packages/control-plane/control_plane/go_dispatch.py" in html
    assert "opencode run -m stepfun/step-3.7-flash" in html
    assert "Prepared" in html
    assert "状态: Prepared" in html
    assert "任务规格: Ready" in html


def test_devframe_cli_exports_visual_state_json(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    rdgoal(
        orchestrator,
        project_root,
        "Build a working MVP prototype.",
        operation="choose architecture direction",
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "visual-state",
        "--runtime-dir",
        str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out
    state = json.loads(output)

    assert exit_code == 0
    validate_schema("schemas/visual_control_plane_state.schema.json", state)
    assert state["projects"][0]["project_id"] == "project"
    assert state["runs"][0]["status"] == "pending"
    assert state["runs"][0]["taskspec_path"].endswith("TASKSPEC.md")
    assert state["runs"][0]["next_command"].startswith("rdgoal worker ")


def test_devframe_cli_shows_action_queue_text(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    rdgoal(
        orchestrator,
        project_root,
        "Build a working MVP prototype.",
        operation="choose architecture direction",
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "actions",
        "--runtime-dir",
        str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Action Queue" in output
    assert "id: human-gate-action" in output
    assert "resume: devframe actions --action-id human-gate-action --format markdown" in output
    assert "human-gate" in output
    assert "rdgoal worker " in output


def test_devframe_cli_exports_action_queue_json_with_paper_project(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    paper_root = make_paper_project(tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "actions",
        "--runtime-dir",
        str(runtime_dir),
        "--paper-project",
        str(paper_root),
        "--format",
        "json",
    ])

    exit_code = devframe_cli_main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert "next_actions" in payload
    assert any(
        action["source_id"] == "demo-paper-deepseek-web-safety-gate"
        for action in payload["next_actions"]
    )
    provider_action = next(
        action
        for action in payload["next_actions"]
        if action["source_id"] == "demo-paper-deepseek-web-safety-gate"
    )
    assert provider_action["status"] == "open"
    assert "manual fallback" in provider_action["label"]


def test_devframe_cli_filters_action_queue_and_writes_output(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    paper_root = make_paper_project(tmp_path)
    output_path = tmp_path / "actions.json"
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "actions",
        "--runtime-dir",
        str(runtime_dir),
        "--paper-project",
        str(paper_root),
        "--status",
        "ready",
        "--source-type",
        "run",
        "--format",
        "json",
        "--output",
        str(output_path),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "Wrote json action queue" in output
    assert len(payload["next_actions"]) == 1
    assert payload["next_actions"][0]["source_id"] == "demo-paper-paper-review"
    assert payload["next_actions"][0]["source_type"] == "run"


def test_devframe_cli_filters_action_queue_by_source_id(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    paper_root = make_paper_project(tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "actions",
        "--runtime-dir",
        str(runtime_dir),
        "--paper-project",
        str(paper_root),
        "--source-id",
        "demo-paper-paper-review",
        "--format",
        "json",
    ])

    exit_code = devframe_cli_main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert len(payload["next_actions"]) == 1
    assert payload["next_actions"][0]["source_id"] == "demo-paper-paper-review"


def test_devframe_cli_rejects_unknown_action_filter_id(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    paper_root = make_paper_project(tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "actions",
        "--runtime-dir",
        str(runtime_dir),
        "--paper-project",
        str(paper_root),
        "--source-id",
        "missing-run",
    ])

    exit_code = devframe_cli_main()
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "Invalid action filters" in captured.err
    assert "missing-run" in captured.err


def test_devframe_cli_exports_action_queue_markdown_handoff(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    paper_root = make_paper_project(tmp_path)
    output_path = tmp_path / "ACTION_QUEUE.md"
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "actions",
        "--runtime-dir",
        str(runtime_dir),
        "--paper-project",
        str(paper_root),
        "--status",
        "ready",
        "--source-type",
        "run",
        "--format",
        "markdown",
        "--output",
        str(output_path),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out
    markdown = output_path.read_text(encoding="utf-8")

    assert exit_code == 0
    assert "Wrote markdown action queue" in output
    assert "# Action Queue Handoff" in markdown
    assert "Read-only queue for manual resume" in markdown
    assert "- Action ID: `demo-paper-paper-review-command-action`" in markdown
    assert (
        "- Resume Filter: `devframe actions --action-id "
        "demo-paper-paper-review-command-action --format markdown`"
    ) in markdown
    assert "demo-paper-paper-review" in markdown
    assert "devframe run --pipeline" in markdown
    assert "```powershell" in markdown


def test_devframe_cli_action_queue_fail_on_match_is_read_only_gate(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    paper_root = make_paper_project(tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "actions",
        "--runtime-dir",
        str(runtime_dir),
        "--paper-project",
        str(paper_root),
        "--status",
        "open",
        "--source-type",
        "gate",
        "--fail-on-match",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Action Queue" in output
    assert "id: demo-paper-deepseek-web-safety-gate-action" in output
    assert "demo-paper-deepseek-web-safety-gate" in output
    assert "manual fallback" in output


def test_devframe_cli_exports_visual_state_html_file(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    output_path = tmp_path / "visual-state.html"
    project_root.mkdir()
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    rdgoal(
        orchestrator,
        project_root,
        "Build a working MVP prototype.",
        operation="choose architecture direction",
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "visual-state",
        "--runtime-dir",
        str(runtime_dir),
        "--format",
        "html",
        "--output",
        str(output_path),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out
    html = output_path.read_text(encoding="utf-8")

    assert exit_code == 0
    assert "Wrote html visual state" in output
    assert "<title>DevFrame Visual Control Plane</title>" in html
    assert "Visual State Snapshot" in html
    assert "Gate Focus" in html
    assert "human-gate" in html
    assert "Run Details" in html
    assert "<dt>Current Decision</dt>" in html
    assert "continue / selected" in html
    assert "Run a worker against the dispatch packet." in html
    assert "TASKSPEC.md" in html
    assert "rdgoal worker" in html
    assert "Build a working MVP prototype." in html
    assert "<th>Action ID</th>" in html
    assert "human-gate-action" in html
    assert "<th>Resume Filter</th>" in html
    assert "<strong>Action ID</strong><code>human-gate-action</code>" in html
    assert (
        "<strong>Resume filter</strong><code>"
        "devframe actions --action-id human-gate-action --format markdown</code>"
    ) in html
    assert "<strong>Handoff</strong>" not in html
    assert "devframe actions --action-id human-gate-action --format markdown" in html
    assert 'href="/actions.md"' not in html


def test_visual_state_html_escapes_runtime_text(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    rdgoal(
        orchestrator,
        project_root,
        "Build <script>alert(1)</script>",
        operation="choose architecture direction",
    )

    html = render_visual_control_plane_state_html(build_visual_control_plane_state(runtime_dir))

    assert "<script>alert(1)</script>" not in html
    assert "Build &lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_dashboard_server_serves_html_and_state_json_read_only(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    rdgoal(
        orchestrator,
        project_root,
        "Build a working MVP prototype.",
        operation="choose architecture direction",
    )
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=1)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with urlopen(f"{base_url}/", timeout=5) as response:
            html = response.read().decode("utf-8")
        with urlopen(f"{base_url}/state.json", timeout=5) as response:
            state = json.loads(response.read().decode("utf-8"))
        with urlopen(f"{base_url}/actions.json?status=open&source_type=gate", timeout=5) as response:
            actions_payload = json.loads(response.read().decode("utf-8"))
        with urlopen(f"{base_url}/actions.json?source-type=gate", timeout=5) as response:
            alias_actions_payload = json.loads(response.read().decode("utf-8"))
        with urlopen(f"{base_url}/actions.md?status=open&source_type=gate", timeout=5) as response:
            actions_markdown = response.read().decode("utf-8")

        assert response.status == 200
        assert '<meta http-equiv="refresh" content="1">' in html
        assert "Visual State Snapshot" in html
        assert "Gate Focus" in html
        assert "human-gate" in html
        assert "Run Details" in html
        assert "<dt>Current Decision</dt>" in html
        assert "continue / selected" in html
        assert "Run a worker against the dispatch packet." in html
        assert "TASKSPEC.json" in html
        assert "rdgoal worker" in html
        assert "Build a working MVP prototype." in html
        assert "<th>Provider</th>" in html
        assert "<th>Binding Health</th>" in html
        assert "chatgpt" in html
        assert "unknown" in html
        assert 'href="/state.json"' in html
        assert 'href="/actions.json"' in html
        assert 'href="/actions.md"' in html
        assert 'href="/actions.md?action_id=human-gate-action"' in html
        assert (
            '<strong>Handoff</strong><a class="row-link" '
            'href="/actions.md?action_id=human-gate-action">Markdown</a>'
        ) in html
        assert "<th>Action ID</th>" in html
        assert "<code>human-gate-action</code>" in html
        assert "<th>Resume Filter</th>" in html
        assert "devframe actions --action-id human-gate-action --format markdown" in html
        validate_schema("schemas/visual_control_plane_state.schema.json", state)
        assert state["projects"][0]["project_id"] == "project"
        assert state["runs"][0]["status"] == "pending"
        assert state["runs"][0]["packet_path"]
        assert state["runs"][0]["next_command"].startswith("rdgoal worker ")
        assert actions_payload["next_actions"][0]["source_id"] == "human-gate"
        assert actions_payload["next_actions"][0]["source_type"] == "gate"
        assert alias_actions_payload["next_actions"][0]["source_type"] == "gate"
        assert "# Action Queue Handoff" in actions_markdown
        assert "human-gate" in actions_markdown
        assert "Read-only queue for manual resume" in actions_markdown

        try:
            urlopen(Request(f"{base_url}/actions.json", method="POST"), timeout=5)
        except HTTPError as error:
            assert error.code == 405
        else:
            raise AssertionError("dashboard accepted a write request")
        try:
            urlopen(Request(f"{base_url}/actions.json", method="PATCH"), timeout=5)
        except HTTPError as error:
            assert error.code == 405
        else:
            raise AssertionError("dashboard accepted a write request")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_actions_endpoint_rejects_invalid_filters(tmp_path):
    runtime_dir = tmp_path / "runtime"
    paper_root = make_paper_project(tmp_path)
    server = build_dashboard_server(
        runtime_dir=runtime_dir,
        paper_project_dirs=[paper_root],
        port=0,
        refresh_seconds=0,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        try:
            urlopen(f"{base_url}/actions.json?status=typo&source_type=runner", timeout=5)
        except HTTPError as error:
            payload = json.loads(error.read().decode("utf-8"))
            assert error.code == 400
        else:
            raise AssertionError("dashboard accepted invalid action filters")

        assert payload["error"] == "invalid action filter"
        assert payload["invalid"] == {"status": ["typo"], "source_type": ["runner"]}
        assert "open" in payload["allowed"]["status"]
        assert "run" in payload["allowed"]["source_type"]

        try:
            urlopen(f"{base_url}/actions.md?priority=urgent", timeout=5)
        except HTTPError as error:
            payload = json.loads(error.read().decode("utf-8"))
            assert error.code == 400
        else:
            raise AssertionError("dashboard accepted invalid markdown action filters")

        assert payload["invalid"] == {"priority": ["urgent"]}

        try:
            urlopen(f"{base_url}/actions.json?source_id=missing-run", timeout=5)
        except HTTPError as error:
            payload = json.loads(error.read().decode("utf-8"))
            assert error.code == 400
        else:
            raise AssertionError("dashboard accepted invalid source_id filter")

        assert payload["invalid"] == {"source_id": ["missing-run"]}
        assert "demo-paper-paper-review" in payload["allowed"]["source_id"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def make_paper_project(tmp_path: Path) -> Path:
    paper_root = tmp_path / "paper-project"
    paper_root.mkdir()
    (paper_root / "PAPER_PROFILE.yaml").write_text(
        "\n".join([
            "paper_id: demo-paper",
            "title: Demo Paper",
            "current_iteration: 1",
            "current_stage: drafting",
        ]),
        encoding="utf-8",
    )
    (paper_root / "PAPER_STATE.yaml").write_text(
        "\n".join([
            "paper_id: demo-paper",
            "current_iteration: 1",
            "current_stage: drafting",
            "status: initialized",
            "next_stage: review_requested",
        ]),
        encoding="utf-8",
    )
    (paper_root / "PAPER_LEDGER.md").write_text("# Paper Ledger\n", encoding="utf-8")
    (paper_root / "PAPER_NEXT_TASK.md").write_text("# Next Task\n\nPrepare review packet.\n", encoding="utf-8")
    (paper_root / "PAPER_REVIEW_SPEC.md").write_text("# Paper Review Spec\n", encoding="utf-8")
    (paper_root / "WEB_AI_ADAPTER.yaml").write_text(
        "\n".join([
            "version: 1",
            "browser:",
            "  provider: chrome",
            "  mode: cdp",
            "  profile_policy: user_selected",
            "  endpoint: http://127.0.0.1:9222",
            "web_ai:",
            "  provider: deepseek",
            "  url: https://chat.deepseek.com/",
            "  submit_strategy: textarea_submit",
            "  response_strategy: latest_assistant_message",
            "  capabilities:",
            "    file_upload: none",
            "    markdown_response: true",
            "    manual_login_required: true",
            "safety:",
            "  persist_raw_transcript: false",
            "  allow_real_paper_full_text: false",
            "  allow_pdf_upload: false",
            "  allow_browser_profile_export: false",
            "  human_gate_required_for:",
            "    - real_paper_full_text",
            "manual_fallback:",
            "  enabled: true",
            "  instructions:",
            "    - Paste minimized prompt manually when automation is unavailable.",
        ]),
        encoding="utf-8",
    )
    paper_task = paper_root / "paper_task"
    paper_task.mkdir()
    (paper_task / "PAPER_TASK_INPUT.yaml").write_text("task_type: cssci_review\n", encoding="utf-8")
    (paper_task / "PRIVACY_ATTESTATION.yaml").write_text(
        "contains_real_paper_full_text: false\n",
        encoding="utf-8",
    )
    return paper_root


def test_visual_state_includes_paper_project_workspace(tmp_path):
    runtime_dir = tmp_path / "runtime"
    paper_root = make_paper_project(tmp_path)

    state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=[paper_root])

    validate_schema("schemas/visual_control_plane_state.schema.json", state)
    assert state["projects"][0]["project_id"] == "demo-paper"
    assert state["runs"][0]["entrypoint"] == "rdpaper"
    assert state["runs"][0]["task_input_path"].endswith("PAPER_TASK_INPUT.yaml")
    assert state["runs"][0]["next_command"].startswith("devframe run --pipeline")
    assert any(agent["role"] == "paper_reviewer" for agent in state["agents"])
    paper_binding = next(binding for binding in state["provider_bindings"] if binding["provider"] == "deepseek")
    assert paper_binding["binding_id"] == "demo-paper-deepseek-web"
    assert paper_binding["mode"] == "browser_cdp"
    assert paper_binding["health"] == "needs_login"
    assert paper_binding["adapter_config_path"].endswith("WEB_AI_ADAPTER.yaml")
    assert paper_binding["manual_fallback_instructions"] == [
        "Paste minimized prompt manually when automation is unavailable.",
    ]
    assert "manual_fallback_enabled" in paper_binding["notes"]
    paper_agent = next(agent for agent in state["agents"] if agent["binding_id"] == "demo-paper-deepseek-web")
    assert paper_agent["status"] == "needs_human"
    privacy_gate = next(gate for gate in state["gates"] if gate["kind"] == "privacy")
    assert privacy_gate["status"] == "pass"
    provider_gate = next(gate for gate in state["gates"] if gate["gate_id"] == "demo-paper-deepseek-web-safety-gate")
    assert provider_gate["kind"] == "safety"
    assert provider_gate["status"] == "open"
    assert "manual login" in provider_gate["reason"]
    assert "manual fallback" in provider_gate["next_action"]
    provider_action = next(action for action in state["next_actions"] if action["source_id"] == provider_gate["gate_id"])
    assert provider_action["status"] == "open"
    assert provider_action["priority"] == "medium"
    assert "manual fallback" in provider_action["label"]
    assert state["decisions"][0]["next_action"].startswith("Complete the provider safety gate")


def test_visual_state_blocks_unsafe_paper_adapter(tmp_path):
    runtime_dir = tmp_path / "runtime"
    paper_root = make_paper_project(tmp_path)
    adapter_path = paper_root / "WEB_AI_ADAPTER.yaml"
    adapter_path.write_text(
        adapter_path.read_text(encoding="utf-8").replace(
            "allow_pdf_upload: false",
            "allow_pdf_upload: true",
        ),
        encoding="utf-8",
    )

    state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=[paper_root])
    html = render_visual_control_plane_state_html(state)

    paper_binding = next(binding for binding in state["provider_bindings"] if binding["provider"] == "deepseek")
    assert paper_binding["health"] == "blocked"
    paper_agent = next(agent for agent in state["agents"] if agent["binding_id"] == "demo-paper-deepseek-web")
    assert paper_agent["status"] == "blocked"
    provider_gate = next(gate for gate in state["gates"] if gate["gate_id"] == "demo-paper-deepseek-web-safety-gate")
    assert provider_gate["status"] == "blocked"
    assert "unsafe paper data flow" in provider_gate["reason"]
    assert "raw transcript persistence" in provider_gate["next_action"]
    assert "Gate Focus" in html
    assert "demo-paper-deepseek-web-safety-gate" in html
    assert "unsafe paper data flow" in html
    assert (
        "<strong>Action ID</strong><code>"
        "demo-paper-deepseek-web-safety-gate-action</code>"
    ) in html
    provider_action = next(action for action in state["next_actions"] if action["source_id"] == provider_gate["gate_id"])
    assert provider_action["status"] == "blocked"
    assert provider_action["priority"] == "high"
    assert state["decisions"][0]["status"] == "blocked"
    assert state["decisions"][0]["next_action"] == provider_gate["next_action"]


def test_visual_state_uses_folder_name_for_unrendered_paper_template(tmp_path):
    runtime_dir = tmp_path / "runtime"
    paper_root = tmp_path / "paper-project"
    shutil.copytree(REPO_ROOT / "packages" / "control-plane" / "templates" / "paper_iteration", paper_root)

    state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=[paper_root])

    validate_schema("schemas/visual_control_plane_state.schema.json", state)
    paper_project = next(project for project in state["projects"] if project["project_id"] == "paper-project")
    assert paper_project["display_name"] == "paper-project"
    assert "{{PAPER_TITLE}}" not in paper_project["goal"]
    paper_binding = next(binding for binding in state["provider_bindings"] if binding["binding_id"] == "paper-project-chatgpt-web")
    assert paper_binding["health"] == "needs_login"
    provider_gate = next(gate for gate in state["gates"] if gate["gate_id"] == "paper-project-chatgpt-web-safety-gate")
    assert provider_gate["status"] == "open"
    assert "manual fallback" in provider_gate["next_action"]
    assert any(action["source_id"] == provider_gate["gate_id"] for action in state["next_actions"])


def test_devframe_cli_exports_visual_state_with_paper_project(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    paper_root = make_paper_project(tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "visual-state",
        "--runtime-dir",
        str(runtime_dir),
        "--paper-project",
        str(paper_root),
    ])

    exit_code = devframe_cli_main()
    state = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    validate_schema("schemas/visual_control_plane_state.schema.json", state)
    assert state["runs"][0]["entrypoint"] == "rdpaper"
    assert state["decisions"][0]["next_action"].startswith("Complete the provider safety gate")


def test_dashboard_server_serves_paper_project_details(tmp_path):
    runtime_dir = tmp_path / "runtime"
    paper_root = make_paper_project(tmp_path)
    server = build_dashboard_server(
        runtime_dir=runtime_dir,
        paper_project_dirs=[paper_root],
        port=0,
        refresh_seconds=0,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with urlopen(f"{base_url}/", timeout=5) as response:
            html = response.read().decode("utf-8")
        with urlopen(f"{base_url}/state.json", timeout=5) as response:
            state = json.loads(response.read().decode("utf-8"))
        with urlopen(f"{base_url}/actions.json?status=ready&source_type=run", timeout=5) as response:
            actions_payload = json.loads(response.read().decode("utf-8"))
        with urlopen(f"{base_url}/actions.md?status=ready&source_type=run", timeout=5) as response:
            actions_markdown = response.read().decode("utf-8")
        with urlopen(f"{base_url}/actions.json?action_id=demo-paper-paper-review-command-action", timeout=5) as response:
            single_action_payload = json.loads(response.read().decode("utf-8"))
        with urlopen(f"{base_url}/actions.md?action_id=demo-paper-paper-review-command-action", timeout=5) as response:
            single_action_markdown = response.read().decode("utf-8")

        assert "Demo Paper" in html
        assert "Gate Focus" in html
        assert "demo-paper-privacy-gate" in html
        assert "demo-paper-deepseek-web-safety-gate" in html
        assert (
            "<strong>Action ID</strong><code>"
            "demo-paper-deepseek-web-safety-gate-action</code>"
        ) in html
        assert (
            '<strong>Handoff</strong><a class="row-link" '
            'href="/actions.md?action_id=demo-paper-deepseek-web-safety-gate-action">'
            "Markdown</a>"
        ) in html
        assert "Action Queue" in html
        assert "Provider Bindings" in html
        assert "<th>Provider</th>" in html
        assert "<th>Binding Health</th>" in html
        assert "paper-reviewer-demo-paper-deepseek-web" in html
        assert "deepseek" in html
        assert "needs_login" in html
        assert "manual login" in html
        assert "manual fallback" in html
        assert "Manual Fallback" in html
        assert "Paste minimized prompt manually when automation is unavailable." in html
        assert "rdpaper" in html
        assert "<dt>Current Decision</dt>" in html
        assert "demo-paper-paper-decision" in html
        assert "continue / selected" in html
        assert (
            "Complete the provider safety gate, then prepare the "
            "privacy-safe paper task packet."
        ) in html
        assert "PAPER_TASK_INPUT.yaml" in html
        assert "privacy" in html
        assert "<th>Action ID</th>" in html
        assert "<code>demo-paper-paper-review-command-action</code>" in html
        assert "<th>Resume Filter</th>" in html
        assert (
            "devframe actions --action-id "
            "demo-paper-paper-review-command-action --format markdown"
        ) in html
        assert state["runs"][0]["entrypoint"] == "rdpaper"
        assert any(binding["provider"] == "deepseek" for binding in state["provider_bindings"])
        assert len(actions_payload["next_actions"]) == 1
        assert actions_payload["next_actions"][0]["source_id"] == "demo-paper-paper-review"
        assert actions_payload["next_actions"][0]["source_type"] == "run"
        assert len(single_action_payload["next_actions"]) == 1
        assert single_action_payload["next_actions"][0]["action_id"] == "demo-paper-paper-review-command-action"
        assert "# Action Queue Handoff" in actions_markdown
        assert "- Action ID: `demo-paper-paper-review-command-action`" in actions_markdown
        assert (
            "- Resume Filter: `devframe actions --action-id "
            "demo-paper-paper-review-command-action --format markdown`"
        ) in actions_markdown
        assert "demo-paper-paper-review" in actions_markdown
        assert "devframe run --pipeline" in actions_markdown
        assert "# Action Queue Handoff" in single_action_markdown
        assert "- Action ID: `demo-paper-paper-review-command-action`" in single_action_markdown
        assert (
            "- Resume Filter: `devframe actions --action-id "
            "demo-paper-paper-review-command-action --format markdown`"
        ) in single_action_markdown
        assert "demo-paper-paper-review" in single_action_markdown
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_devframe_dashboard_unknown_subcommand_returns_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "dashboard", "open"])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Unknown dashboard subcommand: open" in output


def test_devframe_dashboard_rejects_remote_bind_without_explicit_flag(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "dashboard", "serve", "--host", "0.0.0.0"])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "--allow-remote" in output


def test_local_dry_run_worker_blocks_draft_only_packet(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    contract_path = write_contract(tmp_path)

    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    orchestrator.register(contract_path, project_root)
    result = orchestrator.dispatch(
        project_id="demo-project",
        requirement="Build a working MVP prototype.",
        operation="publish production release",
    )

    worker_result = LocalDryRunWorker(runtime_dir=runtime_dir).run_packet(result.packet.packet_dir)

    assert result.dispatch_ready is False
    assert worker_result.summary.status == "blocked"


def test_command_worker_runs_command_and_ingests_report(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    contract_path = write_contract(tmp_path)

    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    orchestrator.register(contract_path, project_root)
    result = orchestrator.dispatch(
        project_id="demo-project",
        requirement="Build a working MVP prototype.",
        operation="choose architecture direction",
    )
    command = [
        sys.executable,
        "-c",
        (
            "import os, pathlib; "
            "assert pathlib.Path(os.environ['RDGOAL_TASKSPEC_JSON']).exists(); "
            "pathlib.Path(os.environ['RDGOAL_REPORT_PATH']).write_text("
            "'## ExecutionReport: command\\n\\n- **Status**: pass\\n- **Changed Files**:\\n- `src/app.py`\\n- **Evidence**: command ok\\n',"
            "encoding='utf-8')"
        ),
    ]

    worker_result = CommandWorker(runtime_dir=runtime_dir).run_packet(result.packet.packet_dir, command)

    assert worker_result.summary.status == "passed"
    assert worker_result.summary.changed_files == ["src/app.py"]
    assert (Path(result.packet.packet_dir) / "worker-output.txt").exists()


def test_command_worker_failed_command_is_not_fake_green(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    contract_path = write_contract(tmp_path)

    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    orchestrator.register(contract_path, project_root)
    result = orchestrator.dispatch(
        project_id="demo-project",
        requirement="Build a working MVP prototype.",
        operation="choose architecture direction",
    )
    command = [sys.executable, "-c", "raise SystemExit(7)"]

    worker_result = CommandWorker(runtime_dir=runtime_dir).run_packet(result.packet.packet_dir, command)

    assert worker_result.summary.status == "failed"
    assert "exited 7" in Path(worker_result.report_path).read_text(encoding="utf-8")


def test_command_worker_resolves_executable_before_running(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    contract_path = write_contract(tmp_path)

    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    orchestrator.register(contract_path, project_root)
    result = orchestrator.dispatch(
        project_id="demo-project",
        requirement="Build a working MVP prototype.",
        operation="choose architecture direction",
    )
    monkeypatch.setattr(
        "control_plane.worker.shutil.which",
        lambda name: sys.executable if name == "python-alias" else None,
    )
    command = [
        "python-alias",
        "-c",
        (
            "import os, pathlib; "
            "pathlib.Path(os.environ['RDGOAL_REPORT_PATH']).write_text("
            "'## ExecutionReport: command\\n\\n- **Status**: pass\\n- **Evidence**: resolved executable\\n',"
            "encoding='utf-8')"
        ),
    ]

    worker_result = CommandWorker(runtime_dir=runtime_dir).run_packet(result.packet.packet_dir, command)

    assert worker_result.summary.status == "passed"
    assert "resolved executable" in worker_result.summary.verification


def test_command_worker_missing_executable_is_reported(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    contract_path = write_contract(tmp_path)

    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    orchestrator.register(contract_path, project_root)
    result = orchestrator.dispatch(
        project_id="demo-project",
        requirement="Build a working MVP prototype.",
        operation="choose architecture direction",
    )

    worker_result = CommandWorker(runtime_dir=runtime_dir).run_packet(
        result.packet.packet_dir,
        ["definitely-missing-devframe-worker-command"],
    )

    packet_dir = Path(result.packet.packet_dir)
    assert worker_result.summary.status == "failed"
    assert "could not start" in Path(worker_result.report_path).read_text(encoding="utf-8")
    assert "FAILED TO START" in (packet_dir / "worker-output.txt").read_text(encoding="utf-8")


def test_command_worker_does_not_run_held_packet(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    contract_path = write_contract(tmp_path)

    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    orchestrator.register(contract_path, project_root)
    result = orchestrator.dispatch(
        project_id="demo-project",
        requirement="Build a working MVP prototype.",
        operation="publish production release",
    )
    marker = project_root / "should-not-exist.txt"
    command = [
        sys.executable,
        "-c",
        f"from pathlib import Path; Path({str(marker)!r}).write_text('ran', encoding='utf-8')",
    ]

    worker_result = CommandWorker(runtime_dir=runtime_dir).run_packet(result.packet.packet_dir, command)

    assert worker_result.summary.status == "blocked"
    assert not marker.exists()


def test_worker_cli_returns_nonzero_for_blocked_command_packet(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    contract_path = write_contract(tmp_path)

    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    orchestrator.register(contract_path, project_root)
    result = orchestrator.dispatch(
        project_id="demo-project",
        requirement="Build a working MVP prototype.",
        operation="publish production release",
    )
    marker = project_root / "should-not-exist.txt"

    exit_code = rdgoal_cli_main([
        "worker",
        result.packet.packet_dir,
        "--runtime-dir",
        str(runtime_dir),
        "--command",
        sys.executable,
        "-c",
        f"from pathlib import Path; Path({str(marker)!r}).write_text('ran', encoding='utf-8')",
    ])

    assert exit_code == 1
    assert not marker.exists()


def test_worker_cli_returns_nonzero_for_blocked_local_dry_run_packet(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    contract_path = write_contract(tmp_path)

    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    orchestrator.register(contract_path, project_root)
    result = orchestrator.dispatch(
        project_id="demo-project",
        requirement="Build a working MVP prototype.",
        operation="publish production release",
    )

    exit_code = rdgoal_cli_main([
        "worker",
        result.packet.packet_dir,
        "--runtime-dir",
        str(runtime_dir),
    ])

    assert exit_code == 1


def test_worker_cli_returns_nonzero_for_failed_command(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    contract_path = write_contract(tmp_path)

    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    orchestrator.register(contract_path, project_root)
    result = orchestrator.dispatch(
        project_id="demo-project",
        requirement="Build a working MVP prototype.",
        operation="choose architecture direction",
    )

    exit_code = rdgoal_cli_main([
        "worker",
        result.packet.packet_dir,
        "--runtime-dir",
        str(runtime_dir),
        "--command",
        sys.executable,
        "-c",
        "raise SystemExit(9)",
    ])

    assert exit_code == 1


def test_devframe_cli_exposes_rdgoal(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    contracts_dir = tmp_path / "contracts"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "rdgoal",
        str(project_root),
        "Build a working MVP prototype.",
        "--runtime-dir",
        str(runtime_dir),
        "--contracts-dir",
        str(contracts_dir),
    ])

    exit_code = devframe_cli_main()

    assert exit_code == 0
    assert (contracts_dir / "project.md").exists()
    assert list((runtime_dir / "rdgoal-outbox" / "project").glob("rdgoal-project-*"))


def test_aihub_go_worker_invokes_taskspec_json(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    contract_path = write_contract(tmp_path)
    fake_module = tmp_path / "fake_aihub.py"
    fake_module.write_text(
        "\n".join([
            "import os, sys",
            "from pathlib import Path",
            "Path(os.environ['RDGOAL_PACKET_DIR'], 'argv.txt').write_text(' '.join(sys.argv), encoding='utf-8')",
            "Path(os.environ['RDGOAL_REPORT_PATH']).write_text(",
            "    '## ExecutionReport: aihub\\n\\n- **Status**: pass\\n- **Changed Files**:\\n- `src/app.py`\\n- **Evidence**: fake aihub ok\\n',",
            "    encoding='utf-8'",
            ")",
        ]),
        encoding="utf-8",
    )
    existing_pythonpath = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv(
        "PYTHONPATH",
        str(tmp_path) + (os.pathsep + existing_pythonpath if existing_pythonpath else ""),
    )

    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    orchestrator.register(contract_path, project_root)
    result = orchestrator.dispatch(
        project_id="demo-project",
        requirement="Build a working MVP prototype.",
        operation="choose architecture direction",
    )

    worker_result = AihubGoWorker(runtime_dir=runtime_dir).run_packet(
        result.packet.packet_dir,
        python_executable=sys.executable,
        module_name="fake_aihub",
    )
    argv_text = (Path(result.packet.packet_dir) / "argv.txt").read_text(encoding="utf-8")

    assert worker_result.summary.status == "passed"
    assert "TASKSPEC.json" in argv_text
    assert "--project demo-project" in argv_text
    assert "--dry-run" in argv_text


def test_worker_cli_returns_nonzero_for_failed_aihub_go(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    contract_path = write_contract(tmp_path)
    fake_module = tmp_path / "fake_fail_aihub.py"
    fake_module.write_text("raise SystemExit(5)\n", encoding="utf-8")
    existing_pythonpath = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv(
        "PYTHONPATH",
        str(tmp_path) + (os.pathsep + existing_pythonpath if existing_pythonpath else ""),
    )

    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    orchestrator.register(contract_path, project_root)
    result = orchestrator.dispatch(
        project_id="demo-project",
        requirement="Build a working MVP prototype.",
        operation="choose architecture direction",
    )

    exit_code = rdgoal_cli_main([
        "worker",
        result.packet.packet_dir,
        "--runtime-dir",
        str(runtime_dir),
        "--aihub-go",
        "--python",
        sys.executable,
        "--aihub-module",
        "fake_fail_aihub",
    ])

    assert exit_code == 1


def test_render_visual_control_plane_html_defaults_to_english(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    rdgoal(
        orchestrator,
        project_root,
        "Build a working MVP prototype.",
        operation="choose architecture direction",
    )

    html = render_visual_control_plane_state_html(build_visual_control_plane_state(runtime_dir))

    assert '<html lang="en">' in html
    assert "<title>DevFrame Visual Control Plane</title>" in html
    assert "Visual State Snapshot" in html
    assert "Gate Focus" in html
    assert "Action Queue" in html
    assert "Run Details" in html
    assert "Safety Defaults" in html
    assert 'aria-label="Language"' in html
    assert '<a class="active" aria-current="true" href="?lang=en">English</a>' in html
    assert "中文" in html
    assert 'href="?lang=en"' in html
    assert '?lang=zh-CN' in html


def test_render_visual_control_plane_html_renders_chinese_when_lang_zh_cn(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    rdgoal(
        orchestrator,
        project_root,
        "Build a working MVP prototype.",
        operation="choose architecture direction",
    )

    html = render_visual_control_plane_state_html(
        build_visual_control_plane_state(runtime_dir),
        endpoint_links=True,
        lang="zh-CN",
    )

    assert '<html lang="zh-CN">' in html
    assert "<title>DevFrame 可视化控制面</title>" in html
    assert "可视化状态快照" in html
    assert "门控聚焦" in html
    assert "动作队列" in html
    assert "运行详情" in html
    assert "安全默认值" in html
    assert "动作交接" in html
    assert "智能体" in html
    assert 'aria-label="语言"' in html
    assert '<a class="active" aria-current="true" href="?lang=zh-CN">中文</a>' in html
    assert "English" in html
    assert '?lang=en' in html
    assert '?lang=zh-CN' in html
    assert "DevFrame Visual Control Plane" not in html
    assert "Visual State Snapshot" not in html


def test_render_visual_control_plane_html_invalid_lang_falls_back_to_english(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    rdgoal(
        orchestrator,
        project_root,
        "Build a working MVP prototype.",
        operation="choose architecture direction",
    )

    html = render_visual_control_plane_state_html(
        build_visual_control_plane_state(runtime_dir),
        lang="fr",
    )

    assert '<html lang="en">' in html
    assert "<title>DevFrame Visual Control Plane</title>" in html
    assert "Visual State Snapshot" in html
    assert '?lang=zh-CN' in html


def test_dashboard_server_serves_chinese_html_with_lang_switch(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    rdgoal(
        orchestrator,
        project_root,
        "Build a working MVP prototype.",
        operation="choose architecture direction",
    )
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with urlopen(f"{base_url}/?lang=zh-CN", timeout=5) as response:
            html = response.read().decode("utf-8")

        assert '<html lang="zh-CN">' in html
        assert "<title>DevFrame 可视化控制面</title>" in html
        assert "可视化状态快照" in html
        assert "门控聚焦" in html
        assert "动作队列" in html
        assert "运行详情" in html
        assert "English" in html
        assert 'href="?lang=en"' in html
        assert '<a class="active" aria-current="true" href="?lang=zh-CN">中文</a>' in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_server_serves_english_by_default(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    rdgoal(
        orchestrator,
        project_root,
        "Build a working MVP prototype.",
        operation="choose architecture direction",
    )
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with urlopen(f"{base_url}/", timeout=5) as response:
            html = response.read().decode("utf-8")

        assert '<html lang="en">' in html
        assert "<title>DevFrame Visual Control Plane</title>" in html
        assert "Visual State Snapshot" in html
        assert "中文" in html
        assert '<a class="active" aria-current="true" href="?lang=en">English</a>' in html
        assert '?lang=zh-CN' in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_html_preserves_lang_in_action_links(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    rdgoal(
        orchestrator,
        project_root,
        "Build a working MVP prototype.",
        operation="choose architecture direction",
    )

    html = render_visual_control_plane_state_html(
        build_visual_control_plane_state(runtime_dir),
        endpoint_links=True,
        lang="zh-CN",
    )

    assert 'href="/actions.md?lang=zh-CN"' in html
    assert 'href="/actions.md?action_id=human-gate-action&amp;lang=zh-CN"' in html


def test_dashboard_server_serves_chinese_action_markdown(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    rdgoal(
        orchestrator,
        project_root,
        "Build a working MVP prototype.",
        operation="choose architecture direction",
    )
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with urlopen(f"{base_url}/actions.md?lang=zh-CN", timeout=5) as response:
            markdown = response.read().decode("utf-8")

        assert "# 动作队列交接" in markdown
        assert "用于手动恢复、审查或 Web AI 交接的只读队列。" in markdown
        assert "- 动作 ID: `human-gate-action`" in markdown
        assert "- 优先级: `" in markdown
        assert "- 状态: `" in markdown
        assert "devframe actions --action-id human-gate-action --format markdown" in markdown
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

def test_team_model_projects_terminal_go_run_pass_status_as_review_gate(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    source_dir = project_root / "packages" / "control-plane" / "control_plane"
    source_dir.mkdir(parents=True)
    (source_dir / "cli.py").write_text("c" * 24, encoding="utf-8")
    go_run_id = "go-pass-test"
    go_run_dir = runtime_dir / "go-runs" / go_run_id
    go_run_dir.mkdir(parents=True)
    (go_run_dir / "go-run.json").write_text(json.dumps({
        "go_run_id": go_run_id,
        "project_id": "project",
        "project_root": str(project_root),
        "requirement": "Test terminal passed go-run.",
        "runtime_dir": str(runtime_dir),
        "status": "passed",
        "execute": True,
        "agents": [{
            "agent_id": "coding-agent-1",
            "shard_index": 1,
            "shard_count": 1,
            "targets": ["packages/control-plane/control_plane/cli.py"],
            "target_bytes": 24,
            "packet_dir": str(runtime_dir / "p1"),
            "task_spec_path": str(runtime_dir / "p1" / "TASKSPEC.json"),
            "worker_command": ["opencode", "run"],
            "status": "completed",
            "worker_status": "passed",
            "report_path": str(runtime_dir / "report.md"),
            "changed_files": ["cli.py"],
            "verification": "ok",
        }],
    }, indent=2, ensure_ascii=True), encoding="utf-8")

    state = build_visual_control_plane_state(runtime_dir)

    validate_schema("schemas/visual_control_plane_state.schema.json", state)
    team = state["team"]

    outcome_gates = [g for g in team["review_gates"] if g["kind"] == "go-run-outcome"]
    assert len(outcome_gates) == 1
    assert outcome_gates[0]["gate_id"] == f"{go_run_id}-outcome-gate"
    assert outcome_gates[0]["status"] == "open"
    assert outcome_gates[0]["run_id"] == go_run_id
    assert "independent review is still required" in outcome_gates[0]["reason"]

    execution_messages = [m for m in team["message_bus"] if m["run_id"] == go_run_id
                          and m["kind"] == "execution-status"]
    assert len(execution_messages) >= 1
    assert any("independent review is still required" in m["summary"] for m in execution_messages)


def test_team_model_projects_terminal_go_run_failed_status_as_review_gate(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    source_dir = project_root / "packages" / "control-plane" / "control_plane"
    source_dir.mkdir(parents=True)
    (source_dir / "go_dispatch.py").write_text("g" * 24, encoding="utf-8")
    go_run_id = "go-fail-test"
    go_run_dir = runtime_dir / "go-runs" / go_run_id
    go_run_dir.mkdir(parents=True)
    (go_run_dir / "go-run.json").write_text(json.dumps({
        "go_run_id": go_run_id,
        "project_id": "project",
        "project_root": str(project_root),
        "requirement": "Test terminal failed go-run.",
        "runtime_dir": str(runtime_dir),
        "status": "failed",
        "execute": True,
        "agents": [{
            "agent_id": "coding-agent-1",
            "shard_index": 1,
            "shard_count": 1,
            "targets": ["packages/control-plane/control_plane/go_dispatch.py"],
            "target_bytes": 24,
            "packet_dir": str(runtime_dir / "p1"),
            "task_spec_path": str(runtime_dir / "p1" / "TASKSPEC.json"),
            "worker_command": ["opencode", "run"],
            "status": "failed",
            "worker_status": "failed",
            "changed_files": [],
        }],
    }, indent=2, ensure_ascii=True), encoding="utf-8")

    state = build_visual_control_plane_state(runtime_dir)

    validate_schema("schemas/visual_control_plane_state.schema.json", state)
    team = state["team"]

    outcome_gates = [g for g in team["review_gates"] if g["kind"] == "go-run-outcome"]
    assert len(outcome_gates) == 1
    assert outcome_gates[0]["gate_id"] == f"{go_run_id}-outcome-gate"
    assert outcome_gates[0]["status"] == "failed"
    assert outcome_gates[0]["run_id"] == go_run_id
    assert "failed" in outcome_gates[0]["reason"]

    review_messages = [m for m in team["message_bus"] if m["run_id"] == go_run_id
                       and m["kind"] == "review-status"]
    assert len(review_messages) >= 1
    assert any("failed" in m["summary"] for m in review_messages)


def test_team_model_projects_terminal_go_run_blocked_status_as_review_gate(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    go_run_id = "go-blocked-test"
    go_run_dir = runtime_dir / "go-runs" / go_run_id
    go_run_dir.mkdir(parents=True)
    (go_run_dir / "go-run.json").write_text(json.dumps({
        "go_run_id": go_run_id,
        "project_id": "project",
        "project_root": str(project_root),
        "requirement": "Test terminal blocked go-run.",
        "runtime_dir": str(runtime_dir),
        "status": "blocked",
        "execute": True,
        "agents": [{
            "agent_id": "coding-agent-1",
            "shard_index": 1,
            "shard_count": 1,
            "targets": [],
            "target_bytes": 0,
            "packet_dir": str(runtime_dir / "p1"),
            "task_spec_path": str(runtime_dir / "p1" / "TASKSPEC.json"),
            "worker_command": ["opencode", "run"],
            "status": "blocked",
            "worker_status": "blocked",
            "changed_files": [],
        }],
    }, indent=2, ensure_ascii=True), encoding="utf-8")

    state = build_visual_control_plane_state(runtime_dir)

    validate_schema("schemas/visual_control_plane_state.schema.json", state)
    team = state["team"]

    outcome_gates = [g for g in team["review_gates"] if g["kind"] == "go-run-outcome"]
    assert len(outcome_gates) == 1
    assert outcome_gates[0]["gate_id"] == f"{go_run_id}-outcome-gate"
    assert outcome_gates[0]["status"] == "blocked"
    assert outcome_gates[0]["run_id"] == go_run_id
    assert "blocked" in outcome_gates[0]["reason"]

    review_messages = [m for m in team["message_bus"] if m["run_id"] == go_run_id
                       and m["kind"] == "review-status"]
    assert len(review_messages) >= 1
    assert any("blocked" in m["summary"] for m in review_messages)


def test_team_model_avoids_duplicate_outcome_gates(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    go_run_id = "go-dup-test"
    go_run_dir = runtime_dir / "go-runs" / go_run_id
    go_run_dir.mkdir(parents=True)
    (go_run_dir / "go-run.json").write_text(json.dumps({
        "go_run_id": go_run_id,
        "project_id": "project",
        "project_root": str(project_root),
        "requirement": "Test dedup.",
        "runtime_dir": str(runtime_dir),
        "status": "passed",
        "execute": True,
        "agents": [{
            "agent_id": "coding-agent-1",
            "shard_index": 1,
            "shard_count": 1,
            "targets": [],
            "target_bytes": 0,
            "packet_dir": str(runtime_dir / "p1"),
            "task_spec_path": str(runtime_dir / "p1" / "TASKSPEC.json"),
            "worker_command": ["opencode", "run"],
            "status": "completed",
            "worker_status": "passed",
            "changed_files": [],
        }],
    }, indent=2, ensure_ascii=True), encoding="utf-8")

    state = build_visual_control_plane_state(runtime_dir)

    team = state["team"]
    outcome_gates = [g for g in team["review_gates"] if g["kind"] == "go-run-outcome"]
    assert len(outcome_gates) == 1


def test_t3_shell_exposes_go_run_outcome_gate_and_message_signal(tmp_path):
    from control_plane.t3_adapter import build_t3_client_shell

    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    go_run_id = "go-shell-test"
    go_run_dir = runtime_dir / "go-runs" / go_run_id
    go_run_dir.mkdir(parents=True)
    (go_run_dir / "go-run.json").write_text(json.dumps({
        "go_run_id": go_run_id,
        "project_id": "project",
        "project_root": str(tmp_path / "project"),
        "requirement": "Test T3 shell go-run outcome.",
        "runtime_dir": str(runtime_dir),
        "status": "passed",
        "execute": True,
        "agents": [{
            "agent_id": "coding-agent-1",
            "shard_index": 1,
            "shard_count": 1,
            "targets": [],
            "target_bytes": 0,
            "packet_dir": str(runtime_dir / "p1"),
            "task_spec_path": str(runtime_dir / "p1" / "TASKSPEC.json"),
            "worker_command": ["opencode", "run"],
            "status": "completed",
            "worker_status": "passed",
            "changed_files": [],
        }],
    }, indent=2, ensure_ascii=True), encoding="utf-8")

    shell = build_t3_client_shell(runtime_dir)

    team = shell["devframe"]["team"]
    outcome_gates = [g for g in team["reviewGates"] if g["kind"] == "go-run-outcome"]
    assert len(outcome_gates) == 1
    assert outcome_gates[0]["gateId"] == f"{go_run_id}-outcome-gate"
    assert outcome_gates[0]["status"] == "open"

    execution_messages = [m for m in team["messageBus"] if m["runId"] == go_run_id
                          and m["kind"] == "execution-status"]
    assert len(execution_messages) >= 1


def test_runtime_store_read_all_tolerates_truncated_trailing_line(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    journal_path = runtime_dir / "rdgoal-events.jsonl"
    valid_line = json.dumps({
        "event_type": "project_registered",
        "project_id": "test-project",
        "payload": {"project_root": str(tmp_path)},
        "timestamp": "2026-06-25T00:00:00Z",
        "event_id": "test-project-e1",
    })
    journal_path.write_text(
        valid_line + "\n" + valid_line[:30],
        encoding="utf-8",
    )

    events = RuntimeStore(runtime_dir=runtime_dir).read_all()

    assert len(events) == 1
    assert events[0]["project_id"] == "test-project"


def test_skill_registry_lists_shipped_agent_acceptance():
    skills = list_methodology_skills()

    assert any(skill.get("skill_id") == "agent-acceptance" for skill in skills)
    shipped = next(skill for skill in skills if skill.get("skill_id") == "agent-acceptance")
    assert shipped["title"] == "agent-acceptance"
    assert shipped["source_kind"] == "local_repository_asset"
    assert Path(shipped["source_path"]).parts[-3:] == ("templates", "runtime-bootstrap", "SKILL.md")
    assert shipped["status"] == "registered"
    assert "@go" in shipped.get("triggers", [])


def test_skill_registry_lists_local_tdd_skill():
    skills = list_methodology_skills()

    assert any(skill.get("skill_id") == "tdd" for skill in skills)
    tdd = next(skill for skill in skills if skill.get("skill_id") == "tdd")
    assert tdd["title"] == "tdd"
    assert "skills" in tdd["source_path"] and tdd["source_path"].endswith("SKILL.md")
    assert tdd["source_kind"] == "local_repository_asset"
    assert tdd["status"] == "registered"
    assert "@tdd" in tdd.get("triggers", [])


def test_skill_registry_lists_external_brain_flow_skills():
    skills = {skill.get("skill_id"): skill for skill in list_methodology_skills()}

    assert skills["bind-chrome"]["source_path"].replace("\\", "/") == "tools/skills/bind-chrome/SKILL.md"
    assert "@bind-chrome" in skills["bind-chrome"].get("triggers", [])
    assert skills["external-brain"]["source_path"].replace("\\", "/") == "tools/skills/external-brain/SKILL.md"
    assert "@external-brain" in skills["external-brain"].get("triggers", [])
    assert skills["context-pack-builder"]["source_path"].replace("\\", "/") == "tools/skills/context-pack-builder/SKILL.md"
    assert "@context-pack" in skills["context-pack-builder"].get("triggers", [])
    assert skills["intent-framing-gate"]["source_path"].replace("\\", "/") == "tools/skills/intent-framing-gate/SKILL.md"
    assert "@intent-frame" in skills["intent-framing-gate"].get("triggers", [])


def test_methodology_dispatch_resolves_external_brain_flow_triggers():
    from control_plane.methodology_dispatch import resolve_methodology

    effective, methodology = resolve_methodology("@bind-chrome bind https://chatgpt.com/c/test")
    assert effective == "bind https://chatgpt.com/c/test"
    assert methodology["skill_id"] == "bind-chrome"

    effective, methodology = resolve_methodology("@intent-frame is this directory complete")
    assert effective == "is this directory complete"
    assert methodology["skill_id"] == "intent-framing-gate"


def test_skill_registry_lists_local_tools_skills_if_present(tmp_path, monkeypatch):
    tools_skills = tmp_path / "tools" / "skills" / "tdd"
    tools_skills.mkdir(parents=True)
    (tools_skills / "SKILL.md").write_text(
        "\n".join([
            "---",
            "name: tdd",
            "description: Test-driven development skill triggered by @tdd.",
            "---",
            "",
            "# tdd",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setattr("control_plane.skill_registry.REPO_ROOT", tmp_path)
    skills = list_methodology_skills()

    assert any(skill.get("skill_id") == "tdd" for skill in skills)
    tdd = next(skill for skill in skills if skill.get("skill_id") == "tdd")
    assert tdd["title"] == "tdd"
    assert "skills" in tdd["source_path"] and tdd["source_path"].endswith("SKILL.md")
    assert tdd["status"] == "registered"
    assert "@tdd" in tdd.get("triggers", [])


def test_visual_state_includes_methodology_skills(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    rdgoal(
        orchestrator,
        project_root,
        "Build a working MVP prototype.",
        operation="choose architecture direction",
    )

    state = build_visual_control_plane_state(runtime_dir)

    assert "skills" in state
    assert any(skill.get("skill_id") == "agent-acceptance" for skill in state["skills"])
    html = render_visual_control_plane_state_html(state)
    assert "Methodology Skills" in html
    assert "agent-acceptance" in html


def test_visual_state_projects_methodology_into_go_runs(tmp_path):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    source_dir = project_root / "src"
    source_dir.mkdir(parents=True)
    (source_dir / "app.py").write_text("print('ok')\n", encoding="utf-8")
    go_root = runtime_dir / "go-runs" / "go-project-123"
    go_root.mkdir(parents=True)
    (go_root / "go-run.json").write_text(json.dumps({
        "go_run_id": "go-project-123",
        "project_id": "project",
        "project_root": str(project_root),
        "requirement": "Add a TDD feature.",
        "status": "queued",
        "execute": False,
        "created_at": "2026-06-26T00:00:00Z",
        "metadata_path": str(go_root / "go-run.json"),
        "methodology": {
            "skill_id": "tdd",
            "title": "tdd",
            "source_path": "tools/skills/tdd/SKILL.md",
            "source_kind": "local_repository_asset",
            "triggers": ["@tdd"],
            "status": "registered",
        },
        "agents": [{
            "agent_id": "coding-agent-1",
            "shard_index": 1,
            "shard_count": 1,
            "status": "queued",
            "worker_status": "",
            "methodology": {
                "skill_id": "tdd",
                "title": "tdd",
                "source_path": "tools/skills/tdd/SKILL.md",
                "source_kind": "local_repository_asset",
                "triggers": ["@tdd"],
                "status": "registered",
            },
            "targets": ["src/app.py"],
            "target_bytes": 12,
            "changed_files": [],
            "packet_dir": str(tmp_path / "packet"),
            "task_spec_path": str(tmp_path / "packet" / "TASKSPEC.json"),
            "report_path": "",
            "worker_command": ["opencode", "run"],
        }],
    }, indent=2), encoding="utf-8")

    state = build_visual_control_plane_state(runtime_dir)

    validate_schema("schemas/visual_control_plane_state.schema.json", state)
    assert state["go_runs"][0]["methodology"]["skill_id"] == "tdd"
    assert state["go_runs"][0]["agents"][0]["methodology"]["skill_id"] == "tdd"
    assert state["team"]["task_board"][0]["methodology"]["skill_id"] == "tdd"
    html = render_visual_control_plane_state_html(state)
    assert "tdd" in html


def test_runtime_store_read_all_tolerates_malformed_line_in_middle(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    journal_path = runtime_dir / "rdgoal-events.jsonl"
    valid_a = json.dumps({
        "event_type": "project_registered",
        "project_id": "project-a",
        "payload": {},
        "timestamp": "2026-06-25T00:00:00Z",
        "event_id": "project-a-e1",
    })
    valid_b = json.dumps({
        "event_type": "project_registered",
        "project_id": "project-b",
        "payload": {},
        "timestamp": "2026-06-25T00:00:01Z",
        "event_id": "project-b-e1",
    })
    journal_path.write_text(
        valid_a + "\n" + "{malformed garbage\n" + valid_b + "\n",
        encoding="utf-8",
    )

    events = RuntimeStore(runtime_dir=runtime_dir).read_all()

    assert len(events) == 2
    assert events[0]["project_id"] == "project-a"
    assert events[1]["project_id"] == "project-b"


def test_runtime_store_read_all_handles_empty_file(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    journal_path = runtime_dir / "rdgoal-events.jsonl"
    journal_path.write_text("", encoding="utf-8")

    events = RuntimeStore(runtime_dir=runtime_dir).read_all()

    assert events == []


def test_runtime_digest_survives_truncated_journal(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    journal_path = runtime_dir / "rdgoal-events.jsonl"
    valid_event = json.dumps({
        "event_type": "project_registered",
        "project_id": "test-project",
        "payload": {"project_root": str(tmp_path / "project"), "priority": "medium"},
        "timestamp": "2026-06-25T00:00:00Z",
        "event_id": "test-project-e1",
    })
    journal_path.write_text(
        valid_event + "\n" + '{"event_type": "project_\n',
        encoding="utf-8",
    )

    digest = build_runtime_digest(runtime_dir)

    assert len(digest["projects"]) == 1
    assert digest["projects"][0]["project_id"] == "test-project"


def test_runtime_store_append_then_read_all_preserves_valid_events(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    store = RuntimeStore(runtime_dir=runtime_dir)
    store.append(JournalEvent(
        event_type="project_registered",
        project_id="test-project",
        payload={"project_root": str(tmp_path)},
    ))

    journal_path = runtime_dir / "rdgoal-events.jsonl"
    content = journal_path.read_text(encoding="utf-8")
    journal_path.write_text(content + '{"truncated\n', encoding="utf-8")

    events = store.read_all()

    assert len(events) == 1
    assert events[0]["project_id"] == "test-project"
