"""Local dry-run worker for rdgoal dispatch packets.

This worker proves the packet -> ExecutionReport -> ingest loop without
modifying the target project. Real workers can later replace this adapter.
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .dispatch_packet import DispatchPacket, DispatchPacketStore, ExecutionReportSummary


@dataclass
class WorkerResult:
    packet: DispatchPacket
    report_path: str
    summary: ExecutionReportSummary


class LocalDryRunWorker:
    def __init__(self, runtime_dir: str | Path | None = None,
                 repo_root: str | Path | None = None) -> None:
        self.store = DispatchPacketStore(runtime_dir=runtime_dir, repo_root=repo_root)

    def run_packet(self, packet_dir: str | Path) -> WorkerResult:
        packet = self.store.load_packet(packet_dir)
        report_path = Path(packet.packet_dir) / "ExecutionReport.md"
        report_path.write_text(self._render_report(packet), encoding="utf-8")
        summary = self.store.ingest_report(packet.packet_dir, report_path)
        return WorkerResult(packet=packet, report_path=str(report_path), summary=summary)

    def _render_report(self, packet: DispatchPacket) -> str:
        status = "pass" if packet.dispatch_ready else "blocked"
        changed_files = "\n".join(f"- `{target}`" for target in packet.targets) or "- (none)"
        blocked_reason = (
            ""
            if packet.dispatch_ready
            else "\n- **Blocked Reason**: Packet is not dispatch-ready; worker performed no project changes."
        )
        return (
            f"## ExecutionReport: {packet.packet_id}\n\n"
            f"- **Status**: {status}{blocked_reason}\n"
            "- **Review Status**: draft\n"
            "- **Summary**: Local dry-run worker consumed the rdgoal dispatch packet. "
            "No target project files were modified.\n"
            "- **Changed Files**:\n"
            f"{changed_files}\n"
            "- **Evidence**: dry-run worker loaded packet.json and wrote this ExecutionReport.\n"
            "- **Risks**: Real implementation still requires a live project-local worker.\n"
            "- **Reviewer Index**:\n"
            f"- `{packet.packet_dir}` -> verify packet.json and TASKSPEC.md before live dispatch.\n"
        )


class CommandWorker:
    """Run an explicit worker command against a dispatch packet."""

    def __init__(self, runtime_dir: str | Path | None = None,
                 repo_root: str | Path | None = None,
                 timeout_seconds: int = 900) -> None:
        self.store = DispatchPacketStore(runtime_dir=runtime_dir, repo_root=repo_root)
        self.timeout_seconds = timeout_seconds

    def run_packet(self, packet_dir: str | Path, command: list[str]) -> WorkerResult:
        if not command:
            raise ValueError("CommandWorker requires a non-empty command list.")

        packet = self.store.load_packet(packet_dir)
        report_path = Path(packet.packet_dir) / "ExecutionReport.md"
        if not packet.dispatch_ready:
            report_path.write_text(self._blocked_report(packet), encoding="utf-8")
            summary = self.store.ingest_report(packet.packet_dir, report_path)
            return WorkerResult(packet=packet, report_path=str(report_path), summary=summary)

        output_path = Path(packet.packet_dir) / "worker-output.txt"
        env = os.environ.copy()
        env.update({
            "RDGOAL_PACKET_DIR": packet.packet_dir,
            "RDGOAL_PACKET_JSON": str(Path(packet.packet_dir) / "packet.json"),
            "RDGOAL_TASKSPEC_JSON": str(Path(packet.packet_dir) / "TASKSPEC.json"),
            "RDGOAL_TASKSPEC_MD": str(Path(packet.packet_dir) / "TASKSPEC.md"),
            "RDGOAL_REPORT_PATH": str(report_path),
        })
        try:
            completed = subprocess.run(
                command,
                cwd=packet.project_root,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            output_path.write_text(
                "STDOUT\n"
                f"{completed.stdout}\n\n"
                "STDERR\n"
                f"{completed.stderr}\n",
                encoding="utf-8",
            )
        except subprocess.TimeoutExpired as exc:
            output_path.write_text(
                "STDOUT\n"
                f"{exc.stdout or ''}\n\n"
                "STDERR\n"
                f"{exc.stderr or ''}\n\n"
                f"TIMEOUT after {self.timeout_seconds} seconds\n",
                encoding="utf-8",
            )
            report_path.write_text(self._failed_report(packet, "worker command timed out"), encoding="utf-8")
            summary = self.store.ingest_report(packet.packet_dir, report_path)
            return WorkerResult(packet=packet, report_path=str(report_path), summary=summary)

        if completed.returncode != 0:
            report_path.write_text(
                self._failed_report(packet, f"worker command exited {completed.returncode}"),
                encoding="utf-8",
            )
        elif not report_path.exists():
            report_path.write_text(
                self._failed_report(packet, "worker command did not produce ExecutionReport.md"),
                encoding="utf-8",
            )

        summary = self.store.ingest_report(packet.packet_dir, report_path)
        return WorkerResult(packet=packet, report_path=str(report_path), summary=summary)

    def _blocked_report(self, packet: DispatchPacket) -> str:
        return (
            f"## ExecutionReport: {packet.packet_id}\n\n"
            "- **Status**: blocked\n"
            "- **Review Status**: draft\n"
            "- **Summary**: Command worker did not run because the packet is not dispatch-ready.\n"
            "- **Changed Files**:\n"
            "- (none)\n"
            "- **Evidence**: packet dispatch_ready was false.\n"
            "- **Risks**: Live worker command was intentionally skipped.\n"
        )

    def _failed_report(self, packet: DispatchPacket, reason: str) -> str:
        return (
            f"## ExecutionReport: {packet.packet_id}\n\n"
            "- **Status**: failed\n"
            "- **Review Status**: draft\n"
            f"- **Summary**: Command worker failed: {reason}.\n"
            "- **Changed Files**:\n"
            "- (unknown)\n"
            "- **Evidence**: see worker-output.txt in the packet directory.\n"
            "- **Risks**: Runner failure must not be reported as pass.\n"
        )


class AihubGoWorker(CommandWorker):
    """Adapter for ai_workflow_hub's `go` TaskSpec entry point."""

    def run_packet(self, packet_dir: str | Path, *, apply_changes: bool = False,
                   python_executable: str | None = None,
                   module_name: str = "ai_workflow_hub.cli") -> WorkerResult:
        packet = self.store.load_packet(packet_dir)
        command = [
            python_executable or sys.executable,
            "-m",
            module_name,
            "go",
            str(Path(packet.packet_dir) / "TASKSPEC.json"),
            "--project",
            packet.project_id,
        ]
        command.append("--apply" if apply_changes else "--dry-run")
        return super().run_packet(packet_dir, command)
