"""Hermetic tests for executor-agnostic git worktree isolation.

These tests build a throwaway git repository in a temp directory and exercise
real `git worktree` behavior. No tokens are spent and no executor is involved.
When git is unavailable, the tests are skipped (the module is defensive and the
caller falls back to in-place execution).
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from control_plane.worktree import (
    WorktreeHandle,
    create_worktree,
    git_repo_root,
    remove_worktree,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")


def _init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(path), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@example.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True, capture_output=True)
    (path / "file.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "init"], check=True, capture_output=True)


def test_git_repo_root_detects_repo(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    root = git_repo_root(repo)
    assert root is not None
    assert root.resolve() == repo.resolve()


def test_git_repo_root_returns_none_outside_repo(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert git_repo_root(plain) is None


def test_create_worktree_makes_isolated_tree(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    runtime = tmp_path / "runtime"

    handle = create_worktree(repo, "go-run-1", "coding-agent-1", runtime_dir=runtime)

    assert isinstance(handle, WorktreeHandle)
    worktree = tmp_path / "runtime" / "worktrees" / "go-run-1" / "coding-agent-1"
    assert worktree.exists()
    # The committed file is present in the isolated checkout.
    assert (worktree / "file.txt").read_text(encoding="utf-8") == "hello\n"
    # Writing in the worktree does not touch the main tree.
    (worktree / "agent-only.txt").write_text("x\n", encoding="utf-8")
    assert not (repo / "agent-only.txt").exists()


def test_create_worktree_returns_none_for_non_repo(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    runtime = tmp_path / "runtime"
    assert create_worktree(plain, "go-run-1", "agent-1", runtime_dir=runtime) is None


def test_create_worktree_is_idempotent(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    runtime = tmp_path / "runtime"

    first = create_worktree(repo, "go-run-1", "coding-agent-1", runtime_dir=runtime)
    second = create_worktree(repo, "go-run-1", "coding-agent-1", runtime_dir=runtime)

    assert first is not None and second is not None
    assert first.path == second.path


def test_two_agents_get_distinct_worktrees(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    runtime = tmp_path / "runtime"

    a = create_worktree(repo, "go-run-1", "coding-agent-1", runtime_dir=runtime)
    b = create_worktree(repo, "go-run-1", "coding-agent-2", runtime_dir=runtime)

    assert a is not None and b is not None
    assert a.path != b.path


def test_remove_worktree(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    runtime = tmp_path / "runtime"

    handle = create_worktree(repo, "go-run-1", "coding-agent-1", runtime_dir=runtime)
    assert handle is not None

    assert remove_worktree(handle) is True
    assert not (tmp_path / "runtime" / "worktrees" / "go-run-1" / "coding-agent-1").exists()
