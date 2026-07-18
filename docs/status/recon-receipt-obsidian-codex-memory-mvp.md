# Recon Receipt: Obsidian To Codex Governed Memory MVP

Lifecycle state: **APPROVED FOR THE BOUNDED SLICE BELOW**

Receipt ID: `RECON-OBSIDIAN-CODEX-MEMORY-MVP-20260718`

This receipt satisfies `rules/recon.md` recon-001/002/003/005/009 and
`rules/open-source-reuse.md` for a thin extension of the existing DevFrame MCP
server. It does not authorize a new memory platform, a custom Obsidian plugin,
or mutation of Codex's generated local memory files.

## Target

- user_goal: Use the repository's Obsidian design with Codex to improve durable
  model memory, retrieval, and governed write-back.
- target_repo_or_kb: this public `dev-frame-system` checkout at
  `b996c74f754bf0c277930767f6d5efccee467ca6` plus a disposable test vault.
- current_slice_goal: Let an authorized Codex MCP client search explicitly
  allowlisted Obsidian Markdown notes and propose a new candidate memory note
  through the existing human-gated write-back lifecycle.
- requested_outcome: A real MCP path for bounded retrieval plus a proposal-only
  write path that cannot scan a whole vault, overwrite an existing note, expose
  an absolute vault path, or bypass human approval.
- date: 2026-07-18
- planner_agent_id: root Codex coordinator
- model_request: `gpt-5.6-sol`, reasoning `high`; three read-only research
  workers were dispatched with that selector, but the service returned capacity
  and HTTP 429 failures. The runtime exposed the requested selector, but no
  successful worker identity attestation was produced.

## Resource Map

- repository_roots:
  - repository root (the checkout containing this receipt)
  - protected source worktree retained outside the public slice
- top_level_tree:
  - `packages/control-plane/`: DevFrame governance kernel, dashboard, MCP server,
    write-back proposal store, and tests.
  - `packages/ai-workflow-hub/`: existing Obsidian REST, allowlisted-note, and
    local RAG pilots.
  - `docs/agent-runtime/`: stable implemented behavior.
  - `docs/status/`: scoped Recon Receipts and historical planning evidence.
  - `schemas/`: memory and runtime contracts.
- important_dirs:
  - `packages/control-plane/control_plane`
  - `packages/control-plane/tests`
  - `packages/ai-workflow-hub/src/ai_workflow_hub/context_layer/adapters`
  - `schemas/agent-runtime`
- docs_read:
  - `AGENTS.md`
  - `rules/recon.md`
  - `rules/open-source-reuse.md`
  - `rules/git.md`
  - `docs/status/recon-receipt-devframe-mcp-server.md`
  - `docs/status/recon-receipt-obsidian-stage3.md`
  - `docs/status/recon-receipt-obsidian-stage4-sync.md`
  - `docs/status/project-and-cross-project-memory-harness-governance-plan.md`
  - `docs/status/context-management-architecture-plan.md`
  - `docs/status/context-noise-governance-and-automation-plan.md`
  - `docs/status/model-knowledge-gap-governance-plan.md`
- examples_read:
  - `packages/ai-workflow-hub/tests/test_obsidian_rest_api.py`
  - `packages/control-plane/tests/test_mcp_server.py`
  - `packages/control-plane/tests/test_writeback.py`
- packages_apps_modules:
  - `control_plane/mcp_server.py`: existing consent-gated MCP JSON-RPC surface.
  - `control_plane/writeback.py`: existing safe-path, atomic, human-gated
    proposal/apply lifecycle.
  - `control_plane/mcp_consent.py`: connection authorization and audit.
  - `ai_workflow_hub/.../obsidian_rest_api.py`: existing managed-block REST
    sync for the paper domain.
  - `ai_workflow_hub/.../rag_faiss_obsidian_local_pilot.py`: existing
    allowlisted local retrieval pilot; not a default dependency for this slice.
- runtime_entrypoints:
  - dashboard `POST /mcp`
  - MCP `initialize -> tools/list -> tools/call`
  - dashboard approval response for `wb-*` proposals
- ui_entrypoints:
  - Obsidian renders the generated candidate Markdown inbox.
  - Existing DevFrame approval surfaces render pending write-back proposals.
- service_entrypoints:
  - existing loopback DevFrame MCP server
  - optional existing Obsidian Local REST API, out of scope for the default path
- state_storage_locations:
  - caller-authorized Obsidian vault root from
    `DEVFRAME_OBSIDIAN_MEMORY_ROOT`
  - pending proposal JSON under the existing DevFrame runtime
    `writeback-proposals/`
- external_integrations:
  - Codex local MCP client
  - Obsidian Markdown vault
  - optional Obsidian Local REST API for later managed-block sync
- notable_generated_or_vendor_paths:
  - Codex native local memories under `$CODEX_HOME/memories/` are generated
    state and stay outside this repository.
  - no external source tree or model output is vendored.
- license_files_found:
  - root `LICENSE`; no third-party code is copied by this slice.

## Verified Current Facts

- The current Codex manual documents separate local Codex Memories, disabled by
  default, with generated state under `$CODEX_HOME/memories/`. It explicitly
  says required team guidance belongs in `AGENTS.md` or checked-in docs and that
  generated memory files should not be the primary manual control surface:
  <https://learn.chatgpt.com/docs/customization/memories>.
- Local command evidence on 2026-07-18:
  `codex features list` reported `memories experimental false`.
- The existing DevFrame MCP server already requires connection consent before
  any tool call and already exposes proposal-only write-back.
- Existing Obsidian code already proves path checks, allowlisted reads,
  token-safe reports, managed-block merge planning, and explicit apply.
- No CodeGraph MCP tools were exposed in this session. An existing `.codegraph`
  index was present outside the public slice, so no index write was authorized
  or performed; bounded literal search was used instead.

## Core Concepts

- Codex native memory: automatic local recall generated from eligible chats;
  useful but generated, experimental, and not project authority.
- Curated Obsidian memory: user-owned Markdown with source, scope, freshness,
  authority, and review-visible content.
- Memory context: a bounded MCP result containing selected excerpts and source
  metadata. It is guidance, not evidence or a final decision.
- Candidate write-back: a new note proposed into a fixed inbox. The AI cannot
  approve it, choose an arbitrary filesystem root, or overwrite an existing
  note.
- Promotion: a later human review or governed policy action; not part of this
  slice.

## Core Data Models

- project/workspace: DevFrame `projectId` plus a separately authorized vault
  root.
- thread/session: consented MCP session id.
- message/event: MCP tool call plus existing MCP audit event.
- tool_call: `search_obsidian_memory` or `propose_obsidian_memory`.
- terminal_run: focused pytest and a running loopback MCP real-path probe.
- diff/checkpoint: existing `wb-*` proposal preview and approval lifecycle.
- review/evidence: relative note path, content SHA-256, relevance score, source
  refs, freshness, authority, limitations, and test output.
- policy/rules: memory is not authority; explicit allowlist; no whole-vault
  scan; candidate-only write; no secret persistence; no native-memory mutation.

## Capability Matrix

- capability_name: Codex automatic local Memories
  - location: Codex host, `$CODEX_HOME/memories/`
  - maturity: experimental and disabled on the inspected host
  - reusable_as_is: optional recall layer
  - reusable_with_adapter: no documented external injection API
  - not_reusable: as the canonical governed store
  - notes: do not edit or depend on generated files as the primary interface.
- capability_name: DevFrame MCP consent and audit
  - location: `control_plane/mcp_server.py`, `control_plane/mcp_consent.py`
  - maturity: implemented and tested
  - reusable_as_is: yes
  - reusable_with_adapter: yes, add two bounded tools
  - not_reusable: false
- capability_name: Human-gated filesystem write-back
  - location: `control_plane/writeback.py`
  - maturity: implemented and tested
  - reusable_as_is: yes
  - reusable_with_adapter: generate a create-only memory inbox note
  - not_reusable: false
- capability_name: Obsidian Markdown store and UI
  - location: caller-owned vault
  - maturity: mature external product
  - reusable_as_is: yes
  - reusable_with_adapter: safe relative-path reader and generated inbox note
  - not_reusable: false
- capability_name: Obsidian Local REST API
  - location: existing ai-workflow-hub adapter plus external plugin
  - maturity: pilot adapter around a mature external surface
  - reusable_as_is: later live sync
  - reusable_with_adapter: yes
  - not_reusable: for the default zero-credential test path
  - notes: deferred; the MVP needs no API key or plugin.
- capability_name: Vector or graph memory backend
  - location: Mem0/OpenMemory, Letta, Graphiti/Zep, LangGraph/LangMem,
    LlamaIndex, or similar
  - maturity: mature external choices
  - reusable_as_is: not yet required
  - reusable_with_adapter: evaluate only after retrieval metrics expose a gap
  - not_reusable: as a phase-one dependency
  - notes: bounded deterministic retrieval is enough for the first real path.

## Reuse Candidate List

- candidate: existing DevFrame MCP server
  - source: `docs/status/recon-receipt-devframe-mcp-server.md`
  - exact_scope_to_reuse: transport, connection consent, tool audit, result
    encoding, and loopback server.
  - expected_adapter_work: register and dispatch two tools.
  - blocking_constraints: all tool calls remain consent-gated.
  - decision: reuse now.
- candidate: existing DevFrame write-back lifecycle
  - source: `packages/control-plane/control_plane/writeback.py`
  - exact_scope_to_reuse: safe path resolution, atomic proposal persistence,
    human approval, audited apply.
  - expected_adapter_work: generate a unique note under a fixed inbox and reject
    any existing target.
  - blocking_constraints: the AI cannot control the vault root or approval.
  - decision: reuse now.
- candidate: Obsidian Markdown/frontmatter
  - source: <https://help.obsidian.md/Editing+and+formatting/Properties>
  - exact_scope_to_reuse: human-readable durable note store and metadata.
  - expected_adapter_work: parse a small allowlisted property set and generate
    candidate frontmatter.
  - blocking_constraints: do not scan `.obsidian/` or the entire vault.
  - decision: reuse now.
- candidate: Obsidian Local REST API
  - source: <https://github.com/coddingtonbear/obsidian-local-rest-api>
  - exact_scope_to_reuse: later heading/frontmatter read-write and open note.
  - expected_adapter_work: existing repository adapter.
  - blocking_constraints: key/plugin setup and live private-vault authorization.
  - decision: defer.
- candidate: Mem0/OpenMemory, Letta, Graphiti, LangGraph/LangMem
  - source: their upstream projects, already cataloged in the project memory
    harness plan.
  - exact_scope_to_reuse: later semantic, temporal, or consolidation backend.
  - expected_adapter_work: backend interface only after evaluation fixtures.
  - blocking_constraints: added dependency, privacy surface, operations, and
    premature backend-led architecture.
  - decision: defer.

## Integration Risk Table

- risk: whole private vault enters model context
  - type: privacy
  - severity: P0
  - mitigation: configured root plus explicit non-empty relative path allowlist;
    no recursive default and no caller-supplied absolute path.
  - owner: memory adapter
- risk: prompt injection inside a memory note
  - type: security
  - severity: P0
  - mitigation: mark all returned content as untrusted reference material,
    return bounded excerpts, and never interpret note text as tool instructions.
  - owner: MCP tool contract
- risk: AI overwrites user-authored notes
  - type: privacy/ux
  - severity: P0
  - mitigation: proposal path is generated under a fixed inbox and must not
    exist; staging records a create-only constraint and the final approved
    apply must use exclusive creation so an approval-time race fails instead of
    replacing a file; existing write-back still requires human approval.
  - owner: proposal adapter plus write-back gate
- risk: secrets become memory
  - type: security
  - severity: P0
  - mitigation: block common credential/private-key patterns before retrieval
    output or proposal staging; never echo rejected content.
  - owner: memory adapter
- risk: stale or cross-project memory becomes authority
  - type: correctness
  - severity: P1
  - mitigation: include scope, authority, freshness, source refs, and explicit
    limitations in every result; default missing values to low authority.
  - owner: context result builder
- risk: hidden mutation of Codex native memory
  - type: maintenance/privacy
  - severity: P1
  - mitigation: no writes under `$CODEX_HOME/memories/`; activation of the
    experimental native feature remains a separate global-config human gate.
  - owner: root coordinator
- risk: duplicate custom MCP/runtime
  - type: maintenance
  - severity: P1
  - mitigation: extend the existing MCP server and proposal store only.
  - owner: control plane

## Build-vs-Buy Decision

- must_reuse:
  - Codex MCP client surface
  - existing DevFrame MCP consent/audit
  - existing DevFrame human-gated write-back
  - Obsidian Markdown/frontmatter
- should_adapt:
  - existing ai-workflow-hub Obsidian REST path in a later live-sync slice
  - an external memory backend only after evaluation proves deterministic
    retrieval insufficient
- can_spike:
  - SQLite FTS5 or hybrid reranking after precision/recall fixtures exist
- must_build_new:
  - one small safe Obsidian memory adapter: configured root resolution,
    allowlisted note read, bounded scoring/excerpt, secret guard, and
    server-generated candidate note.
- rationale: Governance and storage surfaces already exist. DevFrame only needs
  the thin policy adapter that makes their boundary explicit to Codex.

## Unknowns / Questions

- unanswered_items:
  - final user vault path and desired inbox folder
  - whether native Codex Memories should later be enabled globally
  - whether semantic retrieval is useful enough to justify an index
- required_verification:
  - disposable-vault real MCP round trip
  - no absolute path or rejected note content in the result
  - explicit paths required and traversal/symlink paths blocked
  - proposal stages one create-only `wb-*` request and leaves the vault
    unchanged until human approval
  - approved proposal writes exactly one generated inbox note
- experiments_needed:
  - run retrieval precision/abstention fixtures before adding FTS/vector search
  - separately human-authorize a real private vault smoke test later

## Recommended Next Slice

- smallest_safe_increment:
  - add a small `obsidian_memory.py` adapter;
  - expose `search_obsidian_memory` and `propose_obsidian_memory` through the
    existing consent-gated MCP server;
  - reuse `stage_writeback_proposal` for a generated create-only inbox note;
  - document the environment setting and native-memory boundary.
- worker_type_needed:
  - one coding worker, one independent reviewer, root acceptance coordinator.
- files_or_modules_in_scope:
  - `packages/control-plane/control_plane/obsidian_memory.py`
  - `packages/control-plane/control_plane/mcp_server.py`
  - `packages/control-plane/control_plane/dashboard.py`, only to bound the
    existing `/mcp` request body and require strict UTF-8 decoding
  - `packages/control-plane/control_plane/mcp_consent.py`, only to expose
    whether a tool-call audit was persisted and whether authorization came
    from a current human decision or a persisted client-name grant
  - `packages/control-plane/control_plane/writeback.py`, only to add an
    opt-in redacted proposal preview while retaining the private apply root
  - `packages/control-plane/tests/test_obsidian_memory.py`
  - `packages/control-plane/tests/test_mcp_server.py`
  - `packages/control-plane/tests/test_mcp_consent.py`, only for current-session
    authorization provenance and audit-result regressions
  - `packages/control-plane/tests/test_writeback.py`, only for the redacted
    preview regression
  - `docs/agent-runtime/obsidian-codex-memory.md`
  - `docs/agent-runtime/capability-inventory.md`
  - `docs/status/status-document-inventory.md`, only to register this scoped
    Recon Receipt in the existing status-document index
  - this receipt
- files_or_modules_out_of_scope:
  - `$CODEX_HOME/config.toml`
  - `$CODEX_HOME/memories/`
  - any real private vault
  - `packages/ai-workflow-hub/` production paths
  - vector/graph databases
  - custom Obsidian plugin or UI
  - automatic promotion or cross-project memory
- evidence_required_for_completion:
  - focused unit tests for read/path/secret/proposal behavior
  - a running dashboard MCP round trip using a disposable vault
  - existing MCP/write-back regression tests
  - `scripts/verify-public-snapshot.ps1`
  - `git diff --check`
  - independent review with zero unresolved P0/P1 findings
- review_gate_definition:
  - block if the adapter can scan a vault without explicit paths, expose an
    absolute root, return a secret-bearing excerpt, overwrite an existing note,
    write before approval, mutate Codex generated memories, or treat memory as
    authority.

## Approval

The root coordinator approves only the bounded slice above. Approval is based
on inspected committed code, existing tests, current Codex manual evidence,
local `codex features list` evidence, and prior scoped Obsidian/MCP receipts.
Any additional store, index, UI, automatic promotion, real-vault access, or
global Codex configuration change requires a new gate.

### Same-Risk Write-Set Amendment

During interface review, the planner confirmed that the existing generic
`list_pending_writebacks` projection returns the proposal `preview`, whose
default shape contains `workspace_root`. Returning that preview for an Obsidian
memory proposal would disclose the absolute private vault root even if the new
tool sanitized its immediate response. The approved slice therefore includes a
backward-compatible, opt-in write-back staging flag that removes
`workspace_root` from the stored/public preview while retaining the private
top-level root required by the later human-approved apply. Existing callers and
project write-back behavior must remain unchanged.

The same amendment also permits an opt-in create-only proposal constraint.
Checking non-existence only at staging is insufficient because another process
could create the target before approval. For memory inbox proposals, the final
apply must perform an exclusive create and fail closed on an existing target;
ordinary write-back proposals keep their current create-or-modify behavior.

### Sensitive MCP Authorization Amendment

Read-only threat probes confirmed two pre-existing properties that are too weak
for a private memory vault: tool-call audit persistence is best-effort, and a
persisted `allow_always` grant is keyed by the client-reported name. Existing
MCP tools retain their compatibility behavior, but the two new memory tools
must fail closed unless their current tool-call audit was durably appended and
the active connection was authorized by a human decision in the current
session. An automatically restored client-name grant may connect and use the
ordinary MCP surface, but it cannot read or propose private memory until the
current connection is explicitly approved.

### MCP Request-Boundary Amendment

The running loopback endpoint currently reads the caller-declared
`Content-Length` without a byte cap and decodes malformed UTF-8 with replacement
characters. Because the memory tools process private local content and share
this transport, the same bounded slice includes a narrow `dashboard.py` change:
`POST /mcp` must reject oversized request bodies before reading them and reject
invalid UTF-8 instead of normalizing it. Other dashboard POST routes and their
compatibility behavior remain out of scope. Real loopback HTTP tests in the
already-approved `test_mcp_server.py` must cover both failures.
