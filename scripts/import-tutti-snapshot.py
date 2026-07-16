import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


EXCLUDED_DIR_NAMES = frozenset({
    ".codex", ".git", "node_modules", ".codegraph",
    ".tmp", ".cache", "dist", "out", "coverage",
})

SENSITIVE_FILE_NAMES = frozenset({
    ".env",
})

SENSITIVE_FILE_SUFFIXES = (
    ".db", ".db-wal", ".db-shm",
    ".log", ".pid",
    ".key", ".pem", ".crt", ".cert", ".der",
    ".exe", ".dll", ".so", ".dylib",
)

SENSITIVE_FILE_PREFIXES = (
    ".env.",
)


def _is_path_excluded(relative_path: str) -> bool:
    parts = relative_path.replace("\\", "/").split("/")
    for i, part in enumerate(parts):
        if part in EXCLUDED_DIR_NAMES:
            return True
    filename = parts[-1]
    if filename in SENSITIVE_FILE_NAMES:
        return True
    if filename.endswith(SENSITIVE_FILE_SUFFIXES):
        return True
    if any(filename.startswith(p) for p in SENSITIVE_FILE_PREFIXES):
        return True
    return False


def _is_safe_path(relative_path: str) -> bool:
    if relative_path.startswith("/") or relative_path.startswith("\\"):
        return False
    if re.match(r"^[a-zA-Z]:", relative_path):
        return False
    normalized = relative_path.replace("\\", "/")
    if normalized.startswith("//"):
        return False
    if normalized.startswith("//./"):
        return False
    parts = normalized.split("/")
    for part in parts:
        if part == "..":
            return False
        if not part:
            return False
    return True


_SUPPORTED_MODES = frozenset({"100644", "100755"})


def _git_ls_tree(repo_path: str, tree_sha: str) -> list[tuple[str, str, str]]:
    result = subprocess.run(
        ["git", "-C", repo_path, "ls-tree", "-z", "-r", tree_sha],
        capture_output=True, check=True, timeout=60,
    )
    entries = []
    for record in result.stdout.rstrip(b"\x00").split(b"\x00"):
        if not record.strip():
            continue
        meta, path_bytes = record.split(b"\t", 1)
        mode, kind, blob_hash = meta.split(b" ", 2)
        mode_str = mode.decode("ascii")
        kind_str = kind.decode("ascii")
        if kind_str != "blob":
            continue
        if mode_str not in _SUPPORTED_MODES:
            raise ValueError(f"Unsupported mode {mode_str} for {path_bytes.decode('utf-8', errors='replace')}")
        entries.append((mode_str, blob_hash.decode("ascii"), path_bytes.decode("utf-8")))
    return entries


def _resolve_sha(repo_path: str, ref: str) -> str:
    result = subprocess.run(
        ["git", "-C", repo_path, "rev-parse", "--verify", f"{ref}^{{commit}}"],
        capture_output=True, text=True, check=True, timeout=30,
    )
    return result.stdout.strip()


def _is_ancestor(repo_path: str, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "-C", repo_path, "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True, timeout=30,
    )
    return result.returncode == 0


def _batch_get_blobs(
    repo_path: str, entries: list[tuple[str, str, str]],
) -> list[tuple[str, str, str, int, bytes]]:
    if not entries:
        return []
    input_data = b"".join(f"{blob_hash}\n".encode() for _, blob_hash, _ in entries)
    result = subprocess.run(
        ["git", "-C", repo_path, "cat-file", "--batch"],
        input=input_data, capture_output=True, timeout=120,
    )
    output = result.stdout
    results = []
    idx = 0
    for mode, blob_hash, path in entries:
        header_end = output.find(b"\n", idx)
        if header_end == -1:
            raise ValueError(f"Unexpected end of batch output for {blob_hash}")
        header = output[idx:header_end].decode()
        parts = header.split()
        if len(parts) != 3 or parts[0] != blob_hash or parts[1] != "blob":
            raise ValueError(f"Unexpected batch response for {blob_hash}: {header}")
        size = int(parts[2])
        content_start = header_end + 1
        content = output[content_start:content_start + size]
        results.append((mode, blob_hash, path, size, content))
        idx = content_start + size + 1
    return results


def _write_file_safely(dest_path: Path, content: bytes, mode_str: str = "100644"):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(content)
    if mode_str == "100755" and os.name != "nt":
        dest_path.chmod(0o755)


_PRIVATE_MARKER_PATTERNS: list[tuple[str, str]] = [
    ("private dev-frame-system checkout path", r"D:\\dev-frame-system|D:/dev-frame-system|D:\\devframe-system|D:/devframe-system"),
    ("private adjacent devframe root path", r"D:\\dev-frame\\|D:/dev-frame/|D:\\test-frame|D:/test-frame|D:\\agent-acceptance|D:/agent-acceptance"),
    ("private RD user home path", r"C:\\Users\\RD|C:/Users/RD"),
    ("concrete ChatGPT conversation URL", r"chatgpt\.com/c/[0-9a-fA-F-]{8,}"),
    ("mojibake replacement marker", r"\u951F\u65A4\u62F7|\uFFFD|\u9225\?|\u922B\?|\u922E\?|\u95BF\u719F\u67BB\u93B7"),
]

_TEXT_SCAN_EXTENSIONS = frozenset({".json", ".md", ".ps1", ".py", ".txt", ".yaml", ".yml"})

_PATCH_SPEC = {
    "file_path": "docs/architecture/workspace-terminal.md",
    "expected_blob_hash": "52cf415533490a677db10383e3233110ac8daef2",
    "original_text": "D:\\dev-frame-system\\.devframe-runtime\\toolchains\\go1.24.5\\go\\bin\\go.exe `",
    "replacement_text": "go `",
}


def _apply_text_patch(
    staging_dir: Path,
    blob_hash: str,
    file_path: str,
    expected_blob_hash: str,
    original_text: str,
    replacement_text: str,
) -> dict:
    if blob_hash != expected_blob_hash:
        raise ValueError(
            f"Patch blob hash mismatch for {file_path}: "
            f"expected {expected_blob_hash}, got {blob_hash}"
        )

    staging_path = staging_dir / file_path
    if not staging_path.exists():
        raise ValueError(f"Patch target not found in staging: {file_path}")

    content = staging_path.read_bytes()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(f"Patch target is not valid UTF-8: {file_path}")

    lines = text.splitlines(keepends=True)
    match_indices = [
        i for i, line in enumerate(lines)
        if line.rstrip("\r\n") == original_text
    ]

    if len(match_indices) != 1:
        raise ValueError(
            f"Patch original text {original_text!r} in {file_path} "
            f"found {len(match_indices)} times, expected exactly 1"
        )

    idx = match_indices[0]
    line_end = ""
    if lines[idx].endswith("\r\n"):
        line_end = "\r\n"
    elif lines[idx].endswith("\n"):
        line_end = "\n"

    lines[idx] = replacement_text + line_end
    new_content = "".join(lines).encode("utf-8")
    staging_path.write_bytes(new_content)

    return {
        "file": file_path,
        "original_git_blob": blob_hash,
        "original_text": original_text,
        "replacement_text": replacement_text,
        "patched_file_sha256": hashlib.sha256(new_content).hexdigest(),
    }


def _scan_private_markers(staging_dir: Path) -> list[str]:
    findings = []
    for fpath in staging_dir.rglob("*"):
        if not fpath.is_file():
            continue
        if fpath.suffix not in _TEXT_SCAN_EXTENSIONS:
            continue
        try:
            content = fpath.read_bytes()
        except Exception:
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for name, pattern in _PRIVATE_MARKER_PATTERNS:
            if re.search(pattern, text):
                relative = fpath.relative_to(staging_dir).as_posix()
                findings.append(f"{relative}: contains {name}")
    return findings


def _has_required_root_files(entries: list[tuple[str, str, str]]) -> tuple[bool, list[str]]:
    paths = {p for _, _, p in entries}
    missing = []
    for required in ("LICENSE", "NOTICE"):
        if required not in paths:
            missing.append(required)
    return len(missing) == 0, missing


_BUILD_ALLOWED = frozenset({
    "apps/desktop/build/entitlements.mac.inherit.plist",
    "apps/desktop/build/entitlements.mac.plist",
    "apps/desktop/build/icon.png",
})

_WALLPAPER_PATH = "apps/desktop/src/renderer/src/assets/workspace-wallpaper/tutti.png"
_MAX_BLOB_SIZE = 5 * 1024 * 1024

_TUTTI_CODEX_PATHS = frozenset({
    ".codex/skills/tutti-app-release/SKILL.md",
    ".codex/skills/tutti-app-release/agents/openai.yaml",
    ".codex/skills/tutti-architecture-review/SKILL.md",
    ".codex/skills/tutti-architecture-review/agents/openai.yaml",
    ".codex/skills/tutti-architecture-review/references/review-rules.json",
    ".codex/skills/tutti-architecture-review/references/scope-contract.md",
    ".codex/skills/tutti-architecture-review/references/tutti-layering.md",
    ".codex/skills/tutti-architecture-review/scripts/build-review-scope.mjs",
    ".codex/skills/tutti-architecture-review/scripts/build-review-scope.test.mjs",
    ".codex/skills/tutti-architecture-review/scripts/plan-review.mjs",
    ".codex/skills/tutti-architecture-review/scripts/plan-review.test.mjs",
})


def _check_tutti_build_contract(entries: list[tuple[str, str, str]]):
    for mode, blob_hash, path in entries:
        if path.startswith("apps/desktop/build/") and path not in _BUILD_ALLOWED:
            raise ValueError(f"Disallowed tutti build artifact: {path}")


def _check_tutti_blob_contract(blobs: list[tuple[str, str, str, int, bytes]]):
    for mode, blob_hash, path, size, content in blobs:
        if path == _WALLPAPER_PATH:
            continue
        if size > _MAX_BLOB_SIZE:
            raise ValueError(f"File exceeds 5MB limit: {path} ({size} bytes)")


def _check_profile(
    profile_name: str,
    snapshot_sha: str,
    excluded_paths: list[str],
    blobs: list[tuple[str, str, str, int, bytes]],
):
    if profile_name == "tutti-77fe474f":
        expected_sha = "77fe474fc953dc31d44ea50d477fdcd7022244e4"
        if snapshot_sha != expected_sha:
            raise ValueError(f"Profile tutti-77fe474f requires snapshot SHA {expected_sha}, got {snapshot_sha}")

        # (b) excluded .codex paths must be exactly the known 11 paths
        codex_excluded = sorted(p for p in excluded_paths if ".codex" in p)
        if codex_excluded != sorted(_TUTTI_CODEX_PATHS):
            raise ValueError(
                f"Profile tutti-77fe474f excluded .codex paths do not match expected set"
            )

        # (c) all 3 required build artifacts must be present (no-extras check is in _check_tutti_build_contract)
        included_paths = {p for _, _, p, _, _ in blobs}
        for allowed in _BUILD_ALLOWED:
            if allowed not in included_paths:
                raise ValueError(f"Profile tutti-77fe474f missing required build artifact: {allowed}")

        # (d) wallpaper path must exist exactly once with exact blob and size
        wallpaper_matches = [(m, h, p, s, c) for m, h, p, s, c in blobs if p == _WALLPAPER_PATH]
        if len(wallpaper_matches) != 1:
            raise ValueError(
                f"Profile tutti-77fe474f requires exactly one wallpaper at {_WALLPAPER_PATH}, "
                f"found {len(wallpaper_matches)}"
            )
        _, blob_hash, _, size, _ = wallpaper_matches[0]
        if blob_hash != "ac4dfad033dfd09b195b63108032c6adc82fc727":
            raise ValueError(f"Profile tutti-77fe474f wallpaper hash mismatch: {blob_hash}")
        if size != 6761064:
            raise ValueError(f"Profile tutti-77fe474f wallpaper size mismatch: {size}")
    else:
        raise ValueError(f"Unknown profile: {profile_name}")


def _run_import(
    source_repo: str,
    upstream_base_sha: str,
    snapshot_sha: str,
    dest_prefix: str,
    source_url: str,
    profile: str | None = None,
):
    resolved_upstream = _resolve_sha(source_repo, upstream_base_sha)
    resolved_snapshot = _resolve_sha(source_repo, snapshot_sha)

    if not _is_ancestor(source_repo, resolved_upstream, resolved_snapshot):
        print(f"[FAIL] Upstream base {resolved_upstream} is not an ancestor of snapshot {resolved_snapshot}", file=sys.stderr)
        sys.exit(1)

    entries = _git_ls_tree(source_repo, resolved_snapshot)

    dest = Path(dest_prefix)
    if dest.exists():
        print(f"[FAIL] Destination already exists: {dest_prefix}", file=sys.stderr)
        sys.exit(1)

    has_required, missing = _has_required_root_files(entries)
    if not has_required:
        print(f"[FAIL] Missing required root files: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    _check_tutti_build_contract(entries)

    included: list[tuple[str, str, str, int]] = []
    excluded_paths: list[str] = []

    for mode, blob_hash, path in entries:
        if not _is_safe_path(path):
            print(f"[FAIL] Unsafe path rejected before publication: {path}", file=sys.stderr)
            sys.exit(1)
        if _is_path_excluded(path):
            excluded_paths.append(path)
            continue
        included.append((mode, blob_hash, path, 0))

    blobs = _batch_get_blobs(source_repo, [(m, h, p) for m, h, p, _ in included])
    _check_tutti_blob_contract(blobs)

    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=dest.parent))
    staging_resolved = staging.resolve()
    try:
        for mode, blob_hash, path, size, content in blobs:
            staging_path = staging / path
            try:
                resolved_target = staging_path.resolve()
            except (OSError, RuntimeError):
                print(f"[FAIL] Unresolvable path: {path}", file=sys.stderr)
                shutil.rmtree(staging, ignore_errors=True)
                sys.exit(1)
            if not str(resolved_target).startswith(str(staging_resolved)):
                print(f"[FAIL] Path escapes staging: {path}", file=sys.stderr)
                shutil.rmtree(staging, ignore_errors=True)
                sys.exit(1)
            _write_file_safely(staging_path, content, mode)

        patch_manifest_entries = []
        if profile == "tutti-77fe474f":
            found = False
            for mode, blob_hash, path, size, content in blobs:
                if path == _PATCH_SPEC["file_path"]:
                    patch_info = _apply_text_patch(
                        staging_dir=staging,
                        blob_hash=blob_hash,
                        file_path=path,
                        expected_blob_hash=_PATCH_SPEC["expected_blob_hash"],
                        original_text=_PATCH_SPEC["original_text"],
                        replacement_text=_PATCH_SPEC["replacement_text"],
                    )
                    patch_manifest_entries.append(patch_info)
                    found = True
                    break
            if not found:
                print(f"[FAIL] Profile tutti-77fe474f requires {_PATCH_SPEC['file_path']} for patching, but it was not found in the snapshot", file=sys.stderr)
                shutil.rmtree(staging, ignore_errors=True)
                sys.exit(1)

        private_findings = _scan_private_markers(staging)
        if private_findings:
            for f in private_findings:
                print(f"[FAIL] Private marker detected: {f}", file=sys.stderr)
            shutil.rmtree(staging, ignore_errors=True)
            sys.exit(1)

        manifest_content = "\n".join([
            "# IMPORT_MANIFEST.md",
            "",
            f"- **Source URL**: {source_url}",
            f"- **Upstream Base SHA**: {resolved_upstream}",
            f"- **Snapshot SHA**: {resolved_snapshot}",
            f"- **File Count**: {len(blobs)}",
            f"- **Total Blob Bytes**: {sum(s for _, _, _, s, _ in blobs)}",
            f"- **Excluded Paths**: {len(excluded_paths)}",
            "",
            "## Exclusion List",
        ])
        for ex in sorted(excluded_paths):
            manifest_content += f"\n- `{ex}`"
        manifest_content += "\n\n## Included Files\n"
        for mode, blob_hash, path, _, _ in sorted(blobs, key=lambda x: x[2]):
            manifest_content += f"- `{mode} {blob_hash} {path}`\n"
        manifest_content += "\n"

        if patch_manifest_entries:
            manifest_content += "## Applied Source Patches\n\n"
            for pe in patch_manifest_entries:
                manifest_content += f"- **File**: `{pe['file']}`\n"
                manifest_content += f"- **Original Git Blob**: `{pe['original_git_blob']}`\n"
                manifest_content += f"- **Original Text (JSON-escaped)**: `{json.dumps(pe['original_text'])}`\n"
                manifest_content += f"- **Replacement Text (JSON-escaped)**: `{json.dumps(pe['replacement_text'])}`\n"
                manifest_content += f"- **Patched File SHA-256**: `{pe['patched_file_sha256']}`\n"
            manifest_content += "\n"

        manifest_path = staging / "IMPORT_MANIFEST.md"
        manifest_path.write_text(manifest_content, encoding="utf-8")

        if profile:
            _check_profile(profile, resolved_snapshot, excluded_paths, blobs)

        staging.rename(dest)

    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    print(f"[OK] Imported {len(blobs)} files ({sum(s for _,_,_,s,_ in blobs)} bytes) to {dest_prefix}")
    print(f"[OK] Excluded {len(excluded_paths)} paths")
    print(f"[OK] Manifest written to {dest / 'IMPORT_MANIFEST.md'}")


def main():
    parser = argparse.ArgumentParser(
        description="Import a Tutti snapshot from a source Git repository"
    )
    parser.add_argument("--source-repo", required=True, help="Path to source Git repository")
    parser.add_argument("--upstream-base-sha", required=True, help="Upstream base commit SHA")
    parser.add_argument("--snapshot-sha", required=True, help="Snapshot tree-ish to export")
    parser.add_argument("--dest-prefix", required=True, help="Destination directory prefix")
    parser.add_argument("--source-url", required=True, help="Source repository URL for manifest")
    parser.add_argument("--profile", default=None, help="Optional profile contract to validate against (e.g. tutti-77fe474f)")

    args = parser.parse_args()

    if not args.source_url.strip():
        print("[FAIL] --source-url must be a nonblank value", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(args.source_repo):
        print(f"[FAIL] Source repo not found: {args.source_repo}", file=sys.stderr)
        sys.exit(1)

    try:
        _run_import(
            source_repo=args.source_repo,
            upstream_base_sha=args.upstream_base_sha,
            snapshot_sha=args.snapshot_sha,
            dest_prefix=args.dest_prefix,
            source_url=args.source_url,
            profile=args.profile,
        )
    except subprocess.CalledProcessError as e:
        print(f"[FAIL] Git command failed: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
