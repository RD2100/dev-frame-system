# Recon Receipt: Canonical Diff Byte Attestation

Receipt ID: `DF-CANONICAL-DIFF-BYTE-SAFE-P1`

Lifecycle state: Approved Recon Receipt. Project coordinator `/root` approved
this receipt on 2026-07-22 for the exact-seven next slice defined below. The
approval grants no authority outside that slice.

Reader: the coder and independent reviewer implementing canonical diff
attestation for generic `devframe go` / `devframe code` evidence preparation.

Post-read action: reference this receipt from the TaskSpec, implement only the
exact-seven write set, and prove all `CD-01` through `CD-14` outcomes before
requesting root acceptance.

## Target

- user_goal: Bind the exact bytes reviewed as `diff.patch` to their Git source,
  repository state, task path set, and final-file bytes without implementing a
  second diff engine.
- target_repo_or_kb: public `dev-frame-system` snapshot at committed HEAD
  `d5674d04222317c8733355d59ccfb2e2dfb92922`.
- current_slice_goal: authorize the smallest safe implementation of raw Git
  diff capture, attestation, replay, and finalization-time validation.
- requested_outcome: byte-stable prepare evidence that fails closed on source,
  artifact, index, path-set, or raw-file drift while preserving explicitly
  scoped legacy behavior.
- date: 2026-07-22
- planner_agent_id: `/root/finalization_retry_writer_sol`

## Resource Map

- repository_roots: `<repo-root>`.
- top_level_tree: `.github/`, `docs/`, `packages/`, `rules/`, `schemas/`,
  `scripts/`, `templates/`, `tests/`, `tools/`, `AGENTS.md`, `LICENSE`, root
  READMEs, and `pytest.ini`.
- important_dirs:
  - `packages/control-plane/control_plane/cli/` - generic code/go prepare and
    finalize orchestration.
  - `packages/control-plane/control_plane/` - deterministic evidence gate.
  - `packages/control-plane/tests/` and `tests/` - unit, CLI real-path, public
    snapshot, and subprocess-finalizer coverage.
  - `schemas/agent-runtime/` - canonical chain-evidence schema.
  - `packages/test-frame/schemas/agent-runtime/` - mandatory semantic mirror.
  - `tools/` - existing `go_evidence.py` finalizer.
  - `docs/status/` - execution root, Recon Receipts, and evidence records.
- docs_read:
  - `AGENTS.md`, `rules/recon.md`, `rules/open-source-reuse.md`, and
    `rules/git.md`.
  - `docs/status/HANDOFF.md`.
  - existing runtime-governance, team-runtime, and CLI-decomposition Recon
    Receipts.
  - Batch E chain-schema compatibility, Batch G opt-in finalization, and Batch
    I generic prepare-evidence records.
  - coordinator-supplied zero-write edge Recon findings `CD-01` through
    `CD-14`; those findings had no durable source file and are normalized here.
- examples_read:
  - evidence fixtures in
    `packages/control-plane/tests/test_evidence_gate.py`.
  - generic prepare/finalize real paths in
    `packages/control-plane/tests/test_cli.py`.
  - finalizer and retry fixtures in `tests/test_go_evidence.py`.
- packages_apps_modules:
  - `packages/control-plane/control_plane/cli/_coding.py`.
  - `packages/control-plane/control_plane/evidence_gate.py`.
  - `schemas/agent-runtime/chain-evidence.schema.json` and
    `packages/test-frame/schemas/agent-runtime/chain-evidence.schema.json`.
  - `tools/go_evidence.py`.
  - rejected text-oriented comparison candidate
    `packages/ai-workflow-hub/src/ai_workflow_hub/git_utils.py`.
- runtime_entrypoints:
  - `devframe go execute ... --prepare-evidence-dir <dir>`.
  - `devframe code execute ... --prepare-evidence-dir <dir>`.
  - explicit `--evidence-dir <dir> --auto-finalize`.
  - `tools/go_evidence.py finalize <evidence-dir>`.
- ui_entrypoints: none in scope; dashboard and visual state remain projections.
- service_entrypoints: none in scope; this is a local CLI/Git/evidence-gate
  path.
- state_storage_locations:
  - operator-selected evidence directory.
  - configured go/atgo runtime directories and TeamRuntime journal.
  - no evidence pack or temporary index belongs in the public repository.
- external_integrations:
  - Git CLI for repository semantics and raw diff bytes.
  - Python standard-library `subprocess`, `tempfile`, and `hashlib`.
  - existing JSON Schema and YAML validators.
- notable_generated_or_vendor_paths:
  - isolated index and capture files must live in an auto-cleaned temporary
    directory outside the worktree.
  - `.codegraph/`, `.pytest_cache/`, `.ruff_cache/`, runtime journals, evidence
    packs, and build outputs remain generated and uncommitted.
  - no external source, dependency, or vendored diff implementation is added.
- license_files_found: root `LICENSE`; no new license obligation.

## Core Concepts

- concepts:
  - three raw Git streams: working, cached, and combined.
  - exact `diff.patch` bytes, explicit empty-stream digest, ordered path scope,
    raw final-file digest, source replay, and real-index immutability.
- domain_terms:
  - `diff_attestation`, `working`, `cached`, `combined`, `file_state`,
    `source`, `index_guard`, and `legacy_unattested_diff`.
- architecture_style: thin adapter over Git and the existing evidence gate;
  Git remains the only diff engine.
- execution_model:
  - capture raw stdout with no text decoding.
  - use the real index only for read-only working/cached observations.
  - use an isolated temporary index for a combined HEAD-to-final-worktree diff
    that includes new paths.
  - repeat capture for stability, atomically publish `diff.patch`, and replay at
    finalization.
- session_model: existing `go_run_id`, project root, ordered task paths, runtime
  root, and evidence directory remain authoritative.
- review_model: independent reviewer and governance FinalVerdict boundaries do
  not change; an executor cannot create acceptance authority.
- evidence_model: names and schema shape are insufficient. Passing evidence
  binds stream bytes, artifact bytes, source metadata, ordered path scope,
  final-file bytes, and real-index state.

## Core Data Models

- project/workspace:
  - resolved repository identity/root, exact base commit, Git version, and real
    index path resolved through Git.
- thread/session:
  - current go run identity; no new session object.
- message/event:
  - existing TeamRuntime review and FinalVerdict references remain unchanged.
- tool_call:
  - shell-free Git argv arrays, raw stdin/stdout, return code, and bounded
    diagnostic stderr.
- terminal_run:
  - two stable captures plus cleanup and index-integrity outcome.
- diff/checkpoint:
  - optional closed `diff_attestation` schema object containing:
    - profile/version, algorithm, base commit, Git version, capture time, and
      ordered target paths.
    - exact argv, SHA-256, and byte length for working, cached, and combined
      streams; empty streams use the SHA-256 of zero bytes rather than a null
      sentinel.
    - `diff.patch` SHA-256 and byte length; its bytes are exactly the combined
      stream.
    - per-path Git classification/status and raw final-file SHA-256 or an
      explicit absent/deleted state.
    - isolated-index strategy and matching real-index SHA-256 before/after.
- review/evidence:
  - canonical and mirrored chain-evidence schemas, EvidenceGate, current
    manifest/FinalVerdict builders, and delegated `go_evidence.py finalize`.
- policy/rules:
  - `recon-001` through `recon-010`, especially durable receipt and HEAD-gap
    rules.
  - `reuse-000` through `reuse-005`.
  - `agent-discipline-001`, `agent-discipline-004` through `006`,
    `agent-discipline-010`, `agent-discipline-012`, and `git-006`.

### Canonical Git profile

- working stream: raw `git diff` against the real index.
- cached stream: raw `git diff --cached HEAD` against the real index.
- combined stream: raw `git diff HEAD` under the isolated index; its bytes are
  published unchanged as `diff.patch`.
- all diff argv use `--binary`, `--full-index`, `--no-color`,
  `--no-ext-diff`, `--no-textconv`, `--no-renames`,
  `--diff-algorithm=myers`, `--no-indent-heuristic`, `--unified=3`,
  `--inter-hunk-context=0`, and explicit `a/` and `b/` prefixes. The combined
  command also uses `--ita-visible-in-index`.
- initialize the isolated index with `git read-tree HEAD`. Discover new paths
  through NUL-delimited `git ls-files --others --exclude-standard -z` plus
  cached additions from `git diff --cached --no-renames --name-only
  --diff-filter=A -z HEAD`. Feed the exact, ordered path records through
  `git --literal-pathspecs add --intent-to-add -f --pathspec-from-file=-
  --pathspec-file-nul`; deduplicate and sort new-path records by raw path bytes,
  never by locale-aware text order.
- invoke Git without a shell and record the complete argv and ordered target
  list. Any fallback that changes this profile requires a revised receipt.

## Committed HEAD Gap

- `_prepare_evidence_only` writes chain evidence and a draft manifest but does
  not create or attest `diff.patch`.
- `evaluate_evidence_dir` requires the filename and review reference but does
  not read or hash its bytes.
- the chain schema has no stream, artifact, source, path-set, or final-file
  attestation fields.
- existing tests create empty or text `diff.patch` fixtures and do not prove
  byte identity.
- `go_evidence.py finalize` already delegates to EvidenceGate, so finalization
  can be enforced without changing that tool unless a new RED disproves the
  delegation boundary.
- `HANDOFF.md` closed M2 and requires a new lifecycle gap plus a real-path RED
  before reopening production code. The zero-write edge matrix below supplies
  that bounded gap evidence; the inspected baseline was clean.

## Edge Matrix

The following outcomes were observed by zero-write probes at the inspected
HEAD in auto-cleaned temporary repositories. They are mandatory acceptance
cases for the next slice, not claims about current production behavior.

| ID | Required outcome |
|---|---|
| `CD-01` | Stable working, cached, and combined streams pass for mixed staged/unstaged state. |
| `CD-02` | Working-stream drift blocks. |
| `CD-03` | Cached-only drift blocks even when the combined stream is stable. |
| `CD-04` | Combined output includes tracked and untracked changes, repeats byte-identically, and leaves the real index unchanged. |
| `CD-05` | New-path bytes, classification, or status drift blocks. |
| `CD-06` | Task path set and artifact-source mismatch blocks through replay. |
| `CD-07` | Empty working plus non-empty cached is valid with an explicit empty digest. |
| `CD-08` | Non-empty working plus empty cached is valid with an explicit empty digest. |
| `CD-09` | Raw final-file SHA drift blocks even when Git diff bytes remain stable. |
| `CD-10` | Artifact truncation, newline transformation, argv drift, or path-order drift blocks. |
| `CD-11` | Source metadata, repository-root, or target-set drift blocks. |
| `CD-12` | Legacy `prepare_evidence` without attestation requires re-prepare; non-prepare legacy behavior remains compatible. |
| `CD-13` | Temporary index/capture state is cleaned on success and error, and the real index remains byte-identical. |
| `CD-14` | Canonical and test-frame chain schemas remain semantically equal. |

## Capability Matrix

- capability_name: Git CLI raw bytes
  - location: installed Git invoked by the control-plane CLI.
  - maturity: mature authority for tracked, staged, binary, path, and index
    semantics.
  - reusable_as_is: diff and index plumbing.
  - reusable_with_adapter: isolated index, raw streaming, hashing, replay, and
    cleanup.
  - not_reusable: decoded stdout or shell-rendered patches.
  - notes: no custom diff parser or renderer is needed.
- capability_name: current EvidenceGate
  - location: `packages/control-plane/control_plane/evidence_gate.py`.
  - maturity: tested fail-closed schema, reviewer, input, verdict, and P0/P1
    gate.
  - reusable_as_is: all existing authority checks.
  - reusable_with_adapter: attestation schema validation and source/artifact
    replay.
  - not_reusable: filename presence as content integrity.
  - notes: finalizer delegation is already correct.
- capability_name: chain-evidence schema
  - location: canonical schema and test-frame semantic mirror.
  - maturity: public contract with an enforced mirror test.
  - reusable_as_is: current run, role, methodology, file, and timestamp fields.
  - reusable_with_adapter: one optional, closed attestation object with a
    prepare-mode enforcement rule.
  - not_reusable: root-only edits or free-form metadata.
  - notes: both schema paths are the same blob at inspected HEAD.
- capability_name: CLI prepare/finalize
  - location: `packages/control-plane/control_plane/cli/_coding.py` and
    delegated finalizer.
  - maturity: tested generic prepare-only and opt-in finalization paths.
  - reusable_as_is: project/run discovery, evidence directory, and guidance.
  - reusable_with_adapter: canonical capture during generic post-execution
    prepare and replay during gate evaluation.
  - not_reusable: pre-execution `atgo` preparation as a post-change diff source.
  - notes: no new CLI or runtime authority.
- capability_name: PowerShell/JavaScript/text pipelines
  - location: local bootstrap writers, embedded Node runner, and
    ai-workflow-hub text diff helpers.
  - maturity: suitable only for their present scoped purposes.
  - reusable_as_is: none for canonical evidence bytes.
  - reusable_with_adapter: they may pass paths or display neutral metadata.
  - not_reusable: string decoding, newline normalization, BOM insertion,
    replacement characters, trimming, or text writes.
  - notes: even byte-capable Node code belongs to another runtime boundary and
    adds no value over the existing Python/Git path.

## Reuse Candidate List

- candidate: Git CLI plus Python standard library
  - source: installed Git and `subprocess`/`tempfile`/`hashlib`.
  - exact_scope_to_reuse: raw stream generation, isolated index operations,
    temporary lifecycle, and streaming SHA-256.
  - expected_adapter_work: a small private capture/replay helper and closed
    metadata construction.
  - blocking_constraints: unsupported Git options, unborn HEAD, submodule, or
    sparse-checkout ambiguity must fail closed.
  - decision: must_reuse.
- candidate: existing schemas, mirror gate, EvidenceGate, and finalizer
  - source: in-repo.
  - exact_scope_to_reuse: contract validation, independent-review checks,
    final verdict, and subprocess entrypoint.
  - expected_adapter_work: add the attestation contract and conditional gate.
  - blocking_constraints: root/mirror equality and legacy policy.
  - decision: should_adapt.
- candidate: ai-workflow-hub or shell text diff path
  - source: in-repo and local shells.
  - exact_scope_to_reuse: none.
  - expected_adapter_work: not applicable.
  - blocking_constraints: text conversion and a separate domain/runtime
    boundary.
  - decision: reject.
- candidate: custom diff engine or per-file patch concatenation
  - source: new code.
  - exact_scope_to_reuse: none.
  - expected_adapter_work: prohibited.
  - blocking_constraints: duplicates Git and creates binary/path/order risk.
  - decision: reject; no exception memo authorizes it.

## Integration Risk Table

- risk: workspace or index changes between capture, review, and finalization.
  - type: security
  - severity: high
  - mitigation: repeat all three streams, attest real index, raw files and
    source metadata, then replay before gate pass.
  - owner: coder and independent reviewer.
- risk: mixed staged/unstaged/new paths are omitted or double counted.
  - type: coupling
  - severity: high
  - mitigation: separate working/cached attestations plus a Git-native isolated
    index for the combined final-worktree artifact.
  - owner: CLI worker.
- risk: text handling mutates bytes without changing apparent content.
  - type: security
  - severity: high
  - mitigation: raw subprocess/file APIs only; hash and length every stream and
    published artifact.
  - owner: CLI and gate workers.
- risk: task scope and captured source diverge.
  - type: security
  - severity: high
  - mitigation: ordered target set in the attestation and exact replay under
    the recorded root/base/argv.
  - owner: gate worker.
- risk: temporary index touches the real index or leaks after an error.
  - type: security
  - severity: high
  - mitigation: temporary index outside the worktree, scoped child environment,
    `finally` cleanup, and before/after real-index byte hashes.
  - owner: CLI worker.
- risk: schema mirror drifts.
  - type: maintenance
  - severity: high
  - mitigation: exact-seven includes both copies and the existing semantic
    mirror/public-snapshot gate.
  - owner: schema worker and reviewer.
- risk: compatibility bypasses the new guarantee.
  - type: maintenance
  - severity: medium
  - mitigation: `prepare_evidence` without attestation blocks and requests
    re-prepare; non-prepare legacy records keep current behavior but cannot
    claim byte attestation.
  - owner: gate worker.
- risk: large binary diffs exhaust memory.
  - type: performance
  - severity: medium
  - mitigation: stream to temporary binary files while hashing.
  - owner: CLI worker.

## Build-vs-Buy Decision

- must_reuse:
  - Git diff/index plumbing and raw stdout.
  - Python standard-library hashing and temporary-file primitives.
  - existing chain schema, mirror contract, EvidenceGate, and finalizer.
- should_adapt:
  - generic `go/code execute --prepare-evidence-dir`.
  - EvidenceGate with conditional prepare-mode attestation and replay.
- can_spike:
  - unsupported Git versions, unborn HEAD, submodules, and sparse checkout only
    in isolated follow-up probes.
- must_build_new:
  - minimal private capture/replay helpers, the closed schema object, and the
    `CD-01` through `CD-14` automated tests.
- rationale: Git already provides the mature diff behavior. DevFrame owns only
  evidence provenance and governance enforcement, so this is adaptation rather
  than a new diff or review-gate subsystem.

## Team Object Mapping

- Agent Registry: one named coder, one independent reviewer, and `/root` as the
  only root-acceptance authority.
- Task Board: work item `DF-CANONICAL-DIFF-BYTE-SAFE-P1` with the frozen
  exact-seven write set.
- Message Bus: the coder TaskSpec and reviewer report must reference this
  receipt; transient chat is not evidence.
- Event Log: existing TeamRuntime records remain downstream and unchanged.
- Evidence Store: the selected evidence directory holds the patch,
  attestation, tests, safety report, and independent review.
- Blackboard/shared memory: not changed by this slice.
- Review Gate: existing EvidenceGate plus canonical replay validation.
- Conflict Control: exact path ownership, isolated temporary index, real-index
  byte guard, and root-only staging/commit lifecycle.

## Unknowns / Questions

- unanswered_items:
  - minimum supported Git version for NUL pathspec input and
    intent-to-add visibility.
  - fail-closed wording for unborn HEAD, submodule dirtiness, and sparse
    checkout.
  - whether a later profile should sign reviewer input hashes; coordinated
    signer/identity protection is outside this slice.
  - whether non-prepare legacy records should eventually migrate to mandatory
    attestation.
- required_verification:
  - automate every edge-matrix case and exercise the actual CLI-to-finalizer
    path.
  - confirm exact artifact bytes, ordered targets, raw file hashes, cleanup,
    and real-index immutability.
  - run schema mirror and public snapshot gates.
- experiments_needed:
  - supported-Git capability failure probe.
  - isolated submodule/sparse/unborn probes before expanding support.

## Recommended Next Slice

- smallest_safe_increment:
  1. Add real-path REDs for byte replacement, stream/source drift, final-file
     drift, missing prepare attestation, and real-index mutation.
  2. Capture stable working and cached raw streams from the real index.
  3. Build the combined stream with an isolated index initialized from HEAD and
     exact NUL-delimited new-path intent-to-add entries; publish it unchanged as
     `diff.patch`.
  4. Record the closed attestation and mirror its schema exactly.
  5. Replay and fail closed in EvidenceGate while retaining the delegated
     finalizer.
  6. Prove `CD-01` through `CD-14`, focused regressions, and public-snapshot
     safety.
- worker_type_needed:
  - one coder restricted to exact seven paths.
  - one independent reviewer.
  - root coordinator alone may accept, stage, and create a local commit under
    `git-006`.
- files_or_modules_in_scope:
  1. `packages/control-plane/control_plane/cli/_coding.py`
  2. `packages/control-plane/control_plane/evidence_gate.py`
  3. `schemas/agent-runtime/chain-evidence.schema.json`
  4. `packages/test-frame/schemas/agent-runtime/chain-evidence.schema.json`
  5. `packages/control-plane/tests/test_evidence_gate.py`
  6. `packages/control-plane/tests/test_cli.py`
  7. `tests/test_go_evidence.py`
- files_or_modules_out_of_scope:
  - `tools/go_evidence.py` unless a concrete RED proves gate delegation cannot
    enforce finalization.
  - review schema, TeamRuntime, RunIndex, dashboard, `atgo`, ai-workflow-hub,
    shell/JavaScript capture, dependencies, or a new helper module.
  - staging, commit, push, PR, release, and deployment by the coder.
- evidence_required_for_completion:
  - automated `CD-01` through `CD-14` with at least one real CLI/finalizer path.
  - affected CLI, gate, and `go_evidence` regression tests.
  - `test_agent_runtime_chain_evidence_schema_mirror_matches_semantically`.
  - `scripts/verify-public-snapshot.ps1 -FailOnTrackedForbidden`.
  - `git diff --check`, exact-path diff reconciliation, and independent review
    with P0/P1 equal to zero.
- review_gate_definition:
  - PASS only when all three Git streams, `diff.patch`, source metadata,
    ordered target set, classifications, raw final-file states, cleanup, and
    real-index bytes match their attestations and replay.
  - PASS only when prepare-mode legacy evidence fails with re-prepare guidance,
    non-prepare compatibility is explicit, and both schemas remain equal.
  - PASS only when no text pipeline or custom diff implementation enters the
    canonical path.

The prior exact-six omitted the test-frame chain-schema mirror. Current HEAD
stores the canonical and mirror schemas as the same blob, and the public
snapshot test requires semantic equality. Adding that mirror is the only
evidence-backed expansion from exact six to exact seven.

## Stop Lines

- The coder TaskSpec must reference this durable receipt before dispatch.
- No write outside exact seven without a revised approved receipt.
- No custom diff engine, per-file patch concatenation, or text-mode capture.
- No mutation of the real Git index and no leaked temporary index on error.
- No final-ready prepare evidence with a missing or mismatched attestation.
- No claim that non-prepare legacy evidence is byte-attested.
- No root-only schema edit; the semantic mirror is part of the same slice.
- Coding workers must not stage, commit, push, or set `root_accepted`.

## Reviewer Index

| Item | Evidence |
|---|---|
| Changed file for this receipt slice | `docs/status/recon-receipt-canonical-diff-attestation.md` only |
| Critical implementation paths | generic prepare, EvidenceGate replay, canonical/mirrored chain schemas, delegated finalizer |
| Current-gap evidence | committed prepare omits the patch; gate checks name/review reference but not bytes; schema has no attestation |
| Edge evidence | zero-write `CD-01` through `CD-14` probes at clean HEAD `d5674d0`; temporary repositories auto-cleaned; no durable source file existed before this receipt |
| Generated artifacts | none retained in the public repository |
| Known gaps | Git-version floor, unborn/submodule/sparse behavior, future signing, eventual non-prepare migration |
| Suggested review focus | three-stream stability, combined new-path fidelity, raw final-file SHA, replay scope, temp-index isolation, legacy rule, schema mirror |
| Approved next action | reference this receipt and dispatch only the exact-seven implementation slice |
