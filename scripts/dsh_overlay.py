#!/usr/bin/env python3
"""Export a reviewed DSH candidate as a source-only overlay patch.

The exporter is deliberately read-only with respect to the DSH checkout. It
uses a clean candidate's diff against the pinned upstream commit and adds
source/test files that are still untracked. Generated output, dependencies,
status documents, and README copies are excluded because they are rebuilt or
owned by the source repository rather than being an overlay contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


GENERATED_PARTS = {"lib", "dist", "build", "coverage", "node_modules", "vendor"}
EXCLUDED_PREFIXES = (".agents/", "docs/", "scripts/")
EXCLUDED_SUFFIXES = (".d.ts", ".d.ts.map", ".js", ".js.map", ".tsbuildinfo")
TRACKED_EXCLUDES = (
    ":(exclude)pnpm-lock.yaml",
    ":(exclude)**/README*",
    ":(exclude)**/lib/**",
    ":(exclude)**/dist/**",
    ":(exclude)**/build/**",
    ":(exclude)**/coverage/**",
    ":(exclude)**/*.d.ts",
    ":(exclude)**/*.d.ts.map",
    ":(exclude)**/*.js",
    ":(exclude)**/*.js.map",
    ":(exclude)**/*.tsbuildinfo",
    ":(exclude)scripts/**",
    ":(exclude)**/node_modules/**",
)


class OverlayError(Exception):
    """A safe, actionable overlay-export error."""


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        raise OverlayError(f"git is unavailable: {exc}") from exc


def _git_root(root: Path) -> Path:
    result = _run(root, "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip() or "not a git worktree"
        raise OverlayError(f"invalid candidate checkout: {detail}")
    return Path(result.stdout.decode("utf-8").strip()).resolve()


def _relative(root: Path, path: Path) -> str:
    try:
        relative = path.resolve().relative_to(root)
    except ValueError as exc:
        raise OverlayError(f"path escapes candidate root: {path}") from exc
    return relative.as_posix()


def _is_overlay_source(relative: str) -> bool:
    if relative in {"", "."} or relative.startswith(EXCLUDED_PREFIXES):
        return False
    if Path(relative).name.startswith("README"):
        return False
    parts = set(relative.split("/"))
    if parts & GENERATED_PARTS:
        return False
    # Ambient declarations that live beside source files are part of the
    # source contract (for example, CSS-module declarations in a new package),
    # while emitted declarations remain generated output and stay excluded.
    source_declaration = relative == "src/css-modules.d.ts" or relative.endswith("/src/css-modules.d.ts")
    return source_declaration or not relative.endswith(EXCLUDED_SUFFIXES)


def _untracked_files(root: Path) -> list[str]:
    result = _run(root, "status", "--porcelain=v1", "--untracked-files=all", "-z")
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip() or "git status failed"
        raise OverlayError(f"cannot inspect candidate: {detail}")
    files: list[str] = []
    for record in result.stdout.split(b"\0"):
        if not record or not record.startswith(b"?? "):
            continue
        relative = record[3:].decode("utf-8", "surrogateescape").replace("\\", "/")
        if _is_overlay_source(relative):
            files.append(relative)
    return sorted(files)


def _tracked_patch(root: Path, base_ref: str) -> bytes:
    result = _run(root, "diff", "--binary", base_ref, "--", ".", *TRACKED_EXCLUDES)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip() or "git diff failed"
        raise OverlayError(f"cannot export tracked overlay: {detail}")
    # Keep source-owned CSS-module declarations even though emitted
    # declarations are excluded above. These files sit beside source and are
    # required by TypeScript consumers of packages with CSS modules.
    declarations = _run(root, "diff", "--binary", base_ref, "--", "**/src/css-modules.d.ts")
    if declarations.returncode != 0:
        detail = declarations.stderr.decode("utf-8", "replace").strip() or "git diff failed"
        raise OverlayError(f"cannot export tracked source declarations: {detail}")
    chunks = [result.stdout.rstrip(b"\n"), declarations.stdout.rstrip(b"\n")]
    return b"\n".join(chunk for chunk in chunks if chunk) + (b"\n" if any(chunks) else b"")


def _untracked_patch(root: Path, relative: str) -> bytes:
    result = _run(root, "diff", "--no-index", "--binary", "--", "/dev/null", relative)
    # git diff --no-index returns 1 when the files differ, which is the
    # expected result for every newly discovered overlay file.
    if result.returncode not in {0, 1}:
        detail = result.stderr.decode("utf-8", "replace").strip() or "git no-index diff failed"
        raise OverlayError(f"cannot export added overlay {relative}: {detail}")
    return result.stdout


def export_overlay(candidate_root: Path, base_ref: str, output: Path) -> dict[str, object]:
    root = _git_root(candidate_root.resolve())
    tracked = _tracked_patch(root, base_ref)
    added = _untracked_files(root)
    chunks = [tracked.rstrip(b"\n")]
    for relative in added:
        patch = _untracked_patch(root, relative).rstrip(b"\n")
        if patch:
            chunks.append(patch)
    payload = b"\n".join(chunk for chunk in chunks if chunk) + b"\n"
    output = output.resolve()
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
    except OSError as exc:
        raise OverlayError(f"cannot write overlay patch {output}: {exc}") from exc
    return {
        "candidateRoot": str(root),
        "baseRef": base_ref,
        "trackedPatchBytes": len(tracked),
        "addedFiles": added,
        "patchBytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "output": str(output),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("export",))
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = export_overlay(args.candidate_root, args.base_ref, args.output)
    except OverlayError as exc:
        if args.json:
            print(json.dumps({"valid": False, "error": str(exc)}))
        else:
            print(f"[DSH-OVERLAY-BLOCKED] {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[DSH-OVERLAY-PASS] {result['output']} ({result['sha256']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
