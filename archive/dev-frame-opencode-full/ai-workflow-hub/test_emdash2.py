# -*- coding: utf-8 -*-
"""Test file."""
from pathlib import Path
from typing import Optional, Union

def _discover_ledger_path(task_id: str, explicit_dir: str = "",
                          run_id: str = "") -> Union[Path, None]:
    """Find ledger JSON for a task, with fallback discovery (A26->A27).

    A27: run_id-aware — prefers <task_id>_<run_id>.json if it exists,
    then falls back to <task_id>.json.
    """
    pass

print("OK")
