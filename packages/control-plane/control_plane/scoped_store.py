"""Scope-aware, malformed-safe file storage for the customization layer.

Every customizable category (team, skills, rules, run defaults,
memory/preferences) stores its per-scope config the same way: a global file at
``<runtime>/<filename>`` and a project file at
``<runtime>/{project_id}/<filename>``. The built-in scope is *not* file-backed —
its records come from code constants or repo markdown, never a runtime file.

This module factors that shared path + read/write logic out of the individual
category modules so none of them re-implement it:

- :func:`scoped_path` maps ``(runtime_dir, filename, scope, project_id)`` to a
  concrete file path, rejecting any path that escapes the runtime root.
- :class:`ScopedStore` offers malformed-safe :meth:`~ScopedStore.load` and
  atomic ASCII :meth:`~ScopedStore.save`, mirroring the existing
  ``custom_skills`` / ``cluster_control`` atomic-write pattern exactly.

The store is category-agnostic. A category constructs one ``ScopedStore`` with
its ``runtime_dir`` + ``filename`` (and, for single-object categories such as
run defaults, an optional ``default_factory``) and reuses it for every scope.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from .backup_guard import default_runtime_dir, is_inside
from .scope_resolver import Scope


def _runtime_root(runtime_dir: str | Path | None) -> Path:
    """Resolve the runtime root, applying the shared default when unset."""
    return Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()


def scoped_path(
    runtime_dir: str | Path | None,
    filename: str,
    scope: Scope,
    project_id: str | None,
) -> Path:
    """Map a scope to the concrete file backing it, guarding the runtime root.

    The contract per scope:

    - ``BUILTIN`` is **not file-backed** — built-in records come from code
      constants or repo markdown, so there is no path to return. This raises
      :class:`ValueError`.
    - ``GLOBAL`` resolves to ``<runtime>/<filename>``.
    - ``PROJECT`` resolves to ``<runtime>/{project_id}/<filename>`` and requires
      a non-empty ``project_id``.

    Args:
        runtime_dir: The runtime root, or ``None`` to use
            :func:`backup_guard.default_runtime_dir`.
        filename: The leaf config filename (e.g. ``"skills.json"``).
        scope: The :class:`~control_plane.scope_resolver.Scope` to resolve.
        project_id: The project slug; required for ``PROJECT`` scope, ignored
            otherwise.

    Returns:
        The resolved, absolute path for the requested scope.

    Raises:
        ValueError: if ``scope`` is ``BUILTIN`` (not file-backed); if ``scope``
            is ``PROJECT`` without a ``project_id``; or if the resolved path
            escapes the runtime root (path-escape guard).
    """
    root = _runtime_root(runtime_dir)

    if scope == Scope.BUILTIN:
        raise ValueError(
            "BUILTIN scope is not file-backed; built-in records come from code "
            "or markdown, not a runtime file."
        )
    if scope == Scope.GLOBAL:
        candidate = root / filename
    elif scope == Scope.PROJECT:
        if not project_id:
            raise ValueError("PROJECT scope requires a non-empty project_id.")
        candidate = root / project_id / filename
    else:  # pragma: no cover - defensive; Scope is a closed enum.
        raise ValueError(f"Unsupported scope: {scope!r}")

    resolved = candidate.resolve()
    # Path-escape guard: a crafted filename/project_id (e.g. containing "..")
    # must never let a write land outside the runtime root.
    if not is_inside(resolved, root):
        raise ValueError(
            f"Resolved path {resolved} escapes the runtime root {root}."
        )
    return resolved


class ScopedStore:
    """Category-agnostic, malformed-safe, atomic scope-aware file store.

    Construct one per category with the ``runtime_dir`` and config ``filename``.
    List-backed categories (team, skills, rules) use the default empty-list
    fallback; single-object categories (run defaults) pass a ``default_factory``
    returning the default object so malformed/missing loads degrade to it.
    """

    def __init__(
        self,
        runtime_dir: str | Path | None,
        filename: str,
        default_factory: Callable[[], Any] | None = None,
    ) -> None:
        """Initialize the store.

        Args:
            runtime_dir: The runtime root, or ``None`` for the shared default.
            filename: The leaf config filename (e.g. ``"skills.json"``).
            default_factory: Optional zero-arg factory producing the fallback
                value for missing/unreadable/malformed files. Defaults to a
                fresh empty ``list`` (list-backed categories).
        """
        self.runtime_dir = runtime_dir
        self.filename = filename
        self._default_factory: Callable[[], Any] = default_factory or (lambda: [])

    def path(self, scope: Scope, project_id: str | None = None) -> Path:
        """Resolve the backing path for ``scope`` (see :func:`scoped_path`)."""
        return scoped_path(self.runtime_dir, self.filename, scope, project_id)

    def load(self, scope: Scope, project_id: str | None = None) -> Any:
        """Load the raw config for ``scope``, never raising on bad input.

        Returns the ``default_factory`` value when the file is missing,
        unreadable, not valid JSON, or has a root type that disagrees with the
        default (list vs object). This mirrors the existing category modules:
        a bad project edit silently degrades to the default, which lets
        resolution fall back to the next-less-specific scope.

        Args:
            scope: The scope to read. ``BUILTIN`` is not file-backed and yields
                the default.
            project_id: Required for ``PROJECT`` scope.

        Returns:
            The parsed JSON value (matching the default's root type) or the
            ``default_factory`` value on any failure.
        """
        default = self._default_factory()

        # BUILTIN is not file-backed, and a PROJECT load without a project id
        # has nothing to read; both degrade to the default without raising.
        if scope == Scope.BUILTIN:
            return default
        try:
            path = self.path(scope, project_id)
        except ValueError:
            return default

        if not path.is_file():
            return default
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # ValueError covers json.JSONDecodeError *and* UnicodeDecodeError
            # (invalid UTF-8 bytes), so malformed bytes never raise here.
            return default

        # Wrong-root-type guard: keep the loaded value only when its root type
        # matches the default's (list-backed vs object-backed category).
        if isinstance(default, list) and not isinstance(data, list):
            return default
        if isinstance(default, dict) and not isinstance(data, dict):
            return default
        return data

    def save(
        self,
        scope: Scope,
        items: Any,
        project_id: str | None = None,
    ) -> None:
        """Atomically write ``items`` as ASCII JSON to ``scope``'s file.

        Creates parent directories, writes to a sibling ``.tmp`` file, then
        :func:`os.replace` swaps it into place so a reader never observes a
        partially written file. Output is ``indent=2`` ASCII
        (``ensure_ascii=True``), matching the existing category modules.

        Args:
            scope: The target scope; must be ``GLOBAL`` or ``PROJECT``.
            items: The JSON-serializable payload to persist.
            project_id: Required for ``PROJECT`` scope.

        Raises:
            ValueError: from :func:`scoped_path` for ``BUILTIN`` scope, a
                missing project id, or a path that escapes the runtime root.
        """
        path = self.path(scope, project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / (path.name + ".tmp")
        tmp.write_text(
            json.dumps(items, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        os.replace(tmp, path)
