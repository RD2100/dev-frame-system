import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[3]
POLICY_DIR = REPO_ROOT / "packages" / "agent-acceptance" / "policies"
CONTRACT_DIR = REPO_ROOT / "packages" / "agent-acceptance" / "contracts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def test_outcome_first_policy_is_public_and_indexed():
    policy = POLICY_DIR / "OUTCOME_FIRST_DELIVERY_POLICY.md"
    guide = REPO_ROOT / "docs" / "agent-runtime" / "outcome-first-delivery.md"

    assert policy.is_file()
    assert guide.is_file()
    assert policy.name in _read(POLICY_DIR / "README.md")
    assert "OUTCOME_FIRST_DELIVERY_POLICY.md" in _read(guide)
    assert "outcome-first delivery" in _read(
        REPO_ROOT / "packages" / "agent-acceptance" / "README.md"
    ).lower()


def test_terminal_semantics_are_bounded_without_inventing_a_milestone():
    policy_names = [
        "TERMINAL_STATE_POLICY.md",
        "RUN_UNTIL_TERMINAL_POLICY.md",
        "NEXT_TASKSPEC_CONSUMPTION_POLICY.md",
        "DISPATCHER_POLICY.md",
        "FLOW_RUNNER_POLICY.md",
    ]
    combined = "\n".join(_read(POLICY_DIR / name) for name in policy_names)

    assert "bounded" in combined
    assert "accepted_done" in combined
    assert "solely to avoid" in combined or "only to avoid" in combined

    dispatcher = _read(POLICY_DIR / "DISPATCHER_POLICY.md")
    assert re.search(
        r"^\| accepted \| false \| .*accepted_done.*\| stopped \| true \| false \|$",
        dispatcher,
        flags=re.MULTILINE,
    )
    assert not re.search(r"^\| accepted_done \|", dispatcher, flags=re.MULTILINE)

    schema_names = [
        "FLOW_OUTCOME.schema.json",
        "DISPATCH_RESULT.schema.json",
        "RUNNER_STATE.schema.json",
        "RUNNER_CONTRACT.schema.json",
        "RUNNER_STEP_RESULT.schema.json",
    ]
    for name in schema_names:
        contract = CONTRACT_DIR / name
        json.loads(_read(contract))
        assert "bounded" in _read(contract), name


def test_accepted_milestone_closure_matches_existing_machine_contracts():
    flow_schema = json.loads(_read(CONTRACT_DIR / "FLOW_OUTCOME.schema.json"))
    dispatch_schema = json.loads(_read(CONTRACT_DIR / "DISPATCH_RESULT.schema.json"))
    flow_validator = Draft202012Validator(flow_schema)
    dispatch_validator = Draft202012Validator(dispatch_schema)

    flow = {
        "task_id": "milestone-17",
        "stage": "delivery",
        "transport_status": "success",
        "business_decision": "accepted",
        "dispatch_status": "stopped",
        "overall_status": "accepted",
        "allow_next_stage": False,
        "terminal": True,
        "required_next_action": "Resume from the authoritative backlog.",
    }
    dispatch = {
        "dispatch_status": "stopped",
        "terminal": True,
        "should_execute_next": False,
        "reason": "accepted_done",
        "required_next_action": "Resume from the authoritative backlog.",
    }

    flow_validator.validate(flow)
    dispatch_validator.validate(dispatch)

    flow["business_decision"] = "accepted_done"
    assert list(flow_validator.iter_errors(flow))


def test_risk_profiles_preserve_hard_gates_and_reduce_repeated_work():
    policy = _read(POLICY_DIR / "OUTCOME_FIRST_DELIVERY_POLICY.md")

    for profile in ("critical", "high", "medium", "low", "read_only"):
        assert f"`{profile}`" in policy

    assert "Independent review required" in policy
    assert "focused" in policy.lower()
    assert "three to five" in policy
    assert "20 percent" in policy
    assert "no-fake-green" in policy


def test_project_rules_expose_outcome_first_decision_points():
    orchestration = _read(REPO_ROOT / "rules" / "orchestration.md")
    normalized_orchestration = " ".join(orchestration.split()).lower()
    review = _read(REPO_ROOT / "rules" / "review.md")
    recon = _read(REPO_ROOT / "rules" / "recon.md")

    for rule_id in range(6, 13):
        assert f"RULE orch-{rule_id:03d}" in orchestration
    for rule_id in range(7, 10):
        assert f"RULE review-{rule_id:03d}" in review
    assert "RULE recon-010" in recon
    assert "committed `HEAD`" in recon
    assert "project root coordinator" in orchestration
    assert "must not design an ordinary next milestone" in normalized_orchestration


def test_runtime_bootstrap_exposes_and_copies_outcome_first_guide():
    template_roots = [
        REPO_ROOT / "templates" / "runtime-bootstrap",
        REPO_ROOT / "packages" / "control-plane" / "templates" / "runtime-bootstrap",
    ]

    for root in template_roots:
        agents = _read(root / "AGENTS.template.md")
        bootstrap = _read(root / "bootstrap.ps1")
        readme = _read(root / "README.md")

        assert "## Outcome-First Delivery" in agents
        assert "outcome-first-delivery.md" in agents
        assert "outcome-first-delivery.md" in bootstrap
        assert "Outcome-First Delivery" in readme


def test_runtime_bootstrap_really_copies_outcome_first_guide(tmp_path):
    if not shutil.which("powershell"):
        pytest.skip("PowerShell is required for the runtime bootstrap probe")

    project_root = tmp_path / "outcome-probe"
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPO_ROOT / "templates" / "runtime-bootstrap" / "bootstrap.ps1"),
            "-ProjectName",
            "outcome-probe",
            "-ProjectRoot",
            str(project_root),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (project_root / "docs" / "agent-runtime" / "outcome-first-delivery.md").is_file()
    assert "Outcome-First Delivery" in (project_root / "AGENTS.md").read_text(
        encoding="utf-8-sig"
    )


def test_delivery_goal_continues_without_master_micro_management():
    policy = _read(POLICY_DIR / "OUTCOME_FIRST_DELIVERY_POLICY.md")
    guide = _read(REPO_ROOT / "docs" / "agent-runtime" / "outcome-first-delivery.md")
    normalized_guide = " ".join(guide.split())

    assert "finite Delivery Goal" in policy
    assert "frozen candidate set" in policy
    assert "project root coordinator" in policy
    assert "MUST NOT prescribe ordinary milestone order" in policy
    assert "generic resume directive" in guide
    assert "does not name that milestone" in normalized_guide
