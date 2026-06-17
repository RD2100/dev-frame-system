"""M3: decision file helpers — shared by nodes and graph routing.

Placed in a separate module to avoid circular imports between
nodes/*.py and workflows/coding_graph.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

VALID_DECISION_STATUSES = {"pending", "approved", "rejected", "continue", "abort", "skip"}
SIDE_EFFECT_NODES = {"execute_node", "fix_node"}
TERMINAL_STATUSES = {"passed", "failed", "blocked", "rejected"}


# ---------------------------------------------------------------------------
# Decision — for human-gate.json / fix-before-round-N.json
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    """Structured result of reading a decision file."""
    status: str | None   # one of VALID_DECISION_STATUSES, or None if missing
    exists: bool         # True if the file exists on disk
    valid: bool          # False when JSON is corrupt or status is invalid
    error: str | None = None


def read_decision(run_dir: str, name: str) -> Decision:
    """Read decisions/{name}.json and return a structured Decision.

    File missing   -> Decision(status=None, exists=False, valid=True)
    JSON corrupt   -> Decision(status=None, exists=True,  valid=False, error=...)
    Invalid status -> Decision(status=...,  exists=True,  valid=False, error=...)
    Valid          -> Decision(status=...,  exists=True,  valid=True)
    """
    if not run_dir:
        return Decision(status=None, exists=False, valid=True)
    path = Path(run_dir) / "decisions" / f"{name}.json"
    if not path.exists():
        return Decision(status=None, exists=False, valid=True)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        status = data.get("status")
        if status is None:
            return Decision(status=None, exists=True, valid=False,
                          error="missing 'status' field")
        if status not in VALID_DECISION_STATUSES:
            return Decision(status=status, exists=True, valid=False,
                          error=f"invalid status: '{status}'")
        return Decision(status=status, exists=True, valid=True)
    except json.JSONDecodeError as e:
        return Decision(status=None, exists=True, valid=False,
                      error=f"JSON parse error: {e}")
    except OSError as e:
        return Decision(status=None, exists=True, valid=False,
                      error=f"read error: {e}")


# ---------------------------------------------------------------------------
# FixControl — for decisions/fix-control.json
# ---------------------------------------------------------------------------

@dataclass
class FixControl:
    """Structured result of reading decisions/fix-control.json."""
    mode: str                    # "auto" or "supervised"
    pause_before_next_fix: bool
    exists: bool
    valid: bool
    error: str | None = None


def read_fix_control(run_dir: str) -> FixControl:
    """Read decisions/fix-control.json.

    File missing -> defaults (mode="auto", pause=False, valid=True).
    """
    if not run_dir:
        return FixControl(mode="auto", pause_before_next_fix=False,
                         exists=False, valid=True)
    path = Path(run_dir) / "decisions" / "fix-control.json"
    if not path.exists():
        return FixControl(mode="auto", pause_before_next_fix=False,
                         exists=False, valid=True)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        mode = data.get("mode", "auto")
        pause = data.get("pause_before_next_fix", False)
        if mode not in ("auto", "supervised"):
            return FixControl(mode=mode, pause_before_next_fix=pause,
                            exists=True, valid=False,
                            error=f"invalid mode: '{mode}'")
        if not isinstance(pause, bool):
            return FixControl(mode=mode, pause_before_next_fix=bool(pause),
                            exists=True, valid=False,
                            error=f"pause_before_next_fix not bool: {pause}")
        return FixControl(mode=mode, pause_before_next_fix=pause,
                         exists=True, valid=True)
    except (json.JSONDecodeError, OSError) as e:
        return FixControl(mode="auto", pause_before_next_fix=False,
                         exists=True, valid=False, error=str(e))


# backward-compat alias (used by _human_gate_route and _test_route)
_read_decision = read_decision
_read_fix_control = read_fix_control
