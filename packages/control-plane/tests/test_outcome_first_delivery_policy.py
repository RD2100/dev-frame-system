import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[3]
POLICY_DIR = REPO_ROOT / "packages" / "agent-acceptance" / "policies"
CONTRACT_DIR = REPO_ROOT / "packages" / "agent-acceptance" / "contracts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def test_outcome_first_policy_is_a_package_owned_machine_asset() -> None:
    policy = POLICY_DIR / "OUTCOME_FIRST_DELIVERY_POLICY.md"
    plan = _read(REPO_ROOT / "PLAN.md")

    assert policy.is_file()
    assert "Outcome-First" in _read(policy)
    assert "机器消费的 rule/schema/policy/contract" in plan
    assert "它们不调度项目" in plan


def test_terminal_semantics_are_bounded_without_inventing_a_milestone() -> None:
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

    for name in [
        "FLOW_OUTCOME.schema.json",
        "DISPATCH_RESULT.schema.json",
        "RUNNER_STATE.schema.json",
        "RUNNER_CONTRACT.schema.json",
        "RUNNER_STEP_RESULT.schema.json",
    ]:
        contract = CONTRACT_DIR / name
        json.loads(_read(contract))
        assert "bounded" in _read(contract), name


def test_accepted_milestone_closure_matches_machine_contracts() -> None:
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


def test_risk_profiles_preserve_hard_gates_and_reduce_repeated_work() -> None:
    policy = _read(POLICY_DIR / "OUTCOME_FIRST_DELIVERY_POLICY.md")
    for profile in ("critical", "high", "medium", "low", "read_only"):
        assert f"`{profile}`" in policy
    assert "Independent review required" in policy
    assert "focused" in policy.lower()
    assert "three to five" in policy
    assert "20 percent" in policy
    assert "no-fake-green" in policy


def test_plan_execution_protocol_preserves_outcome_first_boundaries() -> None:
    plan = _read(REPO_ROOT / "PLAN.md")
    protocol = plan.split("## 12. Execution Protocol", 1)[1].split(
        "## 13. Human Gates", 1
    )[0]

    assert "任何时刻只允许一个 `active` 里程碑" in plan
    assert "focused 验证" in protocol
    assert "affected/broad gate" in protocol
    assert "产品审阅先于技术 P0–P3 审阅" in protocol
    assert "只有全部通过才更新本文件的状态和 Next Action" in protocol
    assert "Worker 成功不会被误写成项目完成" in plan


def test_project_rules_expose_outcome_first_decision_points() -> None:
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


def test_bootstrap_exposes_single_plan_instead_of_a_parallel_guide() -> None:
    for root in [
        REPO_ROOT / "templates" / "runtime-bootstrap",
        REPO_ROOT / "packages" / "control-plane" / "templates" / "runtime-bootstrap",
    ]:
        agents = _read(root / "AGENTS.template.md")
        bootstrap = _read(root / "bootstrap.ps1")
        plan = _read(root / "PLAN.template.md")

        assert "only human development authority" in " ".join(agents.split())
        assert '"PLAN.template.md" "PLAN.md"' in bootstrap
        assert "## Execution Protocol" in plan
        assert "outcome-first-delivery.md" not in bootstrap


def test_delivery_goal_continues_without_master_micro_management() -> None:
    policy = _read(POLICY_DIR / "OUTCOME_FIRST_DELIVERY_POLICY.md")
    plan = _read(REPO_ROOT / "PLAN.md")

    assert "finite Delivery Goal" in policy
    assert "frozen candidate set" in policy
    assert "project root coordinator" in policy
    assert "MUST NOT prescribe ordinary milestone order" in policy
    assert "后续条目是有序 backlog" in plan
