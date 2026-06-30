"""Executor-agnostic git worktree isolation for parallel coding agents.

Each parallel coding agent can be given its own git worktree so two agents
physically cannot edit the same working tree. This module knows only git; it
never references OpenCode or any specific executor. The executor-specific state
isolation (for example a per-worktree ``OPENCODE_HOME``) is computed by the
dispatch layer and passed in as a generic environment override.

Every function here is defensive: when the project is not a git repository, git
is unavailable, or a command fails, ``create_worktree`` returns ``None`` and the
caller falls back to in-place execution. Isolation is an opt-in enhancement, not
a correctness dependency, so failing to isolate must never raise.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class WorktreeHandle:
    """A created git worktree for a single agent run."""

    path: str
    repo_root: str
    run_id: str
    agent_id: str


def _git_executable() -> str | None:
    return shutil.which("git")


def _run_git(repo_root: Path, args: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess | None:
    git = _git_executable()
    if not git:
        return None
    try:
        return subprocess.run(
            [git, "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def git_repo_root(project_root: str | Path) -> Path | None:
    """Return the top-level git working tree for ``project_root`` or ``None``.

    ``None`` means the path is not inside a git working tree, or git is not
    available. Callers treat ``None`` as "isolation impossible, fall back".
    """
    root = Path(project_root)
    if not root.exists():
        return None
    completed = _run_git(root, ["rev-parse", "--show-toplevel"])
    if completed is None or completed.returncode != 0:
        return None
    top = completed.stdout.strip()
    if not top:
        return None
    try:
        return Path(top).resolve()
    except OSError:
        return None


def _safe_segment(value: str) -> str:
    text = "".join(ch if (ch.isalnum() or ch in {"-", "_"}) else "-" for ch in str(value).strip())
    text = text.strip("-")
    return text or "agent"


def create_worktree(
    project_root: str | Path,
    run_id: str,
    agent_id: str,
    *,
    runtime_dir: str | Path,
) -> WorktreeHandle | None:
    """Create a detached git worktree for one agent, or return ``None``.

    The worktree is checked out at the current ``HEAD`` (detached) under
    ``<runtime_dir>/worktrees/<run_id>/<agent_id>``. Returns ``None`` on any
    failure so the caller can fall back to in-place execution. If a worktree
    already exists at the target path it is reused.
    """
    repo_root = git_repo_root(project_root)
    if repo_root is None:
        return None

    worktree_path = (
        Path(runtime_dir).resolve()
        / "worktrees"
        / _safe_segment(run_id)
        / _safe_segment(agent_id)
    )

    if worktree_path.exists():
        # Reuse an existing worktree (idempotent re-execution).
        if _is_registered_worktree(repo_root, worktree_path):
            return WorktreeHandle(
                path=str(worktree_path),
                repo_root=str(repo_root),
                run_id=run_id,
                agent_id=agent_id,
            )
        return None

    try:
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    completed = _run_git(
        repo_root,
        ["worktree", "add", "--detach", str(worktree_path), "HEAD"],
    )
    if completed is None or completed.returncode != 0:
        return None

    return WorktreeHandle(
        path=str(worktree_path),
        repo_root=str(repo_root),
        run_id=run_id,
        agent_id=agent_id,
    )


def _is_registered_worktree(repo_root: Path, worktree_path: Path) -> bool:
    completed = _run_git(repo_root, ["worktree", "list", "--porcelain"])
    if completed is None or completed.returncode != 0:
        return False
    target = str(worktree_path.resolve()).replace("\\", "/").lower()
    for line in completed.stdout.splitlines():
        if not line.startswith("worktree "):
            continue
        listed = line[len("worktree "):].strip()
        try:
            normalized = str(Path(listed).resolve()).replace("\\", "/").lower()
        except OSError:
            continue
        if normalized == target:
            return True
    return False


def remove_worktree(handle: WorktreeHandle) -> bool:
    """Remove a previously created worktree. Returns ``True`` on success.

    Defensive: never raises. Callers may keep worktrees for inspection instead
    of calling this, since the runtime directory is disposable.
    """
    repo_root = Path(handle.repo_root)
    completed = _run_git(repo_root, ["worktree", "remove", "--force", handle.path])
    return bool(completed is not None and completed.returncode == 0)
