"""Maestro Android wrapper — Run YAML flow on device"""

import subprocess, os, json, glob
from pathlib import Path


def run(project_config: dict) -> dict:
    """Execute Maestro flows on Android device/emulator"""
    flow_dir = project_config.get("maestro", {}).get("flow_dir", "tests/android/maestro/")
    device = project_config.get("maestro", {}).get("device", "")
    results = {"passed": True, "tool": "maestro", "results": [], "failed": [], "flows": 0}

    if not os.path.isdir(flow_dir):
        return {**results, "skipped": True}

    flows = sorted(Path(flow_dir).glob("*.yaml"))
    if not flows:
        return {**results, "skipped": True}

    for flow in flows:
        results["flows"] += 1
        name = flow.stem
        cmd = ["maestro", "test", str(flow)]
        if device:
            cmd.extend(["--device", device])
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env={**os.environ, "PATH": os.environ.get("PATH", "")})
            if r.returncode == 0:
                results["results"].append({"name": name, "status": "passed"})
            else:
                results["passed"] = False
                results["failed"].append(name)
                results["results"].append({"name": name, "status": "failed", "error": r.stderr[:300] if r.stderr else "Maestro assertion failed"})
        except FileNotFoundError:
            return {**results, "skipped": True, "note": "Maestro CLI not in PATH"}
        except subprocess.TimeoutExpired:
            results["passed"] = False
            results["failed"].append(name)

    # Collect screenshots from Maestro debug dir
    maestro_dir = os.path.expanduser("~/.maestro/tests")
    if os.path.isdir(maestro_dir):
        latest = sorted(Path(maestro_dir).iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        if latest:
            for png in latest[0].glob("*.png"):
                dest = os.path.join("reports", "maestro", png.name)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                import shutil
                shutil.copy(png, dest)

    return results
