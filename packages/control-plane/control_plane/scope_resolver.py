"""Reusable, category-agnostic configuration resolution engine.

The customization layer stacks config in three scopes ordered least- to
most-specific (``built-in default < global < project``). This module owns the
shared, deterministic resolution logic so that no category (team, skills,
rules, run defaults, memory/preferences) re-implements it:

- **Phase 1 — scope merge** (:func:`merge_by_id`): merge per-scope record lists
  by id so the most-specific scope that defines an id wins, annotating each
  effective record with the scope it was selected from.
- **Phase 2 — deny-overrides** (added separately): fold capability flags with
  most-restrictive-wins and apply P0 rules as unconditional hard denies.

The two phases are kept strictly orthogonal: scope merge decides *which*
records are in scope and never inspects capability polarity, while the
deny-overrides pass decides *who* wins on a capability and never changes which
records are in scope.

Everything here is a pure, deterministic function of its inputs. There is no
I/O in this module; category modules supply already-loaded, per-scope record
lists (see ``scoped_store`` for malformed-safe loading).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Scope(str, Enum):
    """A configuration layer, ordered least- to most-specific.

    Values are the stable lowercase strings used for the ``_scope`` annotation
    on effective records and in the API surface.
    """

    BUILTIN = "builtin"
    GLOBAL = "global"
    PROJECT = "project"


# Ordered least- to most-specific. Iterating in this order and letting later
# scopes overwrite earlier ones means the most-specific defining scope wins on
# a tie (project > global > builtin).
SCOPE_ORDER: tuple[Scope, ...] = (Scope.BUILTIN, Scope.GLOBAL, Scope.PROJECT)


def merge_by_id(
    layers: dict[Scope, list[dict]],
    id_key: str = "id",
) -> list[dict]:
    """Phase 1 scope merge: the most-specific scope wins per record id.

    Iterates the layers in :data:`SCOPE_ORDER` (least- to most-specific) and
    keeps, for each distinct id, the record from the most-specific scope that
    defines it. Each effective record is annotated with ``_scope`` (the scope's
    string value) so the UI/audit can distinguish inherited from overridden
    values. Exactly one record is emitted per distinct id.

    Args:
        layers: Per-scope record lists. A scope may be absent or empty.
        id_key: The field used to key records for merging. Defaults to ``"id"``.

    Returns:
        One record per distinct id, in first-seen order, each carrying a
        ``_scope`` annotation naming the winning scope.

    Notes:
        - Records that are not dicts or that lack ``id_key`` are skipped, so a
          stray entry never raises here. Category loaders are responsible for
          per-record validation; this keeps the merge robust and deterministic.
        - Determinism: output depends only on layer contents and ``id_key``;
          within a layer, the last record for a given id wins (loaders dedupe).
    """
    merged: dict[object, dict] = {}
    for scope in SCOPE_ORDER:
        for record in layers.get(scope, []):
            if not isinstance(record, dict) or id_key not in record:
                continue
            rid = record[id_key]
            # Later scopes (more specific) overwrite earlier ones.
            merged[rid] = {**record, "_scope": scope.value}
    return list(merged.values())


@dataclass(frozen=True)
class ResolvedConfig:
    """The layered result of resolving one category.

    Exposes each scope layer alongside the scope-merged ``effective`` set so the
    API can render built-in/global/project plus the effective merge. The
    ``constraints`` field carries resolved capability constraints for
    capability-bearing categories (populated by the deny-overrides pass) and is
    ``None`` for categories without capability flags.
    """

    builtin: list[dict]
    global_: list[dict]
    project: list[dict]
    effective: list[dict]
    constraints: dict | None = None


# ---------------------------------------------------------------------------
# Phase 2 — deny-overrides (most-restrictive wins + P0 hard denies)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapabilityFlag:
    """A single capability flag and the value that wins under deny-overrides.

    ``restrictive_value`` is the value a unit must vote to *tighten* the flag.
    Resolution starts from the permissive opposite of this value and flips to
    ``restrictive_value`` the moment any enabled unit votes for it (or a P0 deny
    targets it). For example ``CapabilityFlag("readOnly", True)`` means
    read-only wins: the fold starts at ``False`` and any enabled unit with
    ``readOnly == True`` makes the effective value ``True``.
    """

    name: str
    restrictive_value: bool


@dataclass(frozen=True)
class CapabilityPolicy:
    """An ordered set of capability flags resolved independently of one another.

    Each flag in ``flags`` is folded on its own; flags never interact, so the
    order is irrelevant to the result and exists only for stable iteration.
    """

    flags: tuple[CapabilityFlag, ...]


# The capability policy for skills. Each flag declares the value that wins under
# most-restrictive resolution:
#   - readOnly                 -> restrictive value True  (read-only wins)
#   - networkEnabled           -> restrictive value False (no-network wins)
#   - requireRedGreenEvidence  -> restrictive value True  (require evidence wins)
SKILL_POLICY = CapabilityPolicy(
    flags=(
        CapabilityFlag("readOnly", True),
        CapabilityFlag("networkEnabled", False),
        CapabilityFlag("requireRedGreenEvidence", True),
    )
)


# Convention for matching a P0 deny rule to the capability flag it tightens.
#
# A P0 deny is a rule record (priority == "P0"). To decide which flag it forces
# to its restrictive value we use a simple, explicit, two-step convention:
#
#   1. Structured target (preferred): the deny record names its target flag
#      directly via one of these keys, checked in order: ``flag``, ``target``,
#      ``capability``. The value is compared to the flag name case-insensitively
#      (e.g. ``{"priority": "P0", "flag": "networkEnabled"}``).
#
#   2. Token alias (fallback): for human-authored rules that name an intent
#      rather than a flag, the deny's ``id``/``rule``/``name``/``text`` fields
#      are scanned for any known alias token below. This lets a P0 rule called
#      "no-network" force ``networkEnabled`` to its restrictive value.
#
# The alias table is intentionally small and explicit; it maps normalized
# (lowercased) tokens to the canonical flag name they tighten.
_DENY_TARGET_KEYS: tuple[str, ...] = ("flag", "target", "capability")
_DENY_TEXT_KEYS: tuple[str, ...] = ("id", "rule", "name", "text")
_DENY_FLAG_ALIASES: dict[str, str] = {
    "no-network": "networkEnabled",
    "no_network": "networkEnabled",
    "network": "networkEnabled",
    "offline": "networkEnabled",
    "read-only": "readOnly",
    "read_only": "readOnly",
    "readonly": "readOnly",
    "require-red-green-evidence": "requireRedGreenEvidence",
    "require_red_green_evidence": "requireRedGreenEvidence",
    "red-green-evidence": "requireRedGreenEvidence",
    "require-evidence": "requireRedGreenEvidence",
}


def deny_targets(deny: dict, flag: CapabilityFlag) -> bool:
    """Decide whether a P0 deny rule targets ``flag``.

    See the module-level convention above. Returns ``True`` when the deny names
    ``flag`` either by a structured target key (``flag``/``target``/
    ``capability``) or by a known alias token found in its
    ``id``/``rule``/``name``/``text`` fields.

    Args:
        deny: A P0 deny rule record.
        flag: The capability flag under consideration.

    Returns:
        ``True`` if the deny forces ``flag`` to its restrictive value.
    """
    if not isinstance(deny, dict):
        return False

    flag_lower = flag.name.lower()

    # Step 1: structured target keys (exact, case-insensitive flag-name match).
    for key in _DENY_TARGET_KEYS:
        value = deny.get(key)
        if isinstance(value, str) and value.lower() == flag_lower:
            return True

    # Step 2: alias tokens scanned in human-readable fields.
    for key in _DENY_TEXT_KEYS:
        value = deny.get(key)
        if not isinstance(value, str):
            continue
        haystack = value.lower()
        for token, target_flag in _DENY_FLAG_ALIASES.items():
            if target_flag == flag.name and token in haystack:
                return True
    return False


def resolve_capabilities(
    units: list[dict],
    policy: CapabilityPolicy,
    hard_denies: list[dict] | None = None,
) -> dict:
    """Phase 2 deny-overrides: most-restrictive flags + unconditional P0 denies.

    For each flag in ``policy`` independently:

    1. Start from the permissive opposite of ``flag.restrictive_value``.
    2. Fold over ``units``: skip any unit explicitly disabled
       (``unit.get("enabled") is False``); any enabled unit that votes the
       restrictive value (``unit.get(flag.name) == flag.restrictive_value``)
       flips the result to the restrictive value (most-restrictive wins).
    3. After the fold, apply every P0 deny that targets the flag
       (see :func:`deny_targets`) as an unconditional hard deny that forces the
       restrictive value regardless of how the permissive votes landed.

    Args:
        units: The scope-merged record set (capability-bearing units).
        policy: The capability policy describing which flags to resolve.
        hard_denies: P0 deny rules to apply as unoverridable hard denies.

    Returns:
        A mapping of flag name to its resolved boolean value.

    Notes:
        - Pure and deterministic: the result depends only on the inputs, and
          each flag is resolved independently of the others.
        - A unit missing a flag (or carrying a non-matching value) is treated as
          a permissive vote for that flag (it simply never flips the result).
    """
    result: dict = {}
    denies = hard_denies or []

    for flag in policy.flags:
        # Begin permissive: the opposite of the restrictive value.
        value = not flag.restrictive_value

        for unit in units:
            if not isinstance(unit, dict):
                continue
            if unit.get("enabled") is False:
                continue
            if unit.get(flag.name) == flag.restrictive_value:
                value = flag.restrictive_value  # any restrictive vote wins

        # P0 hard denies short-circuit any permissive votes for this flag.
        for deny in denies:
            if deny_targets(deny, flag):
                value = flag.restrictive_value
                break

        result[flag.name] = value

    return result


def collect_p0_denies(layers: dict[Scope, list[dict]]) -> list[dict]:
    """Collect P0 rule records across every scope layer.

    A P0 deny is any rule record whose ``priority`` field equals the string
    ``"P0"``. P0 rules act as unconditional hard denies in
    :func:`resolve_capabilities`; numeric priority lives only on rules.

    Args:
        layers: Per-scope record lists (the same shape passed to
            :func:`merge_by_id`).

    Returns:
        Every P0 rule record found, in scope order (builtin, global, project),
        preserving within-layer order. Non-dict entries are skipped.

    Notes:
        Collection is intentionally orthogonal to scope merge: P0 denies are
        gathered from *all* layers (a P0 rule at any scope is a hard deny), not
        just the most-specific defining scope, so a lower scope can never weaken
        a P0 governance rule.
    """
    denies: list[dict] = []
    for scope in SCOPE_ORDER:
        for record in layers.get(scope, []):
            if isinstance(record, dict) and record.get("priority") == "P0":
                denies.append(record)
    return denies


def resolve(
    category: str,
    loaders: object,
    project_id: str | None,
    policy: CapabilityPolicy | None = None,
) -> ResolvedConfig:
    """Orchestrate full resolution for one category: scope merge then deny-overrides.

    Collects the three scope layers from ``loaders``, runs the Phase 1 scope
    merge to produce the ``effective`` set, and — only when ``policy`` is
    provided — runs the Phase 2 deny-overrides pass (most-restrictive votes plus
    P0 hard denies collected from every layer) to produce ``constraints``.

    Args:
        category: The category name (carried for callers/audit; resolution is
            category-agnostic).
        loaders: An object exposing three malformed-safe, zero-argument-ish
            loaders: ``builtin()``, ``global_()``, and ``project(project_id)``.
            ``project`` is only consulted when ``project_id`` is truthy.
        project_id: The project scope identifier, or ``None`` for global-only
            resolution (the project layer is then empty).
        policy: The capability policy for capability-bearing categories. When
            ``None`` (e.g. team), ``constraints`` is omitted (left ``None``).

    Returns:
        A :class:`ResolvedConfig` exposing each layer, the scope-merged
        ``effective`` set, and ``constraints`` (``None`` when no policy).

    Notes:
        Pure and deterministic given the loader outputs; performs no I/O itself.
    """
    layers: dict[Scope, list[dict]] = {
        Scope.BUILTIN: loaders.builtin(),
        Scope.GLOBAL: loaders.global_(),
        Scope.PROJECT: loaders.project(project_id) if project_id else [],
    }

    effective = merge_by_id(layers)

    constraints: dict | None = None
    if policy is not None:
        constraints = resolve_capabilities(
            effective, policy, collect_p0_denies(layers)
        )

    return ResolvedConfig(
        builtin=layers[Scope.BUILTIN],
        global_=layers[Scope.GLOBAL],
        project=layers[Scope.PROJECT],
        effective=effective,
        constraints=constraints,
    )
