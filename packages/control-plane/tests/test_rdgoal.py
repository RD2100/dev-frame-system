from pathlib import Path
import json
import os
import sys

from jsonschema import Draft202012Validator
from jsonschema.validators import validator_for
import yaml

from control_plane.backup_guard import BackupGuard
from control_plane.cli import main as devframe_cli_main
from control_plane.decision_engine import DecisionEngine, DecisionMode, OperationRequest
from control_plane.orchestrator import Orchestrator
from control_plane.project_contract import load_contract, render_contract_markdown
from control_plane.rdgoal import rdgoal
from control_plane.rdgoal_cli import main as rdgoal_cli_main
from control_plane.runtime_digest import build_runtime_digest, render_runtime_digest_markdown
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
