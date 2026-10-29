"""Debug verify --json output."""
import io, json, sys, tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ai_workflow_hub.cli import app

def _fake_runtime():
    return {"sanitize": lambda rid: rid, "create": MagicMock(), "execute": MagicMock(),
            "status": MagicMock(), "redact": lambda s: s}

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    run_id = "debug-verify"
    run_dir = tmp / run_id
    run_dir.mkdir(parents=True)
    state = {"run_id": run_id, "task_id": "t", "project_id": "p", "status": "completed",
             "workflow_type": "paper", "created_at": "x", "updated_at": "x",
             "executed_nodes": [], "acceptance_result": {"status": "accepted", "reasons": [], "blocking_issues": []},
             "blocking_count": 0, "non_blocking_count": 0,
             "evidence_manifest": {"manifest_id": "ev", "status": "complete", "version": "1.0",
                 "generated_at": "x", "files": [],
                 "privacy_attestation": {"no_full_text": True, "no_api_keys": True, "no_personal_identity": True}},
             "ledger_dir": "", "decision_base_dir": ""}
    (run_dir / "state.json").write_text(json.dumps(state))
    (run_dir / "closeout-report.json").write_text(json.dumps({"v": 1}))
    (run_dir / "closeout-report.md").write_text("# Report")

    rt = _fake_runtime()
    runner = CliRunner()
    sb = io.StringIO()
    eb = io.StringIO()
    _c = Console(file=sb, force_terminal=False, width=4096)
    _ec = Console(file=eb, force_terminal=False)

    with patch("ai_workflow_hub.cli._paper_runtime", return_value=rt), \
         patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp), \
         patch("ai_workflow_hub.cli.init_env"), \
         patch("ai_workflow_hub.cli.console", _c), \
         patch("ai_workflow_hub.cli.err_console", _ec):
        r = runner.invoke(app, ["paper", "audit", "--run-id", run_id], catch_exceptions=False)
    print(f"Audit exit: {r.exit_code}")

    zips = list(run_dir.glob("audit-bundle-*.zip"))
    print(f"ZIPs: {len(zips)}")

    sb2 = io.StringIO()
    eb2 = io.StringIO()
    _c2 = Console(file=sb2, force_terminal=False, width=4096)
    _ec2 = Console(file=eb2, force_terminal=False)

    with patch("ai_workflow_hub.cli._paper_runtime", return_value=rt), \
         patch("ai_workflow_hub.cli.init_env"), \
         patch("ai_workflow_hub.cli.console", _c2), \
         patch("ai_workflow_hub.cli.err_console", _ec2):
        r2 = runner.invoke(app, ["paper", "verify", "--zip", str(zips[0]), "--json"], catch_exceptions=False)
    print(f"Verify exit: {r2.exit_code}")
    out = sb2.getvalue()
    print(f"stdout len: {len(out)}")
    print(f"stdout repr first 500: {out[:500]!r}")
    try:
        parsed = json.loads(out.strip())
        print(f"JSON OK: verdict={parsed.get('verdict')}")
    except json.JSONDecodeError as e:
        print(f"JSON FAIL: {e}")
        # Try to find the issue
        lines = out.strip().split("\n")
        for i, line in enumerate(lines[:5]):
            print(f"  line {i}: len={len(line)} repr={line[:80]!r}")
