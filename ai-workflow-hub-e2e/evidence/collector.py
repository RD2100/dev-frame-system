"""证据收集器 — 统一收集各工具的日志、截图、视频、堆栈"""

import os
import time
import json
import hashlib
from datetime import datetime
from pathlib import Path

from evidence.signing import sign_evidence


def _compute_sha256(filepath: str) -> str | None:
    """Compute SHA256 hex digest of a file's content.

    Returns the lowercase hex digest string, or None if the file does not
    exist or cannot be read.  This is an integrity checksum, NOT a
    cryptographic signature.
    """
    try:
        with open(filepath, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except (OSError, IOError):
        return None


class EvidenceCollector:
    def __init__(self, project_name: str):
        self.project_name = project_name
        self.timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.base_dir = os.path.join("reports", project_name, datetime.now().strftime("%Y-%m-%d"))

    def collect(self, build_id: str = None) -> "EvidenceIndex":
        """收集所有证据"""
        os.makedirs(self.base_dir, exist_ok=True)

        index = EvidenceIndex(self.project_name, self.timestamp, build_id)

        # 收集各工具证据
        self._collect_screenshots(index)
        self._collect_videos(index)
        self._collect_logcat(index)
        self._collect_crash_info(index)

        # 写入索引
        index_path = os.path.join(self.base_dir, "evidence.json")
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index.to_dict(), f, ensure_ascii=False, indent=2)

        print(f"  [FILE] Evidence collected: {self.base_dir}")
        return index

    def _collect_screenshots(self, index):
        """收集各工具截图"""
        tool_dirs = {
            "maestro": "reports/maestro/",
            "airtest": "reports/airtest_log/",
            "playwright": "test-results/",
        }
        for tool, dir_path in tool_dirs.items():
            if os.path.isdir(dir_path):
                for f in Path(dir_path).rglob("*.png"):
                    index.add_evidence(
                        type="screenshot",
                        tool=tool,
                        path=str(f),
                    )

    def _collect_videos(self, index):
        """收集各工具录屏"""
        tool_dirs = {
            "maestro": "reports/maestro/",
            "playwright": "test-results/",
        }
        for tool, dir_path in tool_dirs.items():
            if os.path.isdir(dir_path):
                for f in Path(dir_path).rglob("*.mp4"):
                    index.add_evidence(
                        type="video",
                        tool=tool,
                        path=str(f),
                    )

    def _collect_logcat(self, index):
        """收集Android logcat"""
        import subprocess
        try:
            log_path = os.path.join(self.base_dir, "logcat", "device.log")
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            r = subprocess.run(
                ["adb", "logcat", "-d"],
                capture_output=True, text=True, timeout=10
            )
            if r.returncode == 0:
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(r.stdout)
                index.add_evidence(
                    type="logcat",
                    tool="adb",
                    path=log_path,
                )
                print("  [LOG] logcat saved")
        except Exception as e:
            print(f"  [WARN] logcat failed: {e}")

    def _collect_crash_info(self, index):
        """从logcat和工具输出中提取崩溃信息"""
        logcat_path = os.path.join(self.base_dir, "logcat", "device.log")
        if os.path.exists(logcat_path):
            with open(logcat_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            # 简单匹配 FATAL EXCEPTION
            if "FATAL EXCEPTION" in content:
                index.add_evidence(
                    type="crash",
                    tool="adb",
                    path=logcat_path,
                    metadata={"crash_type": "fatal_exception"}
                )
                print("  [CRASH] Crash detected! (FATAL EXCEPTION)")


class EvidenceIndex:
    def __init__(self, project: str, timestamp: str, build_id: str = None):
        self.project = project
        self.timestamp = timestamp
        self.build_id = build_id or "unknown"
        self.evidences = []

    def add_evidence(self, type: str, tool: str, path: str, metadata: dict = None):
        metadata = dict(metadata or {})  # shallow copy to avoid mutating caller's dict

        # Integrity checksum — SHA256 of file content.
        # This is an integrity checksum, NOT a cryptographic signature.
        # It detects accidental corruption or naive tampering (e.g. replacing
        # a screenshot file), but does NOT provide non-repudiation.
        sha256 = _compute_sha256(path)
        metadata["sha256"] = sha256

        collected_at = datetime.now().isoformat()

        # HMAC-SHA256 signature for tamper detection.
        # Signing key is from env var EVIDENCE_SIGNING_KEY.
        # When key is absent, signature_status="unsigned" and signature=None.
        sig = sign_evidence(
            evidence_type=type,
            tool=tool,
            path=path,
            sha256=sha256,
            timestamp=collected_at,
            build_id=self.build_id,
        )

        self.evidences.append({
            "type": type,
            "tool": tool,
            "path": path,
            "metadata": metadata,
            "collected_at": collected_at,
            "signature": sig["signature"],
            "signature_status": sig["signature_status"],
        })

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "timestamp": self.timestamp,
            "build_id": self.build_id,
            "evidence_count": len(self.evidences),
            "evidences": self.evidences,
        }

    def summary(self) -> str:
        lines = [
            f"[FILE] Evidence Index: {self.project}",
            f"   时间: {self.timestamp}",
            f"   构建: {self.build_id}",
            f"   证据数: {len(self.evidences)}",
        ]
        type_counts = {}
        for e in self.evidences:
            t = e["type"]
            type_counts[t] = type_counts.get(t, 0) + 1
        for t, c in type_counts.items():
            lines.append(f"   - {t}: {c}件")
        return "\n".join(lines)
