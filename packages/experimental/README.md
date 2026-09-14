---
description: "The experimental group map: private prototypes and internal-only plugins excluded from official releases, for users and maintainers navigating the group."
kind: "package-group"
---

# packages/experimental

English | [中文](README.zh.md)

## Summary

The experimental group contains prototype capabilities that are not part of any official release: they run on the real harness, but their contracts can change and they carry no support promise. The group holds Agent Teams, the expert-team pipelines over persona packs, the cross-realm Inspector, the CPython subprocess backend for the code-execution seam, and the browser-worker runtime and image packer used by preview deployments. Use these packages to try an unreleased capability; they carry no stability promise, and released products must not depend on them.

## Table of Contents

- [Packages](#packages)
- [Related documentation](#related-documentation)
- [Dev Note](#dev-note)

-----

<a id="packages"></a>
## Packages

| Package | Role | ctx key |
|---|---|---|
| [`agent-hierarchy`](agent-hierarchy/README.md) | Three-role policy, creation-entry guard, plugin-scope validation, and cold recovery for the pluginized hierarchy | `ctx.agentHierarchy` |
| [`agent-team-profile`](agent-team-profile/README.md) | Explicit source-checkout profile layer for Agent Teams | — |
| [`agent-team`](agent-team/README.md) | Named teammates with durable messages and a shared task board | `ctx.agentTeams` |
| [`agent-team-web-profile`](agent-team-web-profile/README.md) | Explicit source-checkout Web layer for Agent Teams | — |
| [`agent-worktree`](agent-worktree/README.md) | Per-agent worktree seam over the worktree registry: single-writer bindings and the three `worktree_*` tools | `ctx.agentWorktree` |
| [`client-ui-agent-team`](client-ui-agent-team/README.md) | Team roster, task board, and teammate navigation for Web | — |
| [`code-runtime-python`](code-runtime-python/README.md) | CPython subprocess backend for the code-execution seam | `ctx.codeRuntime` |
| [`devframe`](devframe/README.md) | Shared contracts for the experimental single-project controller | — |
| [`devframe-profile`](devframe-profile/README.md) | Explicit source-checkout Web profile layer mounting the DevFrame stack | — |
| [`expert-pack-dev`](expert-pack-dev/README.md) | Software-development data pack for the expert-team core: six Chinese-primary expert personas (product-manager, architect, tech-lead, engineer, qa, code-reviewer), a hierarchical six-phase team with two human gates, result JSON Schemas, and an acceptance-checklist skill | data pack — no ctx key |
| [`expert-pack-paper`](expert-pack-paper/README.md) | Paper-research data pack for the expert-team core: four Chinese-primary expert personas, a four-phase human-gated pipeline, a review-checklist skill, and phase-result JSON Schemas | data pack — no ctx key |
| [`expert-team`](expert-team/README.md) | Expert-team core: fail-loud pack mounting, pipeline orchestration with human-review gates, persona-derived phase subagents, and the five model tools | `ctx.expertTeam` |
| [`inspector`](inspector/README.md) | Cross-realm CDP hub for Host debugging, Client Runtime inspection, network capture, and Cordis trees | `ctx.inspector` |
| [`agent-evidence`](agent-evidence/README.md) | Append-only evidence ledger for agent work: task/Goal binding receipts, submission receipts, and verification snapshots | `ctx.agentEvidence` |
| [`agent-reliability`](agent-reliability/README.md) | Process-tree stop, admission cutoff, uncertain-call reconciliation, and the flush barrier as one service | `ctx.agentReliability` |
| [`project-contracts`](project-contracts/README.md) | Shared type vocabulary for the pluginized agent hierarchy: roles, task states, ids, records, and store seams | — |
| [`project-controller`](project-controller/README.md) | Project task board: TaskState transitions, a bounded developing budget, lifecycle, and the controller-only merge gate | `ctx.projectController` |
| [`project-memory`](project-memory/README.md) | Bounded append-only project memory over a user-selected Obsidian Vault subtree: scoped search/read/append tools, session-log receipts, path containment, and honest failure reporting | library service — no ctx key |
| [`session-identity`](session-identity/README.md) | Durable agent binding registry and exact-cwd native Session creation | `ctx.agentBindings` |
| [`shadow-routing`](shadow-routing/README.md) | Service Definition for the shadow routing seam: the abstract router contract, routing vocabulary, and the `shadow/delivery-received` event | `ctx.shadowRouter` |
| [`shadow-controller`](shadow-controller/README.md) | Read-only Remote owner of the Shadow router status snapshot for host status surfaces | `ctx.shadowController` |
| [`shadow-web-profile`](shadow-web-profile/README.md) | Explicit source-checkout Web layer for the resident Shadow entry card | — |
| [`client-ui-shadow-entry`](client-ui-shadow-entry/README.md) | Resident Web Shadow entry card above Settings with the honest status panel | — |
| [`tool-agent-team`](tool-agent-team/README.md) | Ten tools that let the model create, message, and coordinate teammates | registers scoped tools on `ctx.tools` |
| [`webworker-packer`](webworker-packer/README.md) | Builds the gzip-compressed VFS image consumed by the browser worker preview | library and CLI — no ctx key |
| [`webworker-runtime`](webworker-runtime/README.md) | Runs the harness plugin tree inside a dedicated browser worker | library and worker entry — no ctx key |

-----

<a id="related-documentation"></a>
## Related documentation

- [Experimental package decision](../../.agents/notes/implemented/architecture/2026-08-18-experimental-agent-teams-packages.md) — placement, release exclusion, and dependency isolation.
- [Agent Teams subsystem](../../docs/subsystems/agent-team.md) — durable Team types and the `ctx.agentTeams` service API.
- [Experimental subtree rules](AGENTS.md) — what experimental status does and does not relax.

-----

<a id="dev-note"></a>
## Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
