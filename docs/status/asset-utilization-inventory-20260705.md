# Asset Utilization Inventory - 2026-07-05

Lifecycle state: evidence record and planning input

Scope: repository assets plus locally visible agent assets. Local filesystem
roots are redacted as `CODEX_HOME`, `AGENTS_HOME`, and `DEVFRAME_RUNTIME` so the
public repository does not expose machine-specific private paths.

Related docs: [Skill Asset Utilization Plan](skill-asset-utilization-plan.md), [Agent Coding Discipline](../agent-runtime/agent-coding-discipline.md), [Methodology Skills Registry](../agent-runtime/methodology-skills.md), [Web AI Adapter Contract](../agent-runtime/web-ai-adapter-contract.md)

## Summary

The project has many useful assets, but utilization is uneven. The strongest
assets are methodology skills, MCP/Web-AI plumbing, schemas, tests, and review
bundle tooling. The weakest layer is not asset creation; it is asset accounting:
there is no unified asset ledger that records which asset was selected, why it
was selected, what artifact it produced, which evidence accepted it, and whether
it should be promoted, retired, or quarantined.

## Repository Snapshot

Observed on 2026-07-05.

| Metric | Count |
|---|---:|
| Git commits | 90 |
| Git branches | 15 |
| Files visible to `rg --files` | 716 |
| Built-in methodology skills under `tools/skills` | 7 |
| Rule documents under `rules` | 12 |
| Root schemas under `schemas` | 34 |
| Agent-runtime docs | 21 |
| Status docs | 79 |
| Control-plane modules | 64 |
| Control-plane test files | 45 |
| AI workflow hub top-level modules | 39 |
| Test-frame schemas | 16 |
| Runtime bootstrap files | 9 |

## Local Agent Asset Snapshot

Observed local asset counts:

| Local asset source | Count / status |
|---|---:|
| `CODEX_HOME/skills/**/SKILL.md` | 13 |
| `AGENTS_HOME/skills/**/SKILL.md` | 102 |
| Total local `SKILL.md` files | 115 |
| `CODEX_HOME/plugins/cache/**/plugin.json` | 31 |
| `CODEX_HOME/plugins/cache/**/*.mcp.json` | 3 |
| `CODEX_HOME/plugins/cache/**/.app.json` | 13 |
| Plugin marketplace candidate manifests under temp cache | 182 |
| Marketplace candidate MCP manifests under temp cache | 8 |
| Marketplace candidate app manifests under temp cache | 154 |
| Runtime custom skills at expected `skills.json` locations | 0 found |

Interpretation:

- The local machine has a large skill and plugin supply, but most of it is not
  governed project capability.
- The public repository should treat local/plugin assets as supply-chain inputs,
  not as automatically available product features.
- The absence of runtime `skills.json` at expected locations means custom skill
  creation/editing is implemented as a capability path but not currently
  populated as a used project asset in this runtime snapshot.

## Configured MCP Snapshot

The current local Codex config declares three MCP servers:

| MCP server | Role |
|---|---|
| `node_repl` | JavaScript execution kernel used by tooling and plugins |
| `codegraph` | repository code intelligence MCP |
| `pencil` | `.pen` design-file editor MCP |

Installed plugin-cache MCP manifests expose:

| Plugin-cache MCP manifest | Server |
|---|---|
| `build-ios-apps` | `xcodebuildmcp` |
| `cloudflare` | `cloudflare-api` |
| `openai-developers` | `openai-api-key-local-confirmation` |

The DevFrame MCP connection CLI could not read active connections because the
dashboard endpoint was not reachable during this audit. That is an accounting
gap: active MCP usage should be inspectable from an offline runtime ledger, not
only from a live dashboard.

## Project MCP Assets

Project files directly supporting MCP:

| Asset | Evidence |
|---|---|
| MCP server | `packages/control-plane/control_plane/mcp_server.py` |
| MCP consent | `packages/control-plane/control_plane/mcp_consent.py` |
| MCP live probe | `packages/control-plane/control_plane/mcp_live_probe.py` |
| Web-AI MCP result recorder | `packages/control-plane/control_plane/web_ai_mcp_recorder.py` |
| MCP CLI surface | `packages/control-plane/control_plane/cli/_mcp.py` |
| MCP tests | `test_mcp_server.py`, `test_mcp_live_probe.py`, `test_mcp_consent.py` |
| MCP docs/evidence | MCP recon receipts and live roundtrip evidence under `docs/status` |

Focused test count:

| Test file | Test functions |
|---|---:|
| `packages/control-plane/tests/test_mcp_server.py` | 17 |
| `packages/control-plane/tests/test_mcp_live_probe.py` | 22 |
| `packages/control-plane/tests/test_mcp_consent.py` | 9 |
| `packages/control-plane/tests/test_custom_skills.py` | 12 |
| `packages/control-plane/tests/test_rdgoal.py` | 74 |

Runtime evidence snapshot:

| Runtime evidence area | Count / status |
|---|---:|
| `DEVFRAME_RUNTIME/external-review-bundles` | 19 directories |
| `DEVFRAME_RUNTIME/web-ai-mcp-results` | 4 files |
| `DEVFRAME_RUNTIME/web-ai-sessions` | 6 files |
| Fixed browser profile config | present |

Interpretation:

- MCP has real code, docs, tests, and some runtime evidence.
- MCP is under-accounted, not absent.
- The main gap is a utilization ledger tying MCP sessions, tools, task intakes,
  consent decisions, evidence records, and downstream work items together.

## Utilization Classes

| Asset class | Current utilization | Risk |
|---|---|---|
| Built-in methodology skills | Discoverable and routable; now governed by skill plan | No usage ledger, no fingerprint, no promotion history |
| Local skills | Abundant local inventory | Easy to over-trust; not project capability until adopted |
| Plugin cache | Large installed/candidate supply | Supply-chain and scope confusion if treated as default capability |
| MCP core | Real code/tests/docs/evidence | Active connection state not offline-auditable |
| External-brain review bundles | Actively used | Bundle count exists, but accepted/rejected/deferred feedback is not normalized |
| Browser/CDP profile | Operationally important | Config exists outside repo; usage depends on handoff discipline |
| Schemas/tests | Strong substrate | Not yet connected to asset utilization scoring |
| Documentation plans | Rich and growing | Discoverability improved, but asset status can still drift |

## Low-Utilization, High-Value Assets

1. Runtime custom skills
   - Capability exists, but no runtime `skills.json` was found in expected
     locations.
   - Next action: create a governed sample custom skill only after a concrete
     work type needs it.

2. MCP active-usage ledger
   - MCP has code and tests, but active connection state required a live
     dashboard and was not available during this audit.
   - Next action: add offline-readable MCP utilization records after the
     review-governance kernel exists.

3. Plugin cache and MCP plugin manifests
   - There are 31 installed plugin manifests and many candidate marketplace
     manifests, but only a few are project-relevant today.
   - Next action: maintain an allowlist/quarantine ledger instead of importing
     plugin capabilities into the main workflow by default.

4. External-review feedback normalization
   - Review bundles are used often, but accepted/rejected/deferred feedback is
     still mostly per-run output.
   - Next action: normalize feedback ingestion into evidence and decision
     records once Phase 1A can validate them.

5. Skill utilization evidence
   - The project can resolve methodology skills, but cannot yet prove how often
     each skill produced accepted value.
   - Next action: implement `skill_usage` evidence only after the review-first
     kernel can validate completion and evidence.

## Proposed Asset Utilization Metrics

Add these metrics after Phase 1A:

| Metric | Meaning |
|---|---|
| `asset_id` | stable identifier for skill, MCP server/tool, plugin, schema, rule, or review bundle |
| `asset_type` | `skill`, `mcp_server`, `mcp_tool`, `plugin`, `schema`, `rule`, `review_bundle`, `browser_profile` |
| `source_tier` | repo canonical, local runtime, plugin cache, marketplace candidate, external |
| `selected_for_work_type` | work-type router row that selected the asset |
| `produced_artifact` | artifact created or updated by using the asset |
| `evidence_ids` | evidence that supports the asset's contribution |
| `gate_decision` | pass, blocked, insufficient evidence, human required, or deferred |
| `last_used_at` | last observed use |
| `promotion_state` | canonical, candidate, quarantined, deprecated, rejected |

## Recommended Next Steps

1. Keep the current public plan boundary: do not implement the utilization
   ledger before the review-governance kernel can validate evidence.
2. During Phase 1A, ensure the kernel packet can represent asset-backed evidence
   without adding a new top-level asset subsystem.
3. After Phase 1A, add a small asset utilization evidence shape that covers
   skills and MCP first.
4. Add MCP offline ledger support before dashboard-only MCP status becomes a
   dependency.
5. Build a project asset allowlist/quarantine view for local skills and plugin
   cache entries.
6. Surface utilization as read-only dashboard projection only after evidence and
   gate decisions exist.

## Audit Commands

Representative commands used:

```powershell
rg --files
Get-ChildItem tools\skills -Directory
Get-ChildItem CODEX_HOME\skills -Recurse -Filter SKILL.md
Get-ChildItem AGENTS_HOME\skills -Recurse -Filter SKILL.md
Get-ChildItem CODEX_HOME\plugins\cache -Recurse -Filter plugin.json
Get-ChildItem CODEX_HOME\plugins\cache -Recurse -Filter *.mcp.json
devframe mcp connections list --format json
scripts\verify-public-snapshot.ps1
```

The MCP connection command was blocked by an unreachable dashboard endpoint
during this audit, so current active MCP connection count is unknown.
