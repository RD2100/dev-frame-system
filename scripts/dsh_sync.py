#!/usr/bin/env python3
"""Read-only DSH upstream synchronization preflight.

This first synchronization slice deliberately does not fetch, merge, reset,
clean, or write to a DSH checkout. It reports whether a checkout is safe to
use as the starting point for a later candidate build.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any


COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
APPLIED_CONFLICT_RE = re.compile(r"Applied patch to '([^']+)' with conflicts\.")
MISSING_INDEX_RE = re.compile(r"error:\s+(.+): does not exist in index$")
MAX_APPLY_DIAGNOSTIC_PATHS = 128


class SyncError(Exception):
    """A user-actionable lock or checkout error."""


def _run_command(command: list[str]) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise SyncError(f"git is unavailable: {exc}") from exc
    return result.returncode, result.stdout, result.stderr


def _run_git(root: Path, *args: str) -> tuple[int, str, str]:
    return _run_command(["git", "-C", str(root), *args])


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SyncError(f"{name} must be an object")
    return value


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise SyncError(f"{name} must be a non-empty string")
    return value


def _require_commit(value: Any, name: str) -> str:
    commit = _require_string(value, name)
    if not COMMIT_RE.fullmatch(commit):
        raise SyncError(f"{name} must be a 40-character lowercase commit")
    return commit


def _require_relative_path(value: Any, name: str) -> str:
    path = _require_string(value, name)
    if Path(path).is_absolute() or WINDOWS_ABSOLUTE_RE.match(path):
        raise SyncError(f"{name} must be relative")
    if any(part == ".." for part in re.split(r"[\\/]", path)):
        raise SyncError(f"{name} must not escape its root")
    return path


def _validate_upstream(value: Any) -> None:
    upstream = _require_mapping(value, "upstream")
    repository = _require_string(upstream.get("repository"), "upstream.repository")
    if repository not in {
        "https://github.com/deepseek-ai/deepseek-harness",
        "https://github.com/deepseek-ai/deepseek-harness.git",
    }:
        raise SyncError("upstream.repository must be the official DeepSeek Harness repository")
    target = _require_mapping(upstream.get("target"), "upstream.target")
    _require_string(target.get("ref"), "upstream.target.ref")
    _require_commit(target.get("commit"), "upstream.target.commit")


def _validate_baseline(value: Any) -> None:
    baseline = _require_mapping(value, "baseline")
    _require_commit(baseline.get("knownUpstreamCommit"), "baseline.knownUpstreamCommit")
    _require_commit(baseline.get("capturedHeadCommit"), "baseline.capturedHeadCommit")
    captured_at = _require_string(baseline.get("capturedAt"), "baseline.capturedAt")
    if not DATE_RE.fullmatch(captured_at):
        raise SyncError("baseline.capturedAt must use YYYY-MM-DD")
    if baseline.get("worktreeStatus") not in {"clean", "dirty"}:
        raise SyncError("baseline.worktreeStatus must be clean or dirty")


def _validate_overlay(value: Any) -> None:
    overlay = _require_mapping(value, "overlay")
    if overlay.get("mode") not in {"pending-inventory", "patch-stack"}:
        raise SyncError("overlay.mode is invalid")
    roots = overlay.get("roots")
    if not isinstance(roots, list):
        raise SyncError("overlay.roots must be an array")
    for index, root in enumerate(roots):
        _require_relative_path(root, f"overlay.roots[{index}]")
    patches = overlay.get("patches")
    if not isinstance(patches, list):
        raise SyncError("overlay.patches must be an array")
    for index, patch in enumerate(patches):
        item = _require_mapping(patch, f"overlay.patches[{index}]")
        identifier = _require_string(item.get("id"), f"overlay.patches[{index}].id")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", identifier):
            raise SyncError(f"overlay.patches[{index}].id is invalid")
        _require_relative_path(item.get("path"), f"overlay.patches[{index}].path")
        checksum = _require_string(item.get("sha256"), f"overlay.patches[{index}].sha256")
        if not SHA256_RE.fullmatch(checksum):
            raise SyncError(f"overlay.patches[{index}].sha256 must be a 64-character lowercase SHA-256")


def _validate_generated(value: Any) -> None:
    generated = _require_mapping(value, "generated")
    if generated.get("sourceOfTruth") != "source":
        raise SyncError("generated.sourceOfTruth must be source")
    paths = generated.get("paths")
    if not isinstance(paths, list) or any(not isinstance(path, str) or not path for path in paths):
        raise SyncError("generated.paths must be a non-empty-string array")


def validate_lock(lock: dict[str, Any]) -> None:
    required = {"$schema", "schemaVersion", "upstream", "baseline", "overlay", "generated"}
    missing = sorted(required - lock.keys())
    if missing:
        raise SyncError(f"lock is missing: {', '.join(missing)}")
    if lock["schemaVersion"] != 1:
        raise SyncError("schemaVersion must be 1")
    upstream = _require_mapping(lock["upstream"], "upstream")
    _validate_upstream(upstream)
    _validate_baseline(lock["baseline"])
    _validate_overlay(lock["overlay"])
    _validate_generated(lock["generated"])


def load_lock(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            lock = json.load(stream)
    except OSError as exc:
        raise SyncError(f"cannot read lock: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SyncError(f"lock is not valid JSON: {path}: {exc}") from exc
    if not isinstance(lock, dict):
        raise SyncError("lock root must be an object")
    validate_lock(lock)
    return lock


def verify_patches(repo_root: Path, lock: dict[str, Any]) -> list[dict[str, str]]:
    """Verify every hash-pinned overlay patch without mutating the checkout."""

    root = repo_root.resolve()
    verified: list[dict[str, str]] = []
    for patch in lock["overlay"]["patches"]:
        relative = Path(patch["path"])
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise SyncError(f"overlay patch escapes repository: {patch['path']}") from exc
        if not path.is_file():
            raise SyncError(f"overlay patch is missing: {patch['path']}")
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise SyncError(f"cannot read overlay patch {patch['path']}: {exc}") from exc
        if digest != patch["sha256"]:
            raise SyncError(
                f"overlay patch hash mismatch for {patch['path']}: "
                f"expected {patch['sha256']}, got {digest}"
            )
        verified.append({"id": patch["id"], "path": patch["path"], "sha256": digest})
    return verified


def _git_root(root: Path) -> Path:
    code, stdout, stderr = _run_git(root, "rev-parse", "--show-toplevel")
    if code != 0:
        detail = stderr.strip() or "not a git worktree"
        raise SyncError(f"invalid DSH checkout: {detail}")
    return Path(stdout.strip()).resolve()


def _git_value(root: Path, *args: str) -> str | None:
    code, stdout, _ = _run_git(root, *args)
    if code != 0:
        return None
    value = stdout.strip()
    return value or None


def _status_paths(root: Path) -> list[dict[str, str]]:
    code, stdout, stderr = _run_git(root, "status", "--porcelain=v1", "-z")
    if code != 0:
        raise SyncError(f"cannot inspect DSH worktree: {stderr.strip() or 'git status failed'}")
    records = [record for record in stdout.split("\x00") if record]
    result: list[dict[str, str]] = []
    for record in records:
        if len(record) < 4:
            raise SyncError("git status returned a malformed record")
        code_pair = record[:2]
        path = record[3:]
        result.append({"status": code_pair, "path": path})
    return result


def _checkout_decision(clean: bool, head: str | None, baseline: dict[str, Any], target: dict[str, Any]) -> str:
    if not clean:
        return "blocked_dirty_worktree"
    if head == target["commit"]:
        return "up_to_date"
    if head == baseline["capturedHeadCommit"]:
        return "ready_for_candidate"
    return "unexpected_clean_head"


def _overlay_inventory(root: Path, lock: dict[str, Any], status_paths: list[dict[str, str]]) -> dict[str, Any]:
    roots = lock["overlay"]["roots"]
    top_level_changes = sorted({item["path"].replace("\\", "/").split("/", 1)[0] for item in status_paths})
    return {
        "mode": lock["overlay"]["mode"],
        "configuredRoots": roots,
        "presentRoots": [root_path for root_path in roots if (root / root_path).exists()],
        "changedTopLevelPaths": top_level_changes,
    }


def _worktree_inventory(status_paths: list[dict[str, str]], decision: str) -> dict[str, Any]:
    tracked_changes = [item for item in status_paths if not item["status"].startswith("??")]
    untracked = [item for item in status_paths if item["status"].startswith("??")]
    return {
        "status": decision,
        "trackedChangeCount": len(tracked_changes),
        "untrackedCount": len(untracked),
        "paths": status_paths,
    }


def _apply_diagnostic_paths(output: str) -> tuple[list[str], list[str]]:
    conflicts: set[str] = set()
    missing: set[str] = set()
    for line in output.splitlines():
        text = line.strip()
        conflict = APPLIED_CONFLICT_RE.search(text)
        if conflict:
            conflicts.add(conflict.group(1).replace("\\", "/"))
            continue
        missing_match = MISSING_INDEX_RE.search(text)
        if missing_match:
            missing.add(missing_match.group(1).replace("\\", "/"))
    return (
        sorted(conflicts)[:MAX_APPLY_DIAGNOSTIC_PATHS],
        sorted(missing)[:MAX_APPLY_DIAGNOSTIC_PATHS],
    )


def inventory(dsh_root: Path, lock: dict[str, Any]) -> dict[str, Any]:
    root = _git_root(dsh_root)
    status_paths = _status_paths(root)
    head = _git_value(root, "rev-parse", "HEAD")
    branch = _git_value(root, "symbolic-ref", "--short", "HEAD") or "(detached)"
    origin_url = _git_value(root, "remote", "get-url", "origin")
    origin_master = _git_value(root, "rev-parse", "refs/remotes/origin/master")
    baseline = lock["baseline"]
    target = lock["upstream"]["target"]
    clean = not status_paths
    head_is_captured_baseline = head == baseline["capturedHeadCommit"]
    head_is_target = head == target["commit"]
    decision = _checkout_decision(clean, head, baseline, target)

    return {
        "schemaVersion": 1,
        "checkout": {
            "root": str(root),
            "branch": branch,
            "headCommit": head,
            "origin": origin_url,
            "originMasterCommit": origin_master,
            "clean": clean,
        },
        "baseline": {
            "capturedHeadCommit": baseline["capturedHeadCommit"],
            "knownUpstreamCommit": baseline["knownUpstreamCommit"],
            "headMatchesCaptured": head_is_captured_baseline,
            "originMasterMatchesKnown": origin_master == baseline["knownUpstreamCommit"],
        },
        "target": {
            "ref": target["ref"],
            "commit": target["commit"],
            "checkedOut": head_is_target,
        },
        "overlay": _overlay_inventory(root, lock, status_paths),
        "worktree": _worktree_inventory(status_paths, decision),
        "applyReadiness": {
            "safeToApply": decision == "ready_for_candidate",
            "reason": "Only a clean checkout at the captured baseline may enter the later candidate-build stage.",
        },
    }


def _check_overlay_patch(root: Path, repo_root: Path, patch: dict[str, str]) -> dict[str, Any]:
    patch_path = (repo_root.resolve() / patch["path"]).resolve()
    code, stdout, stderr = _run_git(
        root,
        "apply",
        "--3way",
        "--check",
        "--whitespace=nowarn",
        str(patch_path),
    )
    conflicts, missing = _apply_diagnostic_paths(f"{stdout}\n{stderr}")
    diagnostics: list[str] = []
    if conflicts:
        diagnostics.append("git_apply_conflict")
    if missing:
        diagnostics.append("git_apply_missing_path")
    if code != 0 and not diagnostics:
        diagnostics.append("git_apply_check_failed")
    return {
        "id": patch["id"],
        "path": patch["path"],
        "sha256": patch["sha256"],
        "applies": code == 0 and not conflicts and not missing,
        "conflicts": conflicts,
        "missing": missing,
        "diagnostics": diagnostics,
    }


def check_overlay(candidate_root: Path, repo_root: Path, lock: dict[str, Any]) -> dict[str, Any]:
    """Check a hash-pinned overlay against a candidate without applying it."""

    root = _git_root(candidate_root.resolve())
    patches = verify_patches(repo_root, lock)
    status_paths = _status_paths(root)
    head = _git_value(root, "rev-parse", "HEAD")
    target = lock["upstream"]["target"]
    checked = [_check_overlay_patch(root, repo_root, patch) for patch in patches]

    candidate_clean = not status_paths
    diagnostics: list[str] = []
    if not candidate_clean:
        diagnostics.append("candidate_dirty")
    if head != target["commit"]:
        diagnostics.append("candidate_target_mismatch")
    applies = not diagnostics and all(item["applies"] for item in checked)
    return {
        "schemaVersion": 1,
        "valid": applies,
        "applies": applies,
        "diagnostics": diagnostics,
        "candidate": {
            "root": str(root),
            "headCommit": head,
            "clean": candidate_clean,
            "statusPathCount": len(status_paths),
        },
        "target": {
            "ref": target["ref"],
            "commit": target["commit"],
            "checkedOut": head == target["commit"],
        },
        "patches": checked,
    }


def _numstat_paths(output: str) -> set[str]:
    """Extract the relative paths reported by ``git apply --numstat``."""

    paths: set[str] = set()
    for line in output.splitlines():
        fields = line.split("\t", 2)
        if len(fields) != 3:
            continue
        path = fields[2].strip().replace("\\", "/")
        if path:
            paths.add(path)
    return paths


def verify_prepared_candidate(candidate_root: Path, repo_root: Path, lock: dict[str, Any]) -> dict[str, Any]:
    """Verify that a prepared candidate contains exactly the applied overlay.

    ``prepare-candidate`` intentionally leaves the overlay as an uncommitted
    working-tree change. This read-only check validates that state by applying
    every locked patch in reverse check mode and comparing Git's reported patch
    paths with the candidate's status paths. It never changes the candidate.
    """

    root = _git_root(candidate_root.resolve())
    patches = verify_patches(repo_root, lock)
    status_paths = _status_paths(root)
    head = _git_value(root, "rev-parse", "HEAD")
    target = lock["upstream"]["target"]
    expected_paths: set[str] = set()
    checked: list[dict[str, Any]] = []
    diagnostics: list[str] = []

    if head != target["commit"]:
        diagnostics.append("candidate_target_mismatch")

    for patch in patches:
        patch_path = (repo_root.resolve() / patch["path"]).resolve()
        code, stdout, stderr = _run_git(
            root,
            "apply",
            "--numstat",
            "--reverse",
            "--check",
            "--whitespace=nowarn",
            str(patch_path),
        )
        output = f"{stdout}\n{stderr}"
        paths = _numstat_paths(stdout)
        expected_paths.update(paths)
        conflicts, missing = _apply_diagnostic_paths(output)
        patch_diagnostics: list[str] = []
        if code != 0:
            patch_diagnostics.append("reverse_apply_check_failed")
            diagnostics.append("overlay_not_applied")
        if conflicts:
            patch_diagnostics.append("git_apply_conflict")
        if missing:
            patch_diagnostics.append("git_apply_missing_path")
        checked.append({
            "id": patch["id"],
            "path": patch["path"],
            "sha256": patch["sha256"],
            "reverseApplies": code == 0 and not conflicts and not missing,
            "expectedPathCount": len(paths),
            "conflicts": conflicts,
            "missing": missing,
            "diagnostics": patch_diagnostics,
        })

    actual_paths = {item["path"].replace("\\", "/") for item in status_paths}
    missing_overlay_paths = sorted(expected_paths - actual_paths)
    extra_paths = sorted(actual_paths - expected_paths)
    if not status_paths:
        diagnostics.append("candidate_not_patched")
    if missing_overlay_paths:
        diagnostics.append("candidate_missing_overlay_paths")
    if extra_paths:
        diagnostics.append("candidate_extra_paths")

    valid = (
        head == target["commit"]
        and bool(status_paths)
        and all(item["reverseApplies"] for item in checked)
        and not missing_overlay_paths
        and not extra_paths
    )
    return {
        "schemaVersion": 1,
        "valid": valid,
        "candidate": {
            "root": str(root),
            "headCommit": head,
            "clean": not status_paths,
            "statusPathCount": len(status_paths),
        },
        "target": {
            "ref": target["ref"],
            "commit": target["commit"],
            "checkedOut": head == target["commit"],
        },
        "overlay": {
            "expectedPathCount": len(expected_paths),
            "missingPaths": missing_overlay_paths[:MAX_APPLY_DIAGNOSTIC_PATHS],
            "extraPaths": extra_paths[:MAX_APPLY_DIAGNOSTIC_PATHS],
        },
        "diagnostics": sorted(set(diagnostics)),
        "patches": checked,
    }


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_candidate_path(source: Path, candidate: Path) -> None:
    if candidate.exists() or candidate.is_symlink():
        raise SyncError(f"candidate path already exists: {candidate}")
    if not candidate.parent.is_dir():
        raise SyncError(f"candidate parent directory does not exist: {candidate.parent}")
    if _is_within(candidate, source) or _is_within(source, candidate):
        raise SyncError("candidate path must not contain or be contained by the source checkout")


def prepare_candidate(
    dsh_root: Path,
    candidate_root: Path,
    repo_root: Path,
    lock: dict[str, Any],
) -> dict[str, Any]:
    """Create a fresh patched candidate without mutating the source checkout."""

    source = _git_root(dsh_root)
    candidate = candidate_root.resolve()
    _validate_candidate_path(source, candidate)
    patches = verify_patches(repo_root, lock)
    target = lock["upstream"]["target"]
    target_commit = target["commit"]
    source_head = _git_value(source, "rev-parse", "HEAD")
    if source_head is None:
        raise SyncError("source checkout has no committed HEAD")
    cat_code, _, cat_stderr = _run_git(source, "cat-file", "-e", f"{target_commit}^{{commit}}")
    if cat_code != 0:
        raise SyncError(
            f"locked target commit is not available locally: {target_commit} "
            f"({cat_stderr.strip() or 'git object lookup failed'})"
        )

    staging = candidate.parent / f".{candidate.name}.staging-{uuid.uuid4().hex}"
    if staging.exists() or staging.is_symlink():
        raise SyncError(f"staging path unexpectedly exists: {staging}")
    try:
        clone_code, _, clone_stderr = _run_command(
            [
                "git",
                "clone",
                "--shared",
                "--no-checkout",
                "--no-tags",
                str(source),
                str(staging),
            ]
        )
        if clone_code != 0:
            raise SyncError(f"cannot create candidate clone: {clone_stderr.strip() or 'git clone failed'}")

        autocrlf_code, _, autocrlf_stderr = _run_git(staging, "config", "core.autocrlf", "false")
        if autocrlf_code != 0:
            raise SyncError(
                f"cannot configure candidate line endings: "
                f"{autocrlf_stderr.strip() or 'git config failed'}"
            )
        checkout_code, _, checkout_stderr = _run_git(staging, "checkout", "--detach", target_commit)
        if checkout_code != 0:
            raise SyncError(
                f"cannot check out locked target {target_commit}: "
                f"{checkout_stderr.strip() or 'git checkout failed'}"
            )

        applied: list[dict[str, str]] = []
        for patch in patches:
            patch_path = (repo_root.resolve() / patch["path"]).resolve()
            check_code, _, check_stderr = _run_git(
                staging,
                "apply",
                "--3way",
                "--check",
                "--whitespace=nowarn",
                str(patch_path),
            )
            if check_code != 0:
                raise SyncError(
                    f"overlay patch conflicts for {patch['id']}: "
                    f"{check_stderr.strip() or 'git apply check failed'}"
                )
            apply_code, _, apply_stderr = _run_git(
                staging,
                "apply",
                "--3way",
                "--whitespace=nowarn",
                str(patch_path),
            )
            if apply_code != 0:
                raise SyncError(
                    f"overlay patch could not be applied for {patch['id']}: "
                    f"{apply_stderr.strip() or 'git apply failed'}"
                )
            applied.append(patch)

        candidate_status = _status_paths(staging)
        candidate_head = _git_value(staging, "rev-parse", "HEAD")
        staging.rename(candidate)
        return {
            "schemaVersion": 1,
            "sourceRoot": str(source),
            "sourceHead": source_head,
            "candidateRoot": str(candidate),
            "target": {"ref": target["ref"], "commit": target_commit},
            "patches": applied,
            "candidate": {
                "headCommit": candidate_head,
                "overlayChangedPathCount": len(candidate_status),
            },
            "next": "run the DSH and DevFrame candidate verification gates before activation",
        }
    except Exception:
        if staging.exists() and not staging.is_symlink():
            shutil.rmtree(staging)
        raise


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("validate", "verify", "inventory", "check-overlay", "prepare-candidate", "verify-prepared"),
        nargs="?",
        default="validate",
        help="validate the lock or produce a read-only checkout inventory",
    )
    parser.add_argument(
        "--lock",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "templates" / "runtime-bootstrap" / "dsh-upstream.lock.json",
    )
    parser.add_argument("--dsh-root", type=Path, help="local DSH checkout for inventory")
    parser.add_argument(
        "--candidate-root",
        type=Path,
        help="candidate path for check-overlay, prepare-candidate, or verify-prepared",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository containing the hash-pinned overlay patch",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="return exit code 2 unless the checkout is a clean captured baseline",
    )
    args = parser.parse_args(argv)

    try:
        lock = load_lock(args.lock.resolve())
        if args.command == "validate":
            output = {"valid": True, "lock": str(args.lock.resolve())}
        elif args.command == "verify":
            output = {
                "valid": True,
                "lock": str(args.lock.resolve()),
                "patches": verify_patches(args.repo_root.resolve(), lock),
            }
        elif args.command == "inventory":
            if args.dsh_root is None:
                raise SyncError("inventory requires --dsh-root")
            output = inventory(args.dsh_root.resolve(), lock)
        elif args.command == "check-overlay":
            if args.candidate_root is None:
                raise SyncError("check-overlay requires --candidate-root")
            output = check_overlay(args.candidate_root, args.repo_root.resolve(), lock)
        elif args.command == "verify-prepared":
            if args.candidate_root is None:
                raise SyncError("verify-prepared requires --candidate-root")
            output = verify_prepared_candidate(args.candidate_root, args.repo_root.resolve(), lock)
        else:
            if args.dsh_root is None or args.candidate_root is None:
                raise SyncError("prepare-candidate requires --dsh-root and --candidate-root")
            output = prepare_candidate(
                args.dsh_root.resolve(),
                args.candidate_root,
                args.repo_root.resolve(),
                lock,
            )
    except SyncError as exc:
        if args.json:
            _print_json({"valid": False, "error": str(exc)})
        else:
            print(f"[DSH-SYNC-BLOCKED] {exc}", file=sys.stderr)
        return 1

    if args.json or args.command in {"inventory", "check-overlay", "verify-prepared"}:
        _print_json(output)
    elif args.command == "prepare-candidate":
        print(f"[DSH-SYNC-PASS] prepared {output['candidateRoot']}")
    else:
        print(f"[DSH-SYNC-PASS] validated {output['lock']}")
    if args.require_ready and args.command == "inventory" and not output["applyReadiness"]["safeToApply"]:
        return 2
    if args.command == "check-overlay" and not output["valid"]:
        return 1
    if args.command == "verify-prepared" and not output["valid"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
