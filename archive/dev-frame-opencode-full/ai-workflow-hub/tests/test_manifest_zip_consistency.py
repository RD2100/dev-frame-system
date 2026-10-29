"""Test verify_manifest_zip_consistency — manifest-zip cross-check."""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

# The tools/ directory lives in the monorepo root, above ai-workflow-hub/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.review_pack_flow import (
    verify_manifest_zip_consistency,
    generate_manifest,
    create_zip,
    sha256_hex,
)


def _write_manifest(path: Path, entries: list[tuple[str, str]]) -> None:
    lines = [
        "# Pack Manifest",
        "",
        "Task ID: test",
        "Review Run ID: test",
        "Generated: test",
        "",
        "| File | SHA256 |",
        "|---|---|",
    ]
    for name, digest in entries:
        lines.append(f"| {name} | {digest} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_consistent_pack_passes(tmp_path: Path):
    """A pack where manifest and zip agree should pass consistency check."""
    # Create files
    (tmp_path / "a.txt").write_text("hello a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("hello b", encoding="utf-8")
    h_a = sha256_hex(tmp_path / "a.txt")
    h_b = sha256_hex(tmp_path / "b.txt")

    _write_manifest(tmp_path / "PACK_MANIFEST.md", [
        ("a.txt", h_a),
        ("b.txt", h_b),
    ])

    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(tmp_path / "a.txt", "a.txt")
        zf.write(tmp_path / "b.txt", "b.txt")

    result = verify_manifest_zip_consistency(tmp_path, zip_name="test.zip")
    assert result["consistency_verdict"] == "passed", f"Expected passed, got: {result}"
    assert result["manifest_file_count"] == 2
    assert result["zip_entry_count"] == 2
    assert result["files_in_both"] == 2
    assert result["manifest_only"] == []
    assert result["zip_only"] == []
    assert result["hash_mismatches"] == []
    assert result["hash_verified"] == 2


def test_missing_manifest_entry_detected(tmp_path: Path):
    """Zip contains a file not in manifest — should fail."""
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "b.txt").write_text("world", encoding="utf-8")

    _write_manifest(tmp_path / "PACK_MANIFEST.md", [
        ("a.txt", sha256_hex(tmp_path / "a.txt")),
        # b.txt is NOT in manifest
    ])

    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(tmp_path / "a.txt", "a.txt")
        zf.write(tmp_path / "b.txt", "b.txt")  # extra

    result = verify_manifest_zip_consistency(tmp_path, zip_name="test.zip")
    assert result["consistency_verdict"] == "failed"
    assert "b.txt" in result["zip_only"]


def test_extra_zip_entry_detected(tmp_path: Path):
    """Manifest entry missing from zip — should fail."""
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")

    _write_manifest(tmp_path / "PACK_MANIFEST.md", [
        ("a.txt", sha256_hex(tmp_path / "a.txt")),
        ("missing.txt", "abc123def456"),
    ])

    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(tmp_path / "a.txt", "a.txt")
        # missing.txt is NOT in zip

    result = verify_manifest_zip_consistency(tmp_path, zip_name="test.zip")
    assert result["consistency_verdict"] == "failed"
    assert "missing.txt" in result["manifest_only"]


def test_hash_mismatch_detected(tmp_path: Path):
    """Manifest hash differs from actual file hash — should fail."""
    (tmp_path / "a.txt").write_text("actual content", encoding="utf-8")

    _write_manifest(tmp_path / "PACK_MANIFEST.md", [
        ("a.txt", "0000000000000000000000000000000000000000000000000000000000000000"),
    ])

    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(tmp_path / "a.txt", "a.txt")

    result = verify_manifest_zip_consistency(tmp_path, zip_name="test.zip")
    assert result["consistency_verdict"] == "failed"
    assert len(result["hash_mismatches"]) == 1
    assert result["hash_verified"] == 0


def test_missing_zip_file_graceful(tmp_path: Path):
    """When zip doesn't exist, zip entries are empty — cross-ref still works."""
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")

    _write_manifest(tmp_path / "PACK_MANIFEST.md", [
        ("a.txt", sha256_hex(tmp_path / "a.txt")),
    ])

    result = verify_manifest_zip_consistency(tmp_path, zip_name="nonexistent.zip")
    assert result["zip_entry_count"] == 0
    # manifest_only includes all manifest entries since zip has none
    assert "a.txt" in result["manifest_only"]


def test_self_referential_entries_excluded_from_hash_check(tmp_path: Path):
    """PACK_MANIFEST.md, VALIDATION_RESULT.json etc. are excluded from hash check."""
    (tmp_path / "a.txt").write_text("content", encoding="utf-8")
    h = sha256_hex(tmp_path / "a.txt")

    _write_manifest(tmp_path / "PACK_MANIFEST.md", [
        ("a.txt", h),
        ("PACK_MANIFEST.md", "hash intentionally excluded for self-referential verification artifact"),
    ])

    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(tmp_path / "a.txt", "a.txt")
        zf.write(tmp_path / "PACK_MANIFEST.md", "PACK_MANIFEST.md")

    result = verify_manifest_zip_consistency(tmp_path, zip_name="test.zip")
    assert result["consistency_verdict"] == "passed"
    assert result["hash_verified"] == 1  # only a.txt
    assert result["hash_excluded"] == 1  # PACK_MANIFEST.md excluded


def test_zip_entry_bytes_differ_from_disk_file(tmp_path: Path):
    """Disk file matches manifest hash, but zip entry contains tampered data."""
    content_original = b"original content for disk"
    content_tampered = b"tampered content in zip"

    # Write original to disk
    (tmp_path / "a.txt").write_bytes(content_original)
    h_original = hashlib.sha256(content_original).hexdigest()

    # Manifest has the ORIGINAL hash (correct)
    _write_manifest(tmp_path / "PACK_MANIFEST.md", [
        ("a.txt", h_original),
    ])

    # But zip contains TAMPERED bytes (different from disk)
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a.txt", content_tampered)

    result = verify_manifest_zip_consistency(tmp_path, zip_name="test.zip")
    assert result["consistency_verdict"] == "failed", \
        f"Should detect tampered zip entry, got: {result['consistency_verdict']}"
    assert len(result["hash_mismatches"]) == 1, \
        f"Expected 1 hash mismatch, got: {result['hash_mismatches']}"
    assert "a.txt" in result["hash_mismatches"][0]
    assert result["hash_verified"] == 0


def test_integration_with_review_pack_flow(tmp_path: Path):
    """End-to-end: generate manifest + zip, then verify consistency."""
    (tmp_path / "f1.md").write_text("file1", encoding="utf-8")
    (tmp_path / "f2.txt").write_text("file2", encoding="utf-8")

    generate_manifest(tmp_path, "test-task", "test-run", "test.zip")
    create_zip(tmp_path, "test.zip")

    result = verify_manifest_zip_consistency(tmp_path, zip_name="test.zip")
    assert result["consistency_verdict"] == "passed", \
        f"Integration failed: {json.dumps(result, indent=2)}"
    assert result["files_in_both"] >= 3  # f1.md, f2.txt, PACK_MANIFEST.md
