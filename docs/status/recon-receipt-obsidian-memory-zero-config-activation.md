# Recon Receipt: Obsidian Memory Zero-Configuration Activation

Lifecycle state: **IMPLEMENTED MVP CANDIDATE -- FINAL INDEPENDENT REVIEW PENDING**

Receipt ID: `RECON-OBSIDIAN-MEMORY-ZERO-CONFIG-ACTIVATION-20260718`

## 2026-07-18 Independent Review Closure Amendment

Two independent read-only reviews blocked the candidate after the operational
repair increment. They found incomplete TOML same-name detection, no
cross-process lifecycle transaction or crash recovery, non-byte-exact hook and
newline restoration, a mismatch between the human-visible proposal and the
eventual applied note, and missing installed-wheel/real-Link evidence. They
also correctly found that the repair-only write set below did not describe the
whole dirty candidate. No real user repair, staging, or commit occurred before
those findings were accepted.

The owner had already authorized continued development to formal personal-use
readiness. The root coordinator therefore re-approves one closure slice under
`recon-001/003/004/009/010` and `agent-discipline-001/004/005/006/008/010/012`.
Its exact public write set is:

- `docs/agent-runtime/obsidian-codex-memory.md`;
- `docs/status/status-document-inventory.md`;
- this Recon Receipt;
- `packages/control-plane/setup.py`;
- `packages/control-plane/control_plane/cli/_usage.py`;
- `packages/control-plane/control_plane/cli/app.py`;
- `packages/control-plane/control_plane/cli/_memory.py`;
- `packages/control-plane/control_plane/obsidian_memory.py`;
- `packages/control-plane/control_plane/obsidian_memory_activation.py`;
- `packages/control-plane/control_plane/writeback.py`;
- `packages/control-plane/tests/test_obsidian_memory_activation.py`;
- `scripts/verify-control-plane-wheel.ps1`.

The sensitive approval/writeback files are included because activation-managed
memory must bind the pending proposal to the exact final bytes a human reviews,
retain create-only/exactly-once recovery, and never auto-promote a different
payload. The packaging files are included because a real installed wheel
reproduced a zero-configuration activation failure: it could not find a source
`setup.py`. The approved fix may build a temporary source snapshot only from
the installed distribution's RECORD-hashed `control_plane` files; it must not
inherit host site-packages, vendor a runtime, or broaden the read tool surface.

The closure implementation must also:

- parse the complete current and proposed Codex TOML, rejecting every semantic
  representation of an existing same-name server;
- preserve unrelated config, instructions, and hooks bytes across activation
  and deactivation, including CRLF and compact JSON;
- serialize confirmed lifecycle operations with a cross-process lock and put a
  durable, least-content transaction record in place before the first managed
  file mutation; recovery may only move exact before/after hashes forward;
- reject an unavailable fixed runtime during repair and re-probe runtime
  identity before each facade tool call;
- bind the isolated facade to a deterministic digest of every installed
  `control_plane` payload file rather than accepting another same-version
  wheel or stale editable snapshot; a legacy/stale facade may be refreshed
  only when the exact dependency marker and managed state path still match;
- force-reinstall only that staged facade under a controlled environment that
  excludes caller Python/venv injection variables; do not force-reinstall or
  silently change the fixed dependency lock;
- keep repair preview zero-write while reporting a required facade refresh,
  and let confirmed repair perform that bounded refresh before restoring the
  missing config block so recovery never depends on an intentionally failing
  activation command;
- keep the proposal record pending outside the Vault while making its reviewed
  payload byte-identical to the create-only payload applied after approval;
- prove process-exit recovery, two-process competition, installed-wheel CLI,
  real stdio `tools/list`, actual Link recall after approval, hook execution,
  precise deactivation, public-snapshot, and full regression behavior.

The root coordinator approves this finite closure write set. Acceptance still
requires a new independent review with P0/P1 = 0, exact diff reconciliation,
and one path-specific local commit. Push, merge, release, private/mixed Vault
access, automatic memory promotion, and any broader MCP tool remain outside the
human gate.

## 2026-07-18 Operational Drift Recovery Amendment

The first real user-home activation later entered a partially drifted state:
the activation record, managed `AGENTS.md` instructions, `SessionStart` hook,
isolated runtime, and dedicated Vault scaffold remained intact, but the exact
managed MCP block was no longer present in `config.toml`. The existing status
and deactivation paths correctly failed closed. The installed main-worktree
`devframe` entrypoint also did not yet contain the candidate `memory` command,
so there was no supported recovery path for personal use.

This observed production-shaped failure authorizes one same-risk recovery
increment under `agent-discipline-001`, `agent-discipline-005`,
`agent-discipline-008`, and `agent-discipline-012`:

- add an explicit `devframe memory repair` command with a zero-write preview
  default and a required `--confirm` mutation gate;
- derive every repairable block from the existing activation record and the
  fixed runtime contract; never accept caller-supplied replacement text;
- restore only a completely absent managed config block while preserving
  unrelated current config content; the managed instructions and hook must
  still match the activation record exactly;
- reject partial markers, a same-name unmanaged MCP server, changed managed
  content, changed Codex home, incompatible state, unsafe paths, or runtime and
  Vault provenance failure;
- update the exact added-text record when a restored block acquires a new
  separator so later deactivation can still remove only DevFrame-owned text;
- apply repair writes as one rollback-capable transaction and leave the Vault,
  approved memories, and isolated runtime unchanged;
- prove the real missing-config failure with RED-to-GREEN tests, including
  preview, unrelated-content preservation, exact deactivation after repair,
  conflict rejection, and rollback when the final state write fails.

This repair-only write set was later superseded by the Independent Review
Closure Amendment above after concrete review findings and an installed-wheel
RED probe proved that packaging, approval payload, and lifecycle transaction
paths also required changes. The read-plane tool allowlist remains exactly
`status` and `recall`; neither amendment exposes proposal, approval, upstream
write, delete, admin, or command tools.

Approval gate: the root coordinator approves this amendment for one coding
worker only after the dirty baseline and per-path hashes are captured. Final
acceptance still requires an independent reviewer, zero unresolved P0/P1
findings, focused and broader tests, public-snapshot verification, an actual
fresh Codex process listing only `status` and `recall`, and exact diff
reconciliation before any local commit.

## 2026-07-18 Implementation Reconciliation

The selected read plane is now a DevFrame facade over Link 1.7.0 rather than
the earlier Local REST spike. The facade exposes only `status` and `recall`.
Pending proposal records stay outside the Vault; the payload shown for approval
is the exact reviewed/active note payload that the existing create-only,
exactly-once writeback path may apply after the human decision.

The Windows CPython 3.10 runtime dependency set, including Link 1.7.0 and MCP
1.28.1, is an exact-version wheel lock with a SHA-256 for every package.
Provisioning rejects host site-package inheritance, verifies that
Link, MCP, and the control plane load from the isolated venv, binds the complete
installed control-plane payload to a schema-2 manifest digest, and removes a
newly created runtime if provisioning fails before an activation journal needs
it. A dependency-exact legacy facade is refreshed in place and re-verified;
dependency marker drift still fails closed. Codex-home drift, `resume` startup
recall, pre-parse response bounds, exact approval payloads, runtime refresh,
and lifecycle crash recovery have production-path regression tests.

The lock is intentionally platform-specific. Other Python/platform combinations
need their own generated and reviewed lock before support can be claimed.

## 2026-07-18 Ecosystem Re-evaluation Amendment

This amendment is newer than the original receipt below and supersedes it
where the two conflict. The original text remains as an audit trail of the
first approved spike. No Local REST API plugin installation, real Codex-home
activation, staging, or commit occurred before this gate was reopened.

The user supplied a current "Codex + Obsidian self-growing knowledge base"
example and explicitly requested a broader ecosystem search. That search found
that the viral workflow is primarily the LLM Wiki pattern rather than a single
Obsidian MCP product. The authoritative idea file defines three layers --
immutable raw sources, an agent-maintained Markdown wiki, and an `AGENTS.md` or
equivalent schema -- plus ingest, query, lint, and answer-backflow operations.
The existing single-`memory.md` activation would provide connectivity but not
that compounding knowledge loop.

### Newly inspected candidates

- `gowtham0992/link` 1.7.0, fixed source tag/commit
  `v1.7.0` / `af37c074a81ea4ab340aa923102b62f1c7857977`, MIT:
  - 106 stars, 718 commits, seven releases at inspection time;
  - Windows Codex installer, Codex `SessionStart` hook, stdio MCP, bounded
    recall, raw/wiki/memory separation, secret scanning, local-only runtime,
    source provenance, lifecycle metadata, and proposal-only session capture;
  - fixed-version Windows evidence collected outside this repository:
    143 focused tests passed, first-use smoke passed, and a fresh disposable
    wiki passed real stdio initialize/prompts/resources/tools/calls;
  - material gaps: one active maintainer; new Codex-hook support; its default
    slim MCP surface still exposes `remember`, `review`, and `admin`; direct
    `remember` trusts the agent's interpretation of user approval; a newly
    written `review_status: pending` memory remains eligible for default
    recall; the upstream installer and runtime do not match DevFrame's
    junction/reparse, TOCTOU, multi-file transaction, or exact rollback gate.
- `basicmachines-co/basic-memory` 0.22.1, AGPL-3.0:
  - 3.5k stars, 1,543 commits, and 87 releases at inspection time;
  - mature local Markdown/Obsidian storage, MCP, project isolation, hybrid
    search, Windows fixes, and rebuildable SQLite index;
  - material gaps: broad read/write MCP surface, no equivalent mandatory
    DevFrame approval boundary, default frontmatter/index behavior that must be
    disabled or isolated for a read plane, automatic-update/telemetry defaults
    that require explicit disabling, and a copyleft integration boundary that
    needs separate licensing review before product adoption.
- `ozankasikci/global-agent-memory` 0.1.6, MIT:
  - nearly exact project-aware/human-review architecture, but only 13 stars,
    six releases, active V1 development, and documented macOS/Linux setup; it
    is reference architecture rather than a Windows MVP dependency.
- Obsidian `Semantic Notes Vault MCP` and `Vault Knowledge Base` were also
  inspected. They strengthen graph/semantic exploration but currently expose a
  broader vault authority or have a much younger operational footprint than
  this bounded memory slice permits.

### Revised decision

- Do not continue the API-key-bearing Local REST activation implementation as
  the default product path. It requires Obsidian to be open, adds plugin/TLS
  lifecycle and a secret, and still does not implement the self-growing wiki
  loop.
- Treat Obsidian as the human-facing IDE for canonical Markdown, not as the
  security authority or mandatory always-running server.
- Use a pinned, independently launched read plane with a Link-compatible
  bounded `status`/`recall` contract. The first acceptance spike may execute
  the fixed Link runtime as a separate process, but Codex must use
  `enabled_tools = ["status", "recall"]`; `remember`, `ingest`, `review`, and
  `admin` are not approved model-facing tools.
- Keep the existing DevFrame `propose_obsidian_memory` plus human approval and
  create-only exactly-once write-back as the only durable write authority.
  Pending candidates must stay outside active recall until approval.
- Prefer a Codex `SessionStart` hook for deterministic bounded recall. Official
  Codex documentation confirms discovery at `~/.codex/hooks.json`, the
  `startup|resume|clear|compact` matcher values, and model-visible plain stdout.
  A managed global `AGENTS.md` block remains useful for policy, but it is not
  the mechanism relied upon to make startup recall happen.
- Preserve a dedicated disposable Vault boundary. The candidate read runtime
  does not yet meet DevFrame's hostile-filesystem TOCTOU/reparse guarantees, so
  a mixed or important private Vault remains outside the approval.

### Revised smallest safe increment

1. Replace the Local REST tracer-bullet expectations with a temporary-home
   activation test that creates a Link-compatible `raw/`, `wiki/`, candidate,
   and approved-memory layout without touching user notes.
2. Provision or select an isolated, exact-version read runtime; never silently
   upgrade it and never expose its write-capable tools.
3. Atomically install reversible managed blocks in Codex MCP config and
   `hooks.json`, preserving unrelated configuration and requiring one explicit
   `--confirm` action.
4. Make the `SessionStart` hook return only a bounded, secret-scanned,
   path-redacted recall capsule. Treat all recalled text as untrusted guidance
   subordinate to current rules, source, tests, evidence, review, and human
   decisions.
5. Route explicit "remember" intent only to the existing DevFrame candidate
   proposal. After owner approval, use the already-tested create-only apply
   path and then rebuild the disposable read index.
6. Prove the full path in temporary Codex/Vault homes, then in the user's empty
   dedicated Vault: startup hook, read-only tool list, task-focused recall,
   proposal, approval, next-session recall, exact deactivation, and no secret
   or absolute-Vault-path disclosure.

The uncommitted Local REST activation module and its first green tracer test
are now classified as an unaccepted spike. They must be replaced or removed
through an exact-path patch after the revised TDD contract exists; they must
not be staged merely because their first test passes.

This receipt governs the follow-up to
`RECON-OBSIDIAN-CODEX-MEMORY-MVP-20260718`. It applies only on the independent
`codex/obsidian-codex-memory-mvp` candidate branch and does not change the
current mainline milestone selected by `docs/status/HANDOFF.md`.

The receipt satisfies `rules/recon.md` recon-001/002/003/005/009/010 and
`rules/open-source-reuse.md`. It replaces the initial assumption that DevFrame
should keep expanding a hand-written Obsidian data plane. Obsidian and a mature
upstream MCP server own live vault access; DevFrame owns only activation,
least-privilege configuration, task-start recall guidance, and its existing
governed proposal boundary.

## Target

- user_goal: After one explicit first-use consent, Codex should start the local
  memory MCP itself and recall the dedicated Obsidian memory note before
  planning, without asking the user for a port, vault path, or allowlist on
  every task. The same server command should remain usable by other
  MCP-compatible AI clients.
- target_repo_or_kb: this independent candidate branch at
  `4e2d47670a77d61a6856f28340d484e3ab5a755e`, the dedicated disposable
  `Obsidian-Codex-Memory` vault, and external upstream source at the fixed
  versions below.
- current_slice_goal: Add a reversible `devframe memory` activation surface
  that launches an upstream stdio MCP through Codex, reads only `memory.md`,
  advertises no write or command tools, and installs a bounded managed recall
  instruction into the user's Codex instruction chain only after an explicit
  confirmation flag.
- requested_outcome: Subsequent Codex tasks need neither a separately running
  DevFrame dashboard nor caller-supplied `relativePaths` for the normal startup
  recall path. Existing proposal approval remains a separate governed tool;
  this slice does not weaken or replace it.
- date: 2026-07-18
- planner_agent_id: root Codex coordinator

## Resource Map

- repository_roots:
  - this public DevFrame candidate worktree;
  - external reference clones outside the public repository, inspected at the
    immutable commits listed under Reuse Candidates;
  - one dedicated disposable Obsidian vault with no user-important notes.
- top_level_tree:
  - `packages/control-plane/control_plane/`: existing CLI, MCP consent/server,
    Obsidian memory adapter, and write-back governance;
  - `packages/control-plane/tests/`: production-path CLI, MCP, and memory tests;
  - `packages/ai-workflow-hub/.../obsidian_rest_api.py`: existing paper-domain
    REST adapter, inspected as prior art but not imported across package
    boundaries;
  - `docs/agent-runtime/`: stable implemented behavior;
  - `docs/status/`: scoped Recon Receipts and the status-document inventory.
- important_dirs:
  - `packages/control-plane/control_plane/cli`
  - `packages/control-plane/control_plane`
  - `packages/control-plane/tests`
  - `docs/agent-runtime`
- docs_read:
  - `AGENTS.md`
  - `docs/status/HANDOFF.md`
  - `rules/recon.md`
  - `rules/open-source-reuse.md`
  - `rules/git.md`
  - `docs/agent-runtime/obsidian-codex-memory.md`
  - `docs/status/recon-receipt-obsidian-codex-memory-mvp.md`
  - current OpenAI Codex MCP and `AGENTS.md` documentation
  - current MCP initialization schema and official SDK server guidance
  - upstream README, manifest, package, license, configuration, path-policy,
    tool-definition, and initialization sources named below.
- packages_apps_modules:
  - Obsidian 1.12.7 desktop: owns the live vault and community-plugin runtime;
  - `obsidian-local-rest-api` 4.1.7: in-process loopback REST and Streamable
    HTTP MCP server;
  - `obsidian-mcp-server` 3.2.9: stdio/HTTP MCP adapter with server
    instructions, read-only mode, and vault-relative path policy;
  - Codex CLI 0.143.0: owns stdio MCP child lifecycle and reads server
    `instructions` plus the global/project `AGENTS.md` instruction chain;
  - existing DevFrame Obsidian memory/write-back modules: retain proposal-only,
    human-approved, create-only write behavior.
- runtime_entrypoints:
  - `devframe memory activate|status|deactivate`;
  - internal `devframe memory serve`, launched by an MCP client over stdio;
  - upstream `npx -y obsidian-mcp-server@3.2.9`;
  - Obsidian Local REST API HTTPS loopback endpoint.
- ui_entrypoints:
  - Obsidian Community Plugins page for the human-controlled upstream plugin
    install/enable step;
  - Codex starts a new task after activation; no persistent dashboard is
    required for read-only recall.
- service_entrypoints:
  - Obsidian owns the loopback service while the dedicated vault is open;
  - Codex owns the stdio child process lifetime.
- state_storage_locations:
  - local activation metadata under `$HOME/.devframe/obsidian-memory/`;
  - Obsidian's own per-vault plugin settings under its `.obsidian/plugins/`
    directory;
  - managed, reversible blocks in `$CODEX_HOME/config.toml` and
    `$CODEX_HOME/AGENTS.md`.
- external_integrations:
  - Obsidian Community Plugins;
  - npm only for the exact upstream package version;
  - Codex MCP configuration;
  - other clients may reuse the same stdio command but are not auto-configured
    by this Codex-first slice.
- notable_generated_or_vendor_paths:
  - no upstream source, npm cache, plugin bundle, token, private vault state, or
    local activation record is committed to the public repository;
  - reference clones stay outside the repository and are not product inputs.
- license_files_found:
  - DevFrame root `LICENSE`;
  - `obsidian-local-rest-api` MIT;
  - `obsidian-mcp-server` Apache-2.0.

## Verified Current Facts

- Obsidian's community registry contains `Local REST API with MCP`. Release
  4.1.7 (2026-07-11) has a built-in authenticated MCP endpoint and comes from
  a repository with 2.7k GitHub stars, 67 releases, and an MIT license.
- Its MCP surface is intentionally broad: it advertises whole-vault listing,
  reading, full-text search, overwrite, append, patch, delete, command
  execution, tags, and active-file operations. Source review found no
  server-level path allowlist or initialize `instructions`; `vault_write`
  explicitly overwrites an existing note without warning. It must not be
  connected directly as the governed memory surface.
- `cyanheads/obsidian-mcp-server` 3.2.9 is Apache-2.0, has 633 GitHub stars,
  268 commits, eight releases, and a tested stdio transport. It returns
  deployment-specific server `instructions`, can hide all write tools with
  `OBSIDIAN_READ_ONLY=true`, disables Obsidian commands by default, and enforces
  exact-or-directory-boundary read prefixes through `OBSIDIAN_READ_PATHS`.
- Its root note listing and tag resource can still reveal vault-relative names
  or tags outside a file allowlist. This slice therefore requires a dedicated
  disposable memory vault and limits the Codex tool surface to
  `obsidian_get_note` and `obsidian_search_notes`. It is not approved for a
  mixed private vault.
- The inspected Windows host has Node.js 24.15.0 and npm/npx 11.12.1, satisfying
  the upstream Node 24 requirement. The dedicated vault is open in Obsidian
  1.12.7 and has no community plugins installed yet.
- Codex 0.143.0 supports stdio MCP child commands, per-server enabled-tool
  lists, read/write approval modes, and server `instructions`. Codex reads
  global `$CODEX_HOME/AGENTS.md` once per run, so a managed block can make the
  startup recall expectation explicit without modifying generated native
  Codex memories.
- The current DevFrame MCP remains healthy on loopback but still requires an
  independently running dashboard, environment variables, fresh session
  authorization, and caller-supplied paths. It is evidence for the proposal
  and governance boundary, not the desired zero-touch read lifecycle.

## Core Concepts

- first-use activation: an explicit, reversible human action that binds one
  dedicated vault and one upstream package version; it is not silent discovery
  of every Obsidian vault.
- zero-touch subsequent use: Codex launches the stdio child and receives recall
  guidance on each new task; Obsidian must still be open because it owns the
  live API.
- startup recall: one bounded read of `memory.md` before planning. Returned
  Markdown remains untrusted guidance and cannot override current source,
  checked-in rules, tests, evidence, reviews, or human decisions.
- governed write: the existing DevFrame candidate-note proposal plus separate
  human approval. The upstream MCP stays read-only in this slice.
- client portability: standard stdio MCP makes the server reusable, but no
  protocol can force every host/model to invoke a tool. Codex receives the
  stronger managed `AGENTS.md` instruction; other hosts must honor MCP server
  instructions or install an equivalent client instruction.

## Core Data Models

- project/workspace: a dedicated vault identity plus the fixed `memory.md`
  allowlist; no mixed-vault auto-discovery.
- thread/session: one MCP stdio child owned by the client.
- message/event: upstream MCP initialize, tools/list, and read-only tool calls.
- tool_call: `obsidian_get_note` for deterministic startup recall and
  `obsidian_search_notes` for task-focused retrieval.
- terminal_run: activation CLI, status CLI, stdio initialize/list/call probe,
  Codex config verification, and a fresh-task behavioral probe.
- diff/checkpoint: managed blocks have unique markers and are removable without
  rewriting unrelated Codex configuration or global instructions.
- review/evidence: upstream version/commit/license, activation state, redacted
  status, exact Git diff, pytest evidence, real Obsidian handshake, and
  independent security review.
- policy/rules: read-only upstream, exact dedicated note, no command tools, no
  token in public/config/AGENTS/audit output, and no automatic plugin install.

## Capability Matrix

- capability_name: Obsidian live vault and built-in MCP
  - location: `coddingtonbear/obsidian-local-rest-api` 4.1.7
  - maturity: mature community plugin and direct Obsidian API integration
  - reusable_as_is: storage, live search, API-key authentication, app-owned
    lifecycle
  - reusable_with_adapter: yes, behind a read-only path-policy MCP
  - not_reusable: direct governed-memory connection because it exposes full
    CRUD and command execution
  - notes: preferred Obsidian data plane; no custom DevFrame RAG is added.
- capability_name: read-only path-policy stdio MCP
  - location: `cyanheads/obsidian-mcp-server` 3.2.9
  - maturity: released, typed, tested, exact version pin available
  - reusable_as_is: stdio framing, tool schemas, search/read operations,
    initialization instructions, upstream error mapping
  - reusable_with_adapter: a thin launcher supplies fixed policy and the plugin
    key without exposing it to Codex configuration
  - not_reusable: unrestricted/default configuration
  - notes: root listing/tag metadata is why the dedicated-vault requirement and
    Codex `enabled_tools` filter are both mandatory.
- capability_name: DevFrame governed proposal and exactly-once create
  - location: existing `obsidian_memory.py`, `writeback.py`, and MCP handler
  - maturity: implemented and independently reviewed
  - reusable_as_is: proposal validation, create-only apply, audit, human gate
  - reusable_with_adapter: later stdio proposal activation, outside this read
    milestone
  - not_reusable: false
- capability_name: Codex-managed MCP lifecycle and startup instructions
  - location: Codex CLI/config and global `AGENTS.md`
  - maturity: implemented on the inspected host and documented by OpenAI
  - reusable_as_is: yes
  - reusable_with_adapter: bounded marked blocks plus verification
  - not_reusable: direct edits without an explicit activation/rollback contract.

## Reuse Candidate List

- candidate: `coddingtonbear/obsidian-local-rest-api` 4.1.7
  - source: <https://github.com/coddingtonbear/obsidian-local-rest-api>
  - inspected_commit: `4b370d84ed46e0ad30c9ef5a912f1a650c9e7eb7`
  - exact_scope_to_reuse: Obsidian plugin lifecycle, authenticated loopback API,
    live note reads and search
  - expected_adapter_work: none in the plugin; install/enable remains human
    controlled
  - blocking_constraints: broad default MCP authority; never connect directly
    as the governed memory server
  - decision: reuse as data plane.
- candidate: `cyanheads/obsidian-mcp-server` 3.2.9
  - source: <https://github.com/cyanheads/obsidian-mcp-server>
  - inspected_commit: `9e9861be17395e942ee7aac3b3607cf9dc4d97b2`
  - exact_scope_to_reuse: stdio transport, server instructions, typed read and
    search tools, upstream client, path policy, read-only tool suppression
  - expected_adapter_work: fixed-version launcher plus activation/config state
  - blocking_constraints: dedicated vault, two-tool Codex allowlist, pinned
    version, local-only upstream, no command/write tools
  - decision: reuse now.
- candidate: Obsidian MCP Connector / Semantic Notes Vault MCP / Vault as MCP
  - source: current Obsidian community registry and upstream repositories
  - exact_scope_to_reuse: later semantic/graph retrieval or all-in-one plugin UX
  - expected_adapter_work: permission-profile and prompt-injection evaluation
  - blocking_constraints: young/high-churn releases or broader default vault
    surfaces; no proven advantage for one startup note
  - decision: defer until retrieval evaluation proves lexical/live search is
    insufficient.
- candidate: custom DevFrame stdio MCP transport or vector database
  - source: proposed alternative
  - exact_scope_to_reuse: none
  - expected_adapter_work: duplicate mature behavior
  - blocking_constraints: recon-005 exception would be required and is not
    justified
  - decision: reject.

## Integration Risk Table

- risk: upstream key or private plugin settings leak into Codex config, logs,
  audit, status, process arguments, or repository
  - type: security/privacy
  - severity: P0
  - mitigation: launcher reads only the API key from the known plugin settings
    file at process start, passes it only through the child environment, and
    never serializes or prints it; tests scan every generated artifact.
  - owner: activation launcher
- risk: direct upstream MCP exposes destructive write/command tools
  - type: security
  - severity: P0
  - mitigation: force `OBSIDIAN_READ_ONLY=true`,
    `OBSIDIAN_ENABLE_COMMANDS=false`, and verify tools/list contains no write,
    delete, append, patch, tag mutation, or command tool.
  - owner: launcher plus real-path test
- risk: whole or mixed private vault metadata escapes the allowlist
  - type: privacy
  - severity: P0
  - mitigation: dedicated disposable vault only, exact `memory.md` read prefix,
    Codex `enabled_tools` restricted to get/search, and no approval for a mixed
    private vault in this slice.
  - owner: activation preflight
- risk: activation corrupts existing global Codex config/instructions
  - type: maintenance/privacy
  - severity: P0
  - mitigation: explicit `--confirm`, unique managed markers, collision checks,
    atomic file replacement, idempotence tests, exact-block deactivation, and
    preservation of all unrelated bytes.
  - owner: activation controller
- risk: model follows prompt injection embedded in `memory.md`
  - type: security/correctness
  - severity: P0
  - mitigation: the managed instruction labels the note untrusted guidance and
    explicitly subordinates it to system/developer instructions, repository
    rules, source, tests, evidence, review, and human decisions.
  - owner: recall instruction
- risk: npm package drift or first-run supply-chain failure
  - type: supply-chain/availability
  - severity: P1
  - mitigation: exact `3.2.9` pin, recorded source commit/license, package
    version check, and failure before any vault call if the resolved package
    identity disagrees. Vendoring remains forbidden.
  - owner: launcher and acceptance probe
- risk: AI host ignores MCP/server or startup instructions
  - type: ux/correctness
  - severity: P1
  - mitigation: Codex receives a tested global managed instruction and a fresh
    task behavioral probe; other clients are reported as compatible but not
    automatically compliant until separately tested.
  - owner: client adapter
- risk: Obsidian is closed when a task starts
  - type: availability/ux
  - severity: P2
  - mitigation: actionable status/error text tells the user to open the
    dedicated vault; no background Windows service is added.
  - owner: activation status

## Build-vs-Buy Decision

- must_reuse:
  - Obsidian's own community plugin lifecycle and live vault API;
  - `obsidian-mcp-server` stdio, instructions, read/search schemas, and path
    policy;
  - Codex MCP child lifecycle and global instruction discovery;
  - existing DevFrame proposal/write-back governance.
- should_adapt:
  - only the first-use activation, secret-free local metadata, least-privilege
    environment, client config, and recall instruction.
- can_spike:
  - semantic retrieval through a mature Obsidian plugin after evaluation
    fixtures show a real recall gap.
- must_build_new:
  - one small activation controller and CLI command family;
  - one stdio process launcher that inherits stdio and injects fixed policy;
  - focused tests and stable runtime documentation.
- must_not_build:
  - MCP framing/server, Obsidian plugin, full-vault scanner, vector/graph store,
    background daemon, custom desktop UI, automatic memory promotion.
- rationale: the mature ecosystem already supplies the data plane and protocol.
  DevFrame's product value is the reversible governance adapter, not another
  Obsidian implementation.

### recon-005 Exception Memo

No exception to hand-write a mature MCP capability is requested. The only new
runtime process is a transparent launcher that inherits stdio from the upstream
server; it does not parse, rewrite, proxy, or implement MCP messages. Custom
code is limited to DevFrame-owned activation, configuration integrity, and
policy injection, which upstream projects and Codex do not jointly provide.

## Unknowns / Questions

- unanswered_items:
  - whether Codex 0.143 applies `enabled_tools` to every plugin-provided resource
    surface as well as tools (the dedicated-vault boundary does not depend on
    this);
  - whether a future upstream release adds exact file/resource filtering that
    removes the dedicated-vault limitation;
  - how often real startup recall is skipped by models despite explicit Codex
    instructions.
- required_verification:
  - plugin install/enable in the dedicated vault after a human confirmation;
  - real HTTPS service and authentication probe without printing the key;
  - stdio initialize, server instructions, tools/list, and `memory.md` read;
  - tools/list negative assertion for every write/command tool;
  - generated Codex config/AGENTS/activation artifacts contain neither the API
    key nor an accidental second server definition;
  - a fresh Codex task attempts startup recall without a user reminder.
- experiments_needed:
  - five fresh low-risk task prompts to measure recall invocation reliability;
  - only then decide whether a server-side no-argument recall tool is needed.

## Recommended Next Slice

- smallest_safe_increment:
  1. add `devframe memory activate|status|deactivate|serve`;
  2. make activation preview-only unless `--confirm` is supplied;
  3. write secret-free activation metadata and reversible managed Codex blocks;
  4. launch only `obsidian-mcp-server@3.2.9` with read-only, command-off,
     `memory.md`-only policy;
  5. verify the production CLI path in temporary homes before touching the real
     Codex home;
  6. after the human plugin-install gate, run the real dedicated-vault path and
     a fresh-task recall probe.
- worker_type_needed:
  - one coding worker, one independent security reviewer, root acceptance
    coordinator. If the root implements because no worker runtime is available,
    review treats the slice as higher risk under recon-004.
- files_or_modules_in_scope:
  - `packages/control-plane/control_plane/obsidian_memory_activation.py`
  - `packages/control-plane/control_plane/cli/_memory.py`
  - `packages/control-plane/control_plane/cli/app.py`
  - `packages/control-plane/control_plane/cli/_usage.py`
  - `packages/control-plane/tests/test_obsidian_memory_activation.py`
  - focused `packages/control-plane/tests/test_cli.py` additions only if the
    production router cannot be covered from the new test module
  - `docs/agent-runtime/obsidian-codex-memory.md`
  - `docs/agent-runtime/capability-inventory.md`
  - `docs/status/status-document-inventory.md`
  - this receipt.
- files_or_modules_out_of_scope:
  - main worktree and `docs/status/HANDOFF.md`;
  - existing MCP consent, write-back, dashboard, and direct filesystem memory
    implementation;
  - automatic community-plugin installation;
  - automatic write or candidate promotion;
  - mixed/private vaults, background services, Windows startup tasks;
  - copied/vendored upstream source or npm artifacts.
- rollback_path:
  - `devframe memory deactivate --confirm` removes only exact managed blocks and
    local activation metadata; it leaves the vault, plugin, user notes, and all
    unrelated Codex config/instructions untouched.
- evidence_required_for_completion:
  - observed RED for missing activation command/behavior;
  - focused activation and production CLI tests;
  - existing Obsidian memory/MCP/write-back regression tests;
  - control-plane regression proportional to the final diff;
  - real fixed-version stdio + dedicated-vault probe;
  - five-task startup-recall behavioral sample or an explicit partial verdict;
  - `scripts/verify-public-snapshot.ps1` and `git diff --check`;
  - independent review of the actual diff with zero unresolved P0/P1.
- review_gate_definition:
  - block if activation can expose the plugin key or absolute vault path, touch
    an unapproved vault, advertise or execute an upstream write/command tool,
    corrupt unrelated global config, silently install a plugin, use an
    unpinned package, or claim that every AI host must obey an advisory MCP
    instruction.

## Approval

The root coordinator approves only the activation slice above. Upstream plugin
installation remains an action-time human gate. Real global Codex activation
requires the explicit production CLI `--confirm` flag and will occur only after
temporary-home tests prove preview, idempotence, redaction, and rollback.

This receipt does not approve a real private vault, a mixed vault, direct use of
the broad Local REST API MCP surface, a new database/index, an Obsidian plugin,
or any push/PR/merge before independent review and root acceptance.
