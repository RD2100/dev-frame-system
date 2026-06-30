"""CLI entry: devframe init, doctor, run, code, go, handoff, pack, dashboard, and rdgoal.

The command implementations live in per-domain submodules of this package
(`_core`, `_coding`, `_webai`, `_client`, `_visual`) and the router lives in
`app`. `shutil` is imported here so the test monkeypatch target
`control_plane.cli.shutil` keeps resolving to the shared `shutil` module.
"""
from __future__ import annotations

import shutil  # noqa: F401 - preserves the control_plane.cli.shutil monkeypatch path

from .app import main

__all__ = ["main"]
