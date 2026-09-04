from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PUBLIC_TEMPLATE_ROOT = REPO_ROOT / "templates" / "runtime-bootstrap"
PACKAGED_TEMPLATE_ROOT = (
    REPO_ROOT / "packages" / "control-plane" / "templates" / "runtime-bootstrap"
)


@pytest.mark.parametrize(
    "name",
    [
        "PLAN.template.md",
        "AGENTS.template.md",
        "bootstrap.ps1",
        "tool-policy.template.md",
        "governance-manifest.template.md",
        "INSTANTIATION.md",
        "README.md",
    ],
)
def test_runtime_bootstrap_templates_are_mirrored(name: str) -> None:
    assert (PACKAGED_TEMPLATE_ROOT / name).read_bytes() == (
        PUBLIC_TEMPLATE_ROOT / name
    ).read_bytes()


def test_bootstrap_contract_uses_one_plan_and_package_owned_machine_assets() -> None:
    plan = (PUBLIC_TEMPLATE_ROOT / "PLAN.template.md").read_text(encoding="utf-8")
    agents = (PUBLIC_TEMPLATE_ROOT / "AGENTS.template.md").read_text(encoding="utf-8")
    policy = (PUBLIC_TEMPLATE_ROOT / "tool-policy.template.md").read_text(
        encoding="utf-8"
    )
    bootstrap = (PUBLIC_TEMPLATE_ROOT / "bootstrap.ps1").read_text(encoding="utf-8")

    assert "Current verdict:" in plan
    assert "## Next Action" in plan
    assert "only human development authority" in " ".join(agents.split())
    assert ".devframe/contracts/" in agents
    assert ".devframe/contracts/capability-inventory.md" in policy
    assert 'New-FromTemplate "PLAN.template.md" "PLAN.md"' in bootstrap
    assert '".devframe/contracts/capability-inventory.md"' in bootstrap
    assert '"packages/agent-acceptance/fixtures/negative-acceptance"' in bootstrap
    assert "docs/" not in bootstrap


def _powershell() -> str:
    executable = shutil.which("powershell") or shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell is required for the runtime bootstrap probe")
    return executable


def test_runtime_bootstrap_generates_single_plan_contract(tmp_path: Path) -> None:
    project_root = tmp_path / "single-plan-project"
    result = subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PUBLIC_TEMPLATE_ROOT / "bootstrap.ps1"),
            "-ProjectName",
            "single-plan-project",
            "-ProjectRoot",
            str(project_root),
            "-Platform",
            "Both",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    generated_plan = (project_root / "PLAN.md").read_text(encoding="utf-8-sig")
    generated_agents = (project_root / "AGENTS.md").read_text(encoding="utf-8-sig")
    assert "# single-plan-project Plan" in generated_plan
    assert "Current verdict:" in generated_plan
    assert "PLAN.md" in generated_agents
    assert (project_root / ".devframe" / "contracts" / "capability-inventory.md").is_file()
    assert (project_root / ".devframe" / "contracts" / "tool-policy.md").is_file()
    assert (project_root / ".devframe" / "contracts" / "governance-manifest.md").is_file()
    assert (
        project_root
        / "packages"
        / "agent-acceptance"
        / "fixtures"
        / "negative-acceptance"
        / "NEG-031-missing-recon-receipt.json"
    ).is_file()
    assert not (project_root / "docs").exists()
    assert not (project_root / ".mcp.json").exists()
    assert not (project_root / "mcp.json").exists()


def test_runtime_bootstrap_preserves_existing_authority_files(tmp_path: Path) -> None:
    project_root = tmp_path / "existing-plan-project"
    project_root.mkdir()
    existing_plan = "# Owner plan\nCurrent verdict: **owner-controlled**\n"
    existing_agents = "# Owner entry\nRead the owner plan.\n"
    (project_root / "PLAN.md").write_text(existing_plan, encoding="utf-8")
    (project_root / "AGENTS.md").write_text(existing_agents, encoding="utf-8")

    result = subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PUBLIC_TEMPLATE_ROOT / "bootstrap.ps1"),
            "-ProjectName",
            "existing-plan-project",
            "-ProjectRoot",
            str(project_root),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (project_root / "PLAN.md").read_text(encoding="utf-8") == existing_plan
    assert (project_root / "AGENTS.md").read_text(encoding="utf-8") == existing_agents
