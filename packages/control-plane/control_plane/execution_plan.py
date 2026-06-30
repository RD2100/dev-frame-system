"""Executor-agnostic write-set scheduling for parallel coding-agent dispatch.

Two agents may run concurrently only if their write sets (target paths) do not
overlap. Overlapping agents are grouped and must run serially; non-overlapping
groups run in parallel. This is a universal file-write safety policy, not an
OpenCode feature, so it lives in the dispatch layer and references no executor.

An agent with no declared targets is treated as writing the whole repository and
therefore conflicts with every other agent (conservative default).
"""
from __future__ import annotations


def _normalize_targets(targets: list[str]) -> set[str]:
    normalized: set[str] = set()
    for target in targets or []:
        text = str(target).strip().replace("\\", "/").strip("/")
        if text:
            normalized.add(text)
    return normalized


def _conflicts(a: set[str], b: set[str]) -> bool:
    # Empty target set = whole-repo write scope = conflicts with everyone.
    if not a or not b:
        return True
    return not a.isdisjoint(b)


def plan_write_set_groups(targets_per_agent: list[list[str]]) -> list[list[int]]:
    """Group agent indices by transitive write-set overlap.

    Returns a list of groups; each group is a list of agent indices that must
    run serially. Groups may run in parallel with one another. Index order and
    group order follow the original agent order so scheduling stays deterministic.
    """
    count = len(targets_per_agent)
    if count == 0:
        return []

    normalized = [_normalize_targets(targets) for targets in targets_per_agent]
    parent = list(range(count))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: int, b: int) -> None:
        root_a, root_b = find(a), find(b)
        if root_a == root_b:
            return
        # Keep the lower index as root so group ordering stays deterministic.
        if root_a < root_b:
            parent[root_b] = root_a
        else:
            parent[root_a] = root_b

    for i in range(count):
        for j in range(i + 1, count):
            if _conflicts(normalized[i], normalized[j]):
                union(i, j)

    groups: dict[int, list[int]] = {}
    for index in range(count):
        groups.setdefault(find(index), []).append(index)

    # Order groups by their smallest member index for deterministic scheduling.
    return [groups[root] for root in sorted(groups)]
