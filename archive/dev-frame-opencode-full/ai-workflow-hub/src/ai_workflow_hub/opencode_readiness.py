"""OpenCode readiness probe — verifies OpenCode is available and responsive."""

from __future__ import annotations
import subprocess
import shutil


def opencode_is_installed() -> bool:
    """Check if the opencode binary is on PATH."""
    return shutil.which("opencode") is not None


def opencode_probe(model: str = "deepseek/deepseek-v4-pro",
                   timeout: int = 30) -> tuple[bool, str]:
    """Quick probe: run a minimal OpenCode task to verify it responds.

    Returns (success, error_message).
    """
    if not opencode_is_installed():
        return False, "opencode binary not found on PATH"

    try:
        result = subprocess.run(
            ["opencode", "run", "-m", model, "-p", "echo hello"],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0:
            return True, ""
        return False, f"opencode exited with code {result.returncode}: {result.stderr[:500]}"
    except subprocess.TimeoutExpired:
        return False, f"opencode probe timed out after {timeout}s"
    except FileNotFoundError:
        return False, "opencode binary not found"
    except Exception as e:
        return False, str(e)


def readiness_check(model: str = "deepseek/deepseek-v4-pro",
                    required_passes: int = 2) -> tuple[bool, str]:
    """Run multiple probes. Returns True only if required_passes succeed.

    Use as a pre-apply gate: don't allow code changes if OpenCode is not
    responding reliably.
    """
    passes = 0
    errors = []
    for i in range(max(required_passes, 3)):
        ok, err = opencode_probe(model=model)
        if ok:
            passes += 1
        else:
            errors.append(f"probe {i+1}: {err}")

    if passes >= required_passes:
        return True, f"{passes}/{required_passes} probes passed"
    return False, "; ".join(errors) if errors else "insufficient passes"
