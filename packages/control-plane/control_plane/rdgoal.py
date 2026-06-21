"""rdgoal total-control entry point."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .orchestrator import DispatchResult, Orchestrator
from .project_contract import render_contract_markdown, slugify_project_id


PACKAGE_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class RdGoalResult:
    project_id: str
    project_root: str
    contract_path: str
    governed: bool
    rdinit_action: str
    dispatch: DispatchResult
    notes: list[str] = field(default_factory=list)


def is_governed(project_root: str | Path) -> bool:
    return (Path(project_root) / "AGENTS.md").exists()


def default_contracts_dir(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / "rules" / "project-contracts"


def ensure_contract(project_id: str, requirement: str,
                    contracts_dir: str | Path) -> tuple[Path, bool]:
    target_dir = Path(contracts_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    contract_path = target_dir / f"{project_id}.md"
    if contract_path.exists():
        return contract_path, False
    contract_path.write_text(render_contract_markdown(project_id, requirement), encoding="utf-8")
    return contract_path, True


def _bootstrap_source_ready(script_path: Path) -> bool:
    source_root = script_path.parents[2]
    return (
        (source_root / "rules").is_dir()
        and (source_root / "schemas").is_dir()
        and (source_root / "docs" / "agent-runtime").is_dir()
    )


def _candidate_bootstrap_paths() -> list[Path]:
    source_repo_root = PACKAGE_ROOT.parents[1]
    return [
        source_repo_root / "templates" / "runtime-bootstrap" / "bootstrap.ps1",
        PACKAGE_ROOT / "templates" / "runtime-bootstrap" / "bootstrap.ps1",
    ]


def find_bootstrap_script() -> Path | None:
    for candidate in _candidate_bootstrap_paths():
        if candidate.exists() and _bootstrap_source_ready(candidate):
            return candidate
    return None


def run_rdinit(project_root: str | Path, *, apply: bool = False) -> str:
    if is_governed(project_root):
        return "skipped_already_governed"
    if not apply:
        return "planned_not_applied"
    bootstrap = find_bootstrap_script()
    if not bootstrap:
        return "bootstrap_unavailable"
    subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(bootstrap),
            "-ProjectRoot",
            str(Path(project_root).resolve()),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return "ran_bootstrap"


def rdgoal(orchestrator: Orchestrator, project_path: str | Path, requirement: str,
           *, operation: str = "direction choice", targets: list[str] | None = None,
           apply_rdinit: bool = False,
           contracts_dir: str | Path | None = None) -> RdGoalResult:
    root = Path(project_path).resolve()
    project_id = slugify_project_id(root)
    notes: list[str] = []

    rdinit_action = run_rdinit(root, apply=apply_rdinit)
    governed = is_governed(root)
    if rdinit_action == "planned_not_applied":
        notes.append("Project is not governed yet; rdinit bootstrap was planned but not applied.")
    if rdinit_action == "bootstrap_unavailable":
        notes.append("rdinit bootstrap assets are unavailable in this installation; dispatch packet was still generated.")

    contract_path, created = ensure_contract(
        project_id,
        requirement,
        contracts_dir=contracts_dir or default_contracts_dir(root),
    )
    if created:
        notes.append("Project contract auto-created with total_control defaults.")

    orchestrator.register(contract_path, root)
    dispatch = orchestrator.dispatch(
        project_id=project_id,
        requirement=requirement,
        operation=operation,
        targets=targets or [],
    )

    return RdGoalResult(
        project_id=project_id,
        project_root=str(root),
        contract_path=str(contract_path),
        governed=governed,
        rdinit_action=rdinit_action,
        dispatch=dispatch,
        notes=notes,
    )
