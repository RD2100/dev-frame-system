import hashlib
import subprocess


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_stage_exact_paths_rejects_dirty_index_and_hash_drift(tmp_path):
    from ai_workflow_hub.git_utils import stage_exact_paths

    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.test")
    _git(tmp_path, "config", "user.name", "test")
    accepted = tmp_path / "accepted.txt"
    extra = tmp_path / "extra.txt"
    accepted.write_text("accepted", encoding="utf-8")
    extra.write_text("extra", encoding="utf-8")
    baseline = {"accepted.txt": _sha(accepted)}
    _git(tmp_path, "add", "extra.txt")
    ok, reason = stage_exact_paths(str(tmp_path), ["accepted.txt"], baseline)
    assert not ok and "index" in reason
    _git(tmp_path, "reset")
    accepted.write_text("drift", encoding="utf-8")
    ok, reason = stage_exact_paths(str(tmp_path), ["accepted.txt"], baseline)
    assert not ok and "drift" in reason
