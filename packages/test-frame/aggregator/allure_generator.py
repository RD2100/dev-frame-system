"""Allure HTML generation with explicit PASS/BLOCKED/FAILED semantics."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Callable, Literal

from capability.providers.common import resolve_executable
from capability.schema import redact_value, summarize


AllureStatus = Literal["PASS", "BLOCKED", "FAILED"]


@dataclass(frozen=True)
class AllureGenerationResult:
    status: AllureStatus
    results_dir: str
    report_dir: str
    manifest_path: str
    command: list[str]
    exit_code: int | None
    reason: str
    stdout: str = ""
    stderr: str = ""
    html_path: str = ""
    summary_path: str = ""

    def __fspath__(self) -> str:
        return self.report_dir

    def __str__(self) -> str:
        return self.report_dir

    def to_dict(self) -> dict:
        return redact_value({
            "status": self.status,
            "results_dir": self.results_dir,
            "report_dir": self.report_dir,
            "manifest_path": self.manifest_path,
            "command": self.command,
            "exit_code": self.exit_code,
            "reason": self.reason,
            "stdout": summarize(self.stdout),
            "stderr": summarize(self.stderr),
            "html_path": self.html_path,
            "summary_path": self.summary_path,
        })


Runner = Callable[..., subprocess.CompletedProcess]
PathResolver = Callable[[str], str | None]


def _repo_local_allure(project_root: Path) -> str | None:
    candidates = [
        project_root / "node_modules" / ".bin" / "allure.cmd",
        project_root / "node_modules" / ".bin" / "allure",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _resolve_allure(project_root: Path, path_resolver: PathResolver | None = None) -> str | None:
    resolver = path_resolver or resolve_executable
    return resolver("allure") or _repo_local_allure(project_root)


def _write_manifest(result: AllureGenerationResult) -> AllureGenerationResult:
    path = Path(result.manifest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def generate_allure_report(
    results_dir: str | Path,
    report_dir: str | Path,
    summary_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
    project_root: str | Path | None = None,
    path_resolver: PathResolver | None = None,
    runner: Runner = subprocess.run,
) -> AllureGenerationResult:
    results_path = Path(results_dir)
    report_path = Path(report_dir)
    manifest = Path(manifest_path) if manifest_path else report_path.parent / "allure-generation.json"
    summary = str(summary_path) if summary_path else ""
    root = Path(project_root) if project_root else Path.cwd()

    display_command = [
        "allure",
        "generate",
        str(results_path),
        "-o",
        str(report_path),
        "--clean",
    ]
    executable = _resolve_allure(root, path_resolver)
    if not executable:
        return _write_manifest(AllureGenerationResult(
            status="BLOCKED",
            results_dir=str(results_path),
            report_dir=str(report_path),
            manifest_path=str(manifest),
            command=display_command,
            exit_code=None,
            reason="allure CLI not found in PATH or node_modules/.bin",
            summary_path=summary,
        ))

    command = [executable, *display_command[1:]]
    try:
        completed = runner(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except FileNotFoundError:
        return _write_manifest(AllureGenerationResult(
            status="BLOCKED",
            results_dir=str(results_path),
            report_dir=str(report_path),
            manifest_path=str(manifest),
            command=display_command,
            exit_code=None,
            reason="allure CLI could not be executed",
            stderr="executable not found",
            summary_path=summary,
        ))
    except subprocess.TimeoutExpired as exc:
        return _write_manifest(AllureGenerationResult(
            status="FAILED",
            results_dir=str(results_path),
            report_dir=str(report_path),
            manifest_path=str(manifest),
            command=display_command,
            exit_code=None,
            reason="allure generate timed out",
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            summary_path=summary,
        ))

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if completed.returncode != 0:
        return _write_manifest(AllureGenerationResult(
            status="FAILED",
            results_dir=str(results_path),
            report_dir=str(report_path),
            manifest_path=str(manifest),
            command=display_command,
            exit_code=completed.returncode,
            reason="allure generate returned a non-zero exit code",
            stdout=stdout,
            stderr=stderr,
            summary_path=summary,
        ))

    html_path = report_path / "index.html"
    if not html_path.exists():
        return _write_manifest(AllureGenerationResult(
            status="FAILED",
            results_dir=str(results_path),
            report_dir=str(report_path),
            manifest_path=str(manifest),
            command=display_command,
            exit_code=completed.returncode,
            reason="allure generate exited 0 but index.html was not created",
            stdout=stdout,
            stderr=stderr,
            summary_path=summary,
        ))

    return _write_manifest(AllureGenerationResult(
        status="PASS",
        results_dir=str(results_path),
        report_dir=str(report_path),
        manifest_path=str(manifest),
        command=display_command,
        exit_code=completed.returncode,
        reason="Allure HTML report generated",
        stdout=stdout,
        stderr=stderr,
        html_path=str(html_path),
        summary_path=summary,
    ))
