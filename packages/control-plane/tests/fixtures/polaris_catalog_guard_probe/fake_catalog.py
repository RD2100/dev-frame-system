"""Deterministic in-memory catalog guard for the PaperLab canary.

The fixture models the boundary between a broad Polaris ``tools/list`` result
and the eight model-facing PaperLab operations.  It intentionally contains no
MCP transport, network access, credentials, persistence, or production
imports.  A rejected or degraded generation never reaches the provider-call
counter and never yields an evidence candidate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping


SERVER_ALIAS = "polaris"
PUBLIC_PREFIX = f"mcp__{SERVER_ALIAS}__"

PAPERLAB_RAW_OPERATIONS: tuple[str, ...] = (
    "search_papers",
    "search_chunks",
    "get_paper",
    "lookup_paper",
    "read_fulltext",
    "get_paper_citation",
    "get_references",
    "get_citations",
)
PUBLIC_OPERATIONS: tuple[str, ...] = tuple(
    f"{PUBLIC_PREFIX}{operation}" for operation in PAPERLAB_RAW_OPERATIONS
)
MAX_CATALOG_ENTRIES = 64

BROAD_READONLY_EXTRA_NAMES: tuple[str, ...] = (
    "scan_papers",
    "grep_fulltext",
    "read_wiki",
    "get_concept",
    "knowledge_graph",
    "list_tasks",
)
HIDDEN_OR_AUTHORITY_NAMES: tuple[str, ...] = (
    "__internal_health",
    "server_config",
    "project_summary",
    "handoff_to_agent",
)
WRITE_NAMES: tuple[str, ...] = (
    "remember",
    "update_plan",
    "writeback",
    "mcp:write",
)
FOREIGN_NAMES: tuple[str, ...] = (
    "mcp__other__search_papers",
    "mcp__foreign__read_fulltext",
)


def _entry(name: str) -> dict[str, str]:
    return {"name": name}


DEFAULT_BROAD_CATALOG: tuple[dict[str, str], ...] = tuple(
    _entry(name)
    for name in (
        *PAPERLAB_RAW_OPERATIONS,
        *BROAD_READONLY_EXTRA_NAMES,
        *HIDDEN_OR_AUTHORITY_NAMES,
        *WRITE_NAMES,
        *FOREIGN_NAMES,
    )
)

CatalogStatus = Literal["ready", "unavailable"]


@dataclass(frozen=True)
class CatalogSnapshot:
    """The only state exposed to a model-facing canary."""

    generation: int
    status: CatalogStatus
    public_names: tuple[str, ...]
    reason: str | None

    @property
    def candidate_available(self) -> bool:
        """Return whether an invocation may produce a bounded candidate."""

        return self.status == "ready" and bool(self.public_names)


@dataclass(frozen=True)
class InvocationResult:
    """A bounded invocation outcome; the candidate is never authoritative."""

    ok: bool
    public_name: str
    error: str | None
    candidate: Mapping[str, str] | None


class FakeCatalogGuard:
    """Filter every catalog generation and guard every model-facing call."""

    def __init__(self) -> None:
        self._latest_generation = 0
        self._snapshot = CatalogSnapshot(
            generation=0,
            status="unavailable",
            public_names=(),
            reason="not_loaded",
        )
        self._provider_calls: list[str] = []

    @property
    def snapshot(self) -> CatalogSnapshot:
        """Return the immutable current catalog status."""

        return self._snapshot

    @property
    def provider_call_count(self) -> int:
        """Expose only the bounded call count used by assertions."""

        return len(self._provider_calls)

    @property
    def provider_calls(self) -> tuple[str, ...]:
        """Return public names that passed the invocation guard."""

        return tuple(self._provider_calls)

    def model_facing_catalog(self) -> tuple[str, ...]:
        """Return the exact stable eight-name model-facing catalog."""

        return self._snapshot.public_names

    def publish(
        self,
        catalog: object,
        *,
        generation: int,
        stale: bool = False,
    ) -> CatalogSnapshot:
        """Replace one catalog generation, failing closed on every defect.

        Generations are strictly increasing.  An older or repeated generation
        is treated as stale and clears the model-facing catalog instead of
        retaining potentially outdated callable names.
        """

        if not isinstance(generation, int) or isinstance(generation, bool):
            return self._unavailable(self._latest_generation, "invalid_generation")
        if generation <= self._latest_generation:
            return self._unavailable(self._latest_generation, "stale_generation")
        self._latest_generation = generation
        if stale:
            return self._unavailable(generation, "stale_catalog")

        names = self._parse_catalog(catalog)
        if names is None:
            return self._unavailable(generation, "malformed_catalog")
        if not names:
            return self._unavailable(generation, "empty_catalog")

        available_raw = set(names)
        if not set(PAPERLAB_RAW_OPERATIONS).issubset(available_raw):
            return self._unavailable(generation, "missing_allowlisted_operation")

        public_names = tuple(
            f"{PUBLIC_PREFIX}{operation}" for operation in PAPERLAB_RAW_OPERATIONS
        )
        self._snapshot = CatalogSnapshot(
            generation=generation,
            status="ready",
            public_names=public_names,
            reason=None,
        )
        return self._snapshot

    def reconnect(self, catalog: object, *, generation: int) -> CatalogSnapshot:
        """Model a reconnect as a complete replacement, never a merge."""

        return self.publish(catalog, generation=generation)

    def exhaust(self, *, generation: int) -> CatalogSnapshot:
        """Model bounded reconnect exhaustion with no retained candidate."""

        if not isinstance(generation, int) or isinstance(generation, bool):
            return self._unavailable(self._latest_generation, "invalid_generation")
        if generation <= self._latest_generation:
            return self._unavailable(self._latest_generation, "stale_generation")
        self._latest_generation = generation
        return self._unavailable(generation, "reconnect_exhausted")

    def invoke(self, public_name: object) -> InvocationResult:
        """Guard a public call before incrementing the provider-call counter."""

        if self._snapshot.status != "ready":
            return InvocationResult(
                ok=False,
                public_name=str(public_name),
                error="catalog_unavailable",
                candidate=None,
            )
        if not isinstance(public_name, str) or public_name not in self._snapshot.public_names:
            return InvocationResult(
                ok=False,
                public_name=str(public_name),
                error="name_not_allowlisted",
                candidate=None,
            )

        self._provider_calls.append(public_name)
        raw_name = public_name.removeprefix(PUBLIC_PREFIX)
        return InvocationResult(
            ok=True,
            public_name=public_name,
            error=None,
            candidate={
                "source": "fixture",
                "operation": raw_name,
                "authority": "devframe",
            },
        )

    @staticmethod
    def _parse_catalog(catalog: object) -> tuple[str, ...] | None:
        if not isinstance(catalog, (list, tuple)):
            return None
        if len(catalog) > MAX_CATALOG_ENTRIES:
            return None

        names: list[str] = []
        for entry in catalog:
            if isinstance(entry, str):
                name = entry
            elif isinstance(entry, Mapping):
                name = entry.get("name")
                if not isinstance(name, str):
                    return None
                if "enabled" in entry:
                    enabled = entry["enabled"]
                    if not isinstance(enabled, bool):
                        return None
                    if not enabled:
                        continue
            else:
                return None

            if name.startswith("mcp__"):
                if not name.startswith(PUBLIC_PREFIX):
                    continue
                name = name.removeprefix(PUBLIC_PREFIX)
            if name in PAPERLAB_RAW_OPERATIONS and name not in names:
                names.append(name)
        return tuple(names)

    def _unavailable(self, generation: int, reason: str) -> CatalogSnapshot:
        self._snapshot = CatalogSnapshot(
            generation=generation,
            status="unavailable",
            public_names=(),
            reason=reason,
        )
        return self._snapshot
