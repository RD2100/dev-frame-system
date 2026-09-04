import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dsh_overlay.py"


def run_git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_export_includes_source_but_excludes_generated_and_private_files(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    run_git(candidate, "init", "--initial-branch", "master")
    run_git(candidate, "config", "user.email", "dsh-overlay-test@example.invalid")
    run_git(candidate, "config", "user.name", "DSH overlay test")
    (candidate / "packages" / "demo").mkdir(parents=True)
    (candidate / "packages" / "demo" / "source.ts").write_text("before\n", encoding="utf-8")
    (candidate / "scripts").mkdir()
    (candidate / "scripts" / "tracked.ts").write_text("before\n", encoding="utf-8")
    run_git(candidate, "add", ".")
    run_git(candidate, "commit", "-m", "baseline")
    base = run_git(candidate, "rev-parse", "HEAD")

    (candidate / "packages" / "demo" / "source.ts").write_text("after\n", encoding="utf-8")
    (candidate / "packages" / "demo" / "new.ts").write_text("new\n", encoding="utf-8")
    (candidate / "packages" / "demo" / "src").mkdir()
    (candidate / "packages" / "demo" / "src" / "css-modules.d.ts").write_text(
        "declare module '*.module.css'\n", encoding="utf-8",
    )
    (candidate / "packages" / "demo" / "generated.js").write_text("generated\n", encoding="utf-8")
    (candidate / "packages" / "demo" / "README.md").write_text("private\n", encoding="utf-8")
    (candidate / "scripts" / "tracked.ts").write_text("private\n", encoding="utf-8")
    (candidate / "scripts" / "private.mjs").write_text("private\n", encoding="utf-8")
    (candidate / "lib").mkdir()
    (candidate / "lib" / "built.js").write_text("built\n", encoding="utf-8")

    output = tmp_path / "overlay.patch"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "export",
            "--candidate-root",
            str(candidate),
            "--base-ref",
            base,
            "--output",
            str(output),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["addedFiles"] == [
        "packages/demo/new.ts",
        "packages/demo/src/css-modules.d.ts",
    ]
    patch = output.read_text(encoding="utf-8")
    assert "packages/demo/source.ts" in patch
    assert "packages/demo/new.ts" in patch
    assert "generated.js" not in patch
    assert "README.md" not in patch
    assert "scripts/" not in patch
    assert "lib/" not in patch


def test_export_keeps_tracked_css_module_declaration(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    run_git(candidate, "init", "--initial-branch", "master")
    run_git(candidate, "config", "user.email", "dsh-overlay-test@example.invalid")
    run_git(candidate, "config", "user.name", "DSH overlay test")
    declaration = candidate / "packages" / "demo" / "src" / "css-modules.d.ts"
    declaration.parent.mkdir(parents=True)
    declaration.write_text("declare module '*.module.css'\n", encoding="utf-8")
    run_git(candidate, "add", ".")
    run_git(candidate, "commit", "-m", "baseline")
    base = run_git(candidate, "rev-parse", "HEAD")

    declaration.write_text("declare module '*.module.css' { const classes: Record<string, string> }\n", encoding="utf-8")
    output = tmp_path / "overlay.patch"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "export",
            "--candidate-root",
            str(candidate),
            "--base-ref",
            base,
            "--output",
            str(output),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "packages/demo/src/css-modules.d.ts" in output.read_text(encoding="utf-8")
