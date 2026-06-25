"""Shared helpers for /go and code dispatch target planning."""
from __future__ import annotations

import subprocess
from pathlib import Path


def resolve_coding_targets(
    project_path: str | Path,
    targets: list[str],
    *,
    changed: bool,
    since: str | None,
) -> list[str]:
    git_targets: list[str] = []
    if since:
        git_targets.extend(_git_since_targets(project_path, since))
    if changed:
        git_targets.extend(_git_changed_targets(project_path))
    if not changed and not since:
        return _dedupe_targets(targets)
    merged = _dedupe_targets([*targets, *git_targets])
    if not merged:
        if since and changed:
            raise ValueError("--since/--changed found no git target files")
        if since:
            raise ValueError(f"--since {since} found no files changed against HEAD")
        raise ValueError("--changed found no modified, staged, or untracked git files")
    return merged


def resolve_agent_count(raw_agents: str, targets: list[str], *, max_agents: int) -> int:
    if max_agents < 1:
        raise ValueError("--max-agents must be >= 1")
    if raw_agents.strip().lower() == "auto":
        if not targets:
            return 1
        return max(1, min(len(targets), max_agents))
    try:
        agents = int(raw_agents)
    except ValueError as exc:
        raise ValueError("--agents must be a positive integer or auto") from exc
    if agents < 1:
        raise ValueError("--agents must be >= 1")
    return agents


def git_changed_targets(project_path: str | Path) -> list[str]:
    project_root = Path(project_path).resolve()
    if not project_root.exists():
        raise ValueError(f"project path does not exist: {project_root}")
    inside = _git_output(project_root, ["rev-parse", "--is-inside-work-tree"])
    if inside.strip().lower() != "true":
        raise ValueError(f"--changed requires a git work tree: {project_root}")
    targets: list[str] = []
    for args in (
        ["diff", "--name-only", "--diff-filter=ACMR"],
        ["diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        targets.extend(line.strip() for line in _git_output(project_root, args).splitlines() if line.strip())
    return _dedupe_targets(targets)


def git_since_targets(project_path: str | Path, ref: str) -> list[str]:
    project_root = Path(project_path).resolve()
    if not project_root.exists():
        raise ValueError(f"project path does not exist: {project_root}")
    inside = _git_output(project_root, ["rev-parse", "--is-inside-work-tree"])
    if inside.strip().lower() != "true":
        raise ValueError(f"--since requires a git work tree: {project_root}")
    output = _git_output(project_root, [
        "diff",
        "--name-only",
        "--diff-filter=ACMR",
        f"{ref}...HEAD",
        "--",
    ])
    return _dedupe_targets([line.strip() for line in output.splitlines() if line.strip()])


def _git_changed_targets(project_path: str | Path) -> list[str]:
    return git_changed_targets(project_path)


def _git_since_targets(project_path: str | Path, ref: str) -> list[str]:
    return git_since_targets(project_path, ref)


def _git_output(project_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(project_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def _dedupe_targets(targets: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for target in targets:
        text = str(target).strip()
        if text and text not in seen:
            seen.add(text)
            unique.append(text)
    return unique
