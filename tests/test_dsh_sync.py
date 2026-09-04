import json
import hashlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dsh_sync.py"
LOCK_TEMPLATE = ROOT / "templates" / "runtime-bootstrap" / "dsh-upstream.lock.json"


def run_git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def make_checkout(tmp_path: Path) -> tuple[Path, str]:
    checkout = tmp_path / "dsh"
    checkout.mkdir()
    run_git(checkout, "init", "--initial-branch", "master")
    run_git(checkout, "config", "user.email", "dsh-sync-test@example.invalid")
    run_git(checkout, "config", "user.name", "DSH sync test")
    (checkout / "README.md").write_text("baseline\n", encoding="utf-8")
    run_git(checkout, "add", "README.md")
    run_git(checkout, "commit", "-m", "baseline")
    return checkout, run_git(checkout, "rev-parse", "HEAD")


def make_lock(tmp_path: Path, captured_head: str) -> Path:
    lock = json.loads(LOCK_TEMPLATE.read_text(encoding="utf-8"))
    lock["baseline"]["capturedHeadCommit"] = captured_head
    lock["baseline"]["knownUpstreamCommit"] = captured_head
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(lock), encoding="utf-8")
    return path


def make_fixture_lock(tmp_path: Path, target_commit: str, patch_path: Path) -> Path:
    lock = json.loads(LOCK_TEMPLATE.read_text(encoding="utf-8"))
    relative_patch = patch_path.relative_to(tmp_path).as_posix()
    lock["upstream"]["target"] = {"ref": "fixture", "commit": target_commit}
    lock["baseline"]["knownUpstreamCommit"] = target_commit
    lock["baseline"]["capturedHeadCommit"] = target_commit
    lock["overlay"]["patches"] = [
        {
            "id": "fixture-overlay",
            "path": relative_patch,
            "sha256": hashlib.sha256(patch_path.read_bytes()).hexdigest(),
        }
    ]
    path = tmp_path / "fixture-lock.json"
    path.write_text(json.dumps(lock), encoding="utf-8")
    return path


def run_sync(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--json"],
        check=False,
        capture_output=True,
        text=True,
    )


def run_sync_plain(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_validate_accepts_current_lock():
    result = run_sync("validate", "--lock", str(LOCK_TEMPLATE))
    assert result.returncode == 0
    assert json.loads(result.stdout)["valid"] is True


def test_inventory_marks_clean_baseline_ready(tmp_path):
    checkout, head = make_checkout(tmp_path)
    lock = make_lock(tmp_path, head)

    result = run_sync("inventory", "--dsh-root", str(checkout), "--lock", str(lock))

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["worktree"]["status"] == "ready_for_candidate"
    assert payload["applyReadiness"]["safeToApply"] is True
    assert payload["worktree"]["paths"] == []


def test_inventory_blocks_dirty_checkout(tmp_path):
    checkout, head = make_checkout(tmp_path)
    lock = make_lock(tmp_path, head)
    (checkout / "local-change.txt").write_text("do not lose me\n", encoding="utf-8")

    result = run_sync("inventory", "--dsh-root", str(checkout), "--lock", str(lock))

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["worktree"]["status"] == "blocked_dirty_worktree"
    assert payload["applyReadiness"]["safeToApply"] is False
    assert payload["worktree"]["untrackedCount"] == 1
    assert payload["worktree"]["paths"][0]["path"] == "local-change.txt"


def test_require_ready_fails_closed_for_dirty_checkout(tmp_path):
    checkout, head = make_checkout(tmp_path)
    lock = make_lock(tmp_path, head)
    (checkout / "local-change.txt").write_text("do not lose me\n", encoding="utf-8")

    result = run_sync(
        "inventory",
        "--dsh-root",
        str(checkout),
        "--lock",
        str(lock),
        "--require-ready",
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["applyReadiness"]["safeToApply"] is False


def test_prepare_candidate_clones_locked_head_and_applies_overlay(tmp_path):
    source, head = make_checkout(tmp_path)
    tracked = source / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    run_git(source, "add", "tracked.txt")
    run_git(source, "commit", "-m", "tracked baseline")
    head = run_git(source, "rev-parse", "HEAD")

    tracked.write_text("after\n", encoding="utf-8")
    (source / "local-only.txt").write_text("must stay out\n", encoding="utf-8")
    patch_path = tmp_path / "overlay.patch"
    patch_path.write_bytes(
        (run_git(source, "diff", "--binary", "HEAD", "--", "tracked.txt") + "\n").encode(),
    )
    lock = make_fixture_lock(tmp_path, head, patch_path)
    candidate = tmp_path / "candidate"

    result = run_sync(
        "prepare-candidate",
        "--dsh-root",
        str(source),
        "--candidate-root",
        str(candidate),
        "--repo-root",
        str(tmp_path),
        "--lock",
        str(lock),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["target"]["commit"] == head
    assert payload["patches"][0]["id"] == "fixture-overlay"
    assert payload["candidate"]["headCommit"] == head
    assert (candidate / "tracked.txt").read_text(encoding="utf-8") == "after\n"
    assert not (candidate / "local-only.txt").exists()
    assert tracked.read_text(encoding="utf-8") == "after\n"
    assert (source / "local-only.txt").read_text(encoding="utf-8") == "must stay out\n"


def test_prepare_candidate_plain_output_reports_candidate_path(tmp_path):
    source, head = make_checkout(tmp_path)
    tracked = source / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    run_git(source, "add", "tracked.txt")
    run_git(source, "commit", "-m", "tracked baseline")
    head = run_git(source, "rev-parse", "HEAD")
    tracked.write_text("after\n", encoding="utf-8")
    patch_path = tmp_path / "overlay.patch"
    patch_path.write_bytes(
        (run_git(source, "diff", "--binary", "HEAD", "--", "tracked.txt") + "\n").encode(),
    )
    lock = make_fixture_lock(tmp_path, head, patch_path)
    candidate = tmp_path / "candidate"

    result = run_sync_plain(
        "prepare-candidate",
        "--dsh-root",
        str(source),
        "--candidate-root",
        str(candidate),
        "--repo-root",
        str(tmp_path),
        "--lock",
        str(lock),
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"[DSH-SYNC-PASS] prepared {candidate.resolve()}"
    assert candidate.is_dir()


def test_prepare_candidate_cleans_staging_after_patch_conflict(tmp_path):
    source, _ = make_checkout(tmp_path)
    tracked = source / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    run_git(source, "add", "tracked.txt")
    run_git(source, "commit", "-m", "tracked baseline")
    head = run_git(source, "rev-parse", "HEAD")
    patch_path = tmp_path / "conflict.patch"
    patch_path.write_text(
        "diff --git a/tracked.txt b/tracked.txt\n"
        "--- a/tracked.txt\n"
        "+++ b/tracked.txt\n"
        "@@ -1 +1 @@\n"
        "-not-present\n"
        "+after\n",
        encoding="utf-8",
    )
    lock = make_fixture_lock(tmp_path, head, patch_path)
    candidate = tmp_path / "candidate"

    result = run_sync(
        "prepare-candidate",
        "--dsh-root",
        str(source),
        "--candidate-root",
        str(candidate),
        "--repo-root",
        str(tmp_path),
        "--lock",
        str(lock),
    )

    assert result.returncode == 1
    assert "overlay patch conflicts" in json.loads(result.stdout)["error"]
    assert not candidate.exists()
    assert not list(tmp_path.glob(".candidate.staging-*"))


def test_prepare_candidate_rejects_existing_or_nested_destination(tmp_path):
    source, head = make_checkout(tmp_path)
    patch_path = tmp_path / "empty.patch"
    patch_path.write_text("", encoding="utf-8")
    lock = make_fixture_lock(tmp_path, head, patch_path)
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "keep.txt").write_text("keep\n", encoding="utf-8")

    existing_result = run_sync(
        "prepare-candidate",
        "--dsh-root",
        str(source),
        "--candidate-root",
        str(existing),
        "--repo-root",
        str(tmp_path),
        "--lock",
        str(lock),
    )
    assert existing_result.returncode == 1
    assert "already exists" in json.loads(existing_result.stdout)["error"]
    assert (existing / "keep.txt").exists()

    nested_result = run_sync(
        "prepare-candidate",
        "--dsh-root",
        str(source),
        "--candidate-root",
        str(source / "nested-candidate"),
        "--repo-root",
        str(tmp_path),
        "--lock",
        str(lock),
    )
    assert nested_result.returncode == 1
    assert "must not contain or be contained" in json.loads(nested_result.stdout)["error"]


def test_validate_rejects_absolute_patch_path(tmp_path):
    lock = json.loads(LOCK_TEMPLATE.read_text(encoding="utf-8"))
    lock["overlay"]["mode"] = "patch-stack"
    lock["overlay"]["patches"] = [
        {
            "id": "unsafe-path",
            "path": "C:\\outside.patch",
            "sha256": "0" * 64,
        }
    ]
    path = tmp_path / "invalid-lock.json"
    path.write_text(json.dumps(lock), encoding="utf-8")

    result = run_sync("validate", "--lock", str(path))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["valid"] is False
    assert "must be relative" in payload["error"]


def test_verify_checks_current_overlay_hash():
    result = run_sync("verify", "--lock", str(LOCK_TEMPLATE))

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    lock = json.loads(LOCK_TEMPLATE.read_text(encoding="utf-8"))
    expected_id = lock["overlay"]["patches"][0]["id"]
    assert payload["patches"][0]["id"] == expected_id


def test_verify_rejects_overlay_hash_drift(tmp_path):
    lock = json.loads(LOCK_TEMPLATE.read_text(encoding="utf-8"))
    lock["overlay"]["patches"][0]["sha256"] = "0" * 64
    path = tmp_path / "invalid-lock.json"
    path.write_text(json.dumps(lock), encoding="utf-8")

    result = run_sync("verify", "--lock", str(path))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["valid"] is False
    assert "hash mismatch" in payload["error"]


def test_check_overlay_reports_clean_candidate_without_mutating_it(tmp_path):
    source, head = make_checkout(tmp_path)
    tracked = source / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    run_git(source, "add", "tracked.txt")
    run_git(source, "commit", "-m", "tracked baseline")
    head = run_git(source, "rev-parse", "HEAD")
    tracked.write_text("after\n", encoding="utf-8")
    patch_path = tmp_path / "overlay.patch"
    patch_path.write_bytes((run_git(source, "diff", "--binary", "HEAD", "--", "tracked.txt") + "\n").encode())
    lock = make_fixture_lock(tmp_path, head, patch_path)
    candidate = tmp_path / "candidate"
    subprocess.run(
        ["git", "clone", "--shared", str(source), str(candidate)],
        check=True,
        capture_output=True,
        text=True,
    )
    before_status = run_git(candidate, "status", "--porcelain=v1")
    before_head = run_git(candidate, "rev-parse", "HEAD")

    result = run_sync(
        "check-overlay",
        "--candidate-root",
        str(candidate),
        "--repo-root",
        str(tmp_path),
        "--lock",
        str(lock),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    assert payload["applies"] is True
    assert payload["patches"][0]["applies"] is True
    assert payload["patches"][0]["conflicts"] == []
    assert payload["patches"][0]["missing"] == []
    assert run_git(candidate, "status", "--porcelain=v1") == before_status
    assert run_git(candidate, "rev-parse", "HEAD") == before_head
    assert (candidate / "tracked.txt").read_text(encoding="utf-8") == "before\n"


def test_check_overlay_reports_conflict_paths_and_preserves_candidate(tmp_path):
    source, _ = make_checkout(tmp_path)
    tracked = source / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    run_git(source, "add", "tracked.txt")
    run_git(source, "commit", "-m", "tracked baseline")
    head = run_git(source, "rev-parse", "HEAD")
    tracked.write_text("after\n", encoding="utf-8")
    patch_path = tmp_path / "overlay.patch"
    patch_path.write_bytes((run_git(source, "diff", "--binary", "HEAD", "--", "tracked.txt") + "\n").encode())
    lock = make_fixture_lock(tmp_path, head, patch_path)
    candidate = tmp_path / "candidate"
    subprocess.run(
        ["git", "clone", "--shared", str(source), str(candidate)],
        check=True,
        capture_output=True,
        text=True,
    )
    run_git(candidate, "config", "user.email", "dsh-sync-test@example.invalid")
    run_git(candidate, "config", "user.name", "DSH sync test")
    (candidate / "tracked.txt").write_text("other\n", encoding="utf-8")
    run_git(candidate, "add", "tracked.txt")
    run_git(candidate, "commit", "-m", "candidate drift")
    before_status = run_git(candidate, "status", "--porcelain=v1")
    before_head = run_git(candidate, "rev-parse", "HEAD")
    before_content = (candidate / "tracked.txt").read_bytes()

    result = run_sync(
        "check-overlay",
        "--candidate-root",
        str(candidate),
        "--repo-root",
        str(tmp_path),
        "--lock",
        str(lock),
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["valid"] is False
    assert payload["applies"] is False
    assert "tracked.txt" in payload["patches"][0]["conflicts"]
    assert payload["patches"][0]["missing"] == []
    assert run_git(candidate, "status", "--porcelain=v1") == before_status
    assert run_git(candidate, "rev-parse", "HEAD") == before_head
    assert (candidate / "tracked.txt").read_bytes() == before_content


def test_check_overlay_rejects_dirty_candidate_even_when_patch_is_applicable(tmp_path):
    source, _ = make_checkout(tmp_path)
    tracked = source / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    run_git(source, "add", "tracked.txt")
    run_git(source, "commit", "-m", "tracked baseline")
    head = run_git(source, "rev-parse", "HEAD")
    tracked.write_text("after\n", encoding="utf-8")
    patch_path = tmp_path / "overlay.patch"
    patch_path.write_bytes((run_git(source, "diff", "--binary", "HEAD", "--", "tracked.txt") + "\n").encode())
    lock = make_fixture_lock(tmp_path, head, patch_path)
    candidate = tmp_path / "candidate"
    subprocess.run(
        ["git", "clone", "--shared", str(source), str(candidate)],
        check=True,
        capture_output=True,
        text=True,
    )
    (candidate / "local-change.txt").write_text("must remain untouched\n", encoding="utf-8")
    before_status = run_git(candidate, "status", "--porcelain=v1")
    before_head = run_git(candidate, "rev-parse", "HEAD")
    before_content = (candidate / "local-change.txt").read_bytes()

    result = run_sync(
        "check-overlay",
        "--candidate-root",
        str(candidate),
        "--repo-root",
        str(tmp_path),
        "--lock",
        str(lock),
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["valid"] is False
    assert payload["applies"] is False
    assert payload["candidate"]["clean"] is False
    assert payload["diagnostics"] == ["candidate_dirty"]
    assert payload["patches"][0]["applies"] is True
    assert run_git(candidate, "status", "--porcelain=v1") == before_status
    assert run_git(candidate, "rev-parse", "HEAD") == before_head
    assert (candidate / "local-change.txt").read_bytes() == before_content


def test_check_overlay_rejects_clean_candidate_at_wrong_target_commit(tmp_path):
    source, _ = make_checkout(tmp_path)
    tracked = source / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    run_git(source, "add", "tracked.txt")
    run_git(source, "commit", "-m", "tracked baseline")
    head = run_git(source, "rev-parse", "HEAD")
    tracked.write_text("after\n", encoding="utf-8")
    patch_path = tmp_path / "overlay.patch"
    patch_path.write_bytes((run_git(source, "diff", "--binary", "HEAD", "--", "tracked.txt") + "\n").encode())
    lock = make_fixture_lock(tmp_path, head, patch_path)
    candidate = tmp_path / "candidate"
    subprocess.run(
        ["git", "clone", "--shared", str(source), str(candidate)],
        check=True,
        capture_output=True,
        text=True,
    )
    run_git(candidate, "config", "user.email", "dsh-sync-test@example.invalid")
    run_git(candidate, "config", "user.name", "DSH sync test")
    (candidate / "unrelated.txt").write_text("candidate-only\n", encoding="utf-8")
    run_git(candidate, "add", "unrelated.txt")
    run_git(candidate, "commit", "-m", "candidate drift")
    before_status = run_git(candidate, "status", "--porcelain=v1")
    before_head = run_git(candidate, "rev-parse", "HEAD")

    result = run_sync(
        "check-overlay",
        "--candidate-root",
        str(candidate),
        "--repo-root",
        str(tmp_path),
        "--lock",
        str(lock),
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["valid"] is False
    assert payload["applies"] is False
    assert payload["candidate"]["clean"] is True
    assert payload["target"]["checkedOut"] is False
    assert payload["diagnostics"] == ["candidate_target_mismatch"]
    assert payload["patches"][0]["applies"] is True
    assert run_git(candidate, "status", "--porcelain=v1") == before_status
    assert run_git(candidate, "rev-parse", "HEAD") == before_head


def test_verify_prepared_accepts_overlay_applied_by_prepare_candidate(tmp_path):
    source, _ = make_checkout(tmp_path)
    tracked = source / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    run_git(source, "add", "tracked.txt")
    run_git(source, "commit", "-m", "tracked baseline")
    head = run_git(source, "rev-parse", "HEAD")
    tracked.write_text("after\n", encoding="utf-8")
    patch_path = tmp_path / "overlay.patch"
    patch_path.write_bytes((run_git(source, "diff", "--binary", "HEAD", "--", "tracked.txt") + "\n").encode())
    lock = make_fixture_lock(tmp_path, head, patch_path)
    candidate = tmp_path / "candidate"

    prepared = run_sync(
        "prepare-candidate",
        "--dsh-root",
        str(source),
        "--candidate-root",
        str(candidate),
        "--repo-root",
        str(tmp_path),
        "--lock",
        str(lock),
    )
    assert prepared.returncode == 0, prepared.stderr
    before_status = run_git(candidate, "status", "--porcelain=v1")
    before_head = run_git(candidate, "rev-parse", "HEAD")

    result = run_sync(
        "verify-prepared",
        "--candidate-root",
        str(candidate),
        "--repo-root",
        str(tmp_path),
        "--lock",
        str(lock),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    assert payload["candidate"]["clean"] is False
    assert payload["candidate"]["statusPathCount"] == 1
    assert payload["overlay"]["expectedPathCount"] == 1
    assert payload["overlay"]["missingPaths"] == []
    assert payload["overlay"]["extraPaths"] == []
    assert payload["patches"][0]["reverseApplies"] is True
    assert run_git(candidate, "status", "--porcelain=v1") == before_status
    assert run_git(candidate, "rev-parse", "HEAD") == before_head
    assert (candidate / "tracked.txt").read_text(encoding="utf-8") == "after\n"


def test_verify_prepared_rejects_unrelated_candidate_paths(tmp_path):
    source, _ = make_checkout(tmp_path)
    tracked = source / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    run_git(source, "add", "tracked.txt")
    run_git(source, "commit", "-m", "tracked baseline")
    head = run_git(source, "rev-parse", "HEAD")
    tracked.write_text("after\n", encoding="utf-8")
    patch_path = tmp_path / "overlay.patch"
    patch_path.write_bytes((run_git(source, "diff", "--binary", "HEAD", "--", "tracked.txt") + "\n").encode())
    lock = make_fixture_lock(tmp_path, head, patch_path)
    candidate = tmp_path / "candidate"

    prepared = run_sync(
        "prepare-candidate",
        "--dsh-root",
        str(source),
        "--candidate-root",
        str(candidate),
        "--repo-root",
        str(tmp_path),
        "--lock",
        str(lock),
    )
    assert prepared.returncode == 0, prepared.stderr
    (candidate / "unrelated.txt").write_text("must block activation\n", encoding="utf-8")

    result = run_sync(
        "verify-prepared",
        "--candidate-root",
        str(candidate),
        "--repo-root",
        str(tmp_path),
        "--lock",
        str(lock),
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["valid"] is False
    assert payload["diagnostics"] == ["candidate_extra_paths"]
    assert payload["overlay"]["extraPaths"] == ["unrelated.txt"]
    assert payload["patches"][0]["reverseApplies"] is True
    assert (candidate / "unrelated.txt").read_text(encoding="utf-8") == "must block activation\n"


def test_verify_prepared_rejects_clean_unpatched_candidate(tmp_path):
    source, head = make_checkout(tmp_path)
    patch_path = tmp_path / "overlay.patch"
    patch_path.write_text(
        "diff --git a/README.md b/README.md\n"
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -1 +1 @@\n"
        "-baseline\n"
        "+patched\n",
        encoding="utf-8",
    )
    lock = make_fixture_lock(tmp_path, head, patch_path)
    candidate = tmp_path / "candidate"
    subprocess.run(
        ["git", "clone", "--shared", str(source), str(candidate)],
        check=True,
        capture_output=True,
        text=True,
    )

    result = run_sync(
        "verify-prepared",
        "--candidate-root",
        str(candidate),
        "--repo-root",
        str(tmp_path),
        "--lock",
        str(lock),
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["valid"] is False
    assert payload["candidate"]["clean"] is True
    assert payload["diagnostics"] == ["candidate_not_patched", "overlay_not_applied"]
    assert payload["patches"][0]["reverseApplies"] is False
