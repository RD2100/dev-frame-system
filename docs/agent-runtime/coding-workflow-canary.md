# Coding Workflow Canary Contract

Lifecycle state: implemented M10B contract, `coding-workflow-canary.v1`

## Purpose

The coding workflow canary is the first and only execution consumer of the
M10A planned-only `governed-coding-v1` Profile. One explicit CLI opt-in lets
`devframe code` consume exactly two frozen offline methodology stages —
`pre:intent` (`intent-framing-gate`) and `post:evidence`
(`evidence-driven-acceptance`) — without constructing any worker, without
network or credentials, and without adding any review or acceptance authority.

The contract version string is defined once, in
`packages/control-plane/control_plane/methodology_dispatch.py`:

```python
WORKFLOW_CANARY_CONTRACT_VERSION = "coding-workflow-canary.v1"
WORKFLOW_CANARY_MODE = "canary_only"
WORKFLOW_CANARY_SELECTION_SOURCE = "explicit_cli_opt_in"
```

Everything in this document describes implemented, test-covered behavior, not
a target state.

## CLI Surface

The canary is opt-in only. It never activates from goal text, configuration,
or inference. The flag exists only on `devframe code`; `devframe go` does not
expose it, and plain dispatch metadata contains no `workflow_canary` key
(`workflow_canary` is a keyword-only parameter defaulting to `False`).

```powershell
devframe code "@go read <goal>" `
  --project D:\work\project `
  --runtime-dir D:\private\devframe-runtime `
  --workflow-canary
```

All of the following must hold, or the run is rejected before any packet,
metadata, or report side effect exists:

- The goal must resolve to the `@go read` methodology trigger with a
  non-empty remaining goal; the resolved methodology must be
  `read_only: true`, `network_enabled: false`.
- Exactly one agent (`--agents 1`, the default), no `--target` entries.
- Default worker profile, no `--command`, no `--model`, no
  `--model-provider`, default `--opencode-agent`, `--driver command`
  (no ACP), no `--isolate`, no rdinit application.
- A project-scope skill policy must exist at
  `<runtime>/<project-id>/skills.json`, parse as `{"version": 1, "skills":
  [...]}` with at least one valid skill and no duplicate skill ids.
- The effective project policy must force the resolved coding Profile to
  read-only and offline (for example one project skill record with
  `readOnly: true`, `networkEnabled: false`). The resolved Profile must be
  `governed-coding-v1`, `work_type: coding`, `resolution_status: selected`,
  `execution_state: planned_only`.

Rejection path: any deviation raises `WorkflowCanaryError` (a `ValueError`).
At prepare time the CLI prints `ERROR: workflow canary ...` to stderr and
exits `2`, and `<runtime>/rdgoal-outbox`, `<runtime>/go-runs`, and
`<runtime>/rdgoal-reports` are never created. At resume time a rejected run
exits `1` with the run metadata byte-identical to before the attempt.

`--preview` renders the canary plan (`workflow : canary_only`, stages
`pre:intent` and `post:evidence`, `worker : none`) and provably never
constructs a worker command. Without `--execute` the run is prepared and
resumable; with `--execute`, or later via
`devframe code execute <go-run-id>`, the two stages are consumed.

## Contract Fields

A canary run records one `workflow_canary` marker inside its
`go-runs/<go-run-id>/go-run.json` metadata:

| Field | Recorded value |
|---|---|
| `contract_version` | `coding-workflow-canary.v1` |
| `mode` | `canary_only` |
| `selection_source` | `explicit_cli_opt_in` |
| `policy_binding` | `resolved_path` and `sha256:<hash>` of the exact project `skills.json` bytes |
| `profile_binding` | `profile_id` (`governed-coding-v1`) and the resolved Profile's `profile_fingerprint` |
| `stage_bindings` | Two entries: `{phase, stage_id, skill_id, source_path, skill_fingerprint}` for `pre:intent:intent-framing-gate` and `post:evidence:evidence-driven-acceptance` |
| `binding_fingerprint` | `sha256:` of the canonical JSON (sorted keys, compact separators, ASCII) of the six binding keys above |
| `status` | `prepared` after prepare; `passed` after execution |
| `stage_results` | `[]` while `prepared`; exactly the two frozen passed entries when `passed` |

The marker's key set is closed: any missing, extra, or renamed key is
malformed and fails.

### Fingerprint and hash binding semantics

- Project policy: the `skills.json` bytes are read and validated before
  Profile resolution and read again after stage binding. If the two reads
  differ in path or bytes, preparation fails ("policy drifted during
  resolution"). The recorded `sha256` binds those exact bytes.
- Profile: `profile_fingerprint` is the SHA-256 of the canonical JSON of the
  whole resolved Profile, so any Profile field change (versions, stages,
  permissions, constraints) changes the fingerprint.
- Skill sources: each bound stage records the `SKILL.md` source path and its
  `sha256:` content fingerprint. The binding step re-reads the file from disk
  and re-hashes it; a mismatch against the Profile's recorded stage
  fingerprint fails ("skill fingerprint drifted"). Stages must be
  `availability: registered`, `human_gate: none`, and offline read-only
  (`read: true`, `write/network/credentials: false`).
- Binding: `binding_fingerprint` covers all six immutable binding keys, so no
  individual binding can be swapped without detection.

## Resume Revalidation

`devframe code execute` on a canary run does not trust stored metadata. It
re-runs the full preparation from current disk state and compares:

- The top-level metadata envelope must contain exactly the known result keys.
  Any extra key fails, including a forged internal
  `_workflow_canary_envelope_validated` marker (which is never serialized to
  the public metadata or status output).
- Authority fields are forbidden at the top level: `final_ready`,
  `root_accepted`, and `FinalVerdict` are rejected under case- and
  punctuation-insensitive key normalization.
- Deleting or downgrading the `workflow_canary` marker (to `null`, `false`,
  or `{}`) fails: a metadata shape that looks like a canary run (single
  shard 1/1 agent, empty targets, empty worker command, `governed-coding-v1`
  profile, `@go read` methodology) is still treated as one and refused
  without a valid marker.
- All immutable binding keys plus `binding_fingerprint` must equal a freshly
  recomputed binding — which re-reads the policy bytes, re-resolves the
  Profile, and re-hashes every skill source from disk.
- The TaskSpec's `workflow_profile` must equal the freshly resolved Profile;
  `work_type` must be `coding`; a `skill_usage` field is rejected.
- The dispatch packet must match the prepared run (project id, packet id and
  directory, empty targets, the exact sharded requirement, TaskSpec
  equality), and both packet and report paths must stay inside the runtime
  directory.
- `status` must be `prepared` (with empty `stage_results`) or `passed` (with
  exactly the frozen passed stage results).

## Fail-Closed Behavior

Every failure below raises `WorkflowCanaryError` with zero side effects — no
packet, no report, no metadata mutation — except where noted:

- Missing, unreadable, or malformed project skill policy; invalid structure;
  invalid or duplicate skill entries.
- Resolved Profile that is not the offline read-only `governed-coding-v1`
  planned-only Profile.
- Stage binding unavailable, requiring a human gate, or not offline
  read-only; skill source missing, unreadable, or fingerprint-drifted.
- Policy byte drift between the double reads of preparation.
- Any non-canary execution option (shards, targets, worker or model
  overrides, ACP, isolation, rdinit).
- A goal that does not resolve to `@go read`.
- Resume-time drift of policy bytes, Profile fingerprint, skill source path
  or bytes; authority field injection; forged, deleted, or downgraded
  markers.
- Packet path outside its runtime, packet drift from the prepared run, a
  symlinked report path, or a packet already containing an authoritative
  review artifact (`review.json`, `review.yaml`, `review.md`,
  `FINAL_VERDICT.json`).
- A draft report that does not ingest as `passed`. This one guard fires after
  the draft `ExecutionReport.md` and its execution summary are already on
  disk; the run metadata still stays unchanged. The branch is unreachable for
  the fixed draft report, whose `Review Status: draft` never matches a
  positive acceptance value.

Regression tests assert the read-only failure contract directly: after a
rejected resume, `go-run.json` is byte-identical, no `ExecutionReport.md`
exists in the packet, and `<runtime>/rdgoal-reports` was never created.

## Permission Boundary

- No worker, no subprocess, no ACP: the canary path never calls
  `build_go_worker_command`, never constructs a `CommandWorker`, and never
  opens an ACP session; the agent's `worker_command` is `[]`.
- No network, no credentials: every bound stage permission is pinned to
  `read: true`, `write: false`, `network: false`, `credentials: false`, and
  the Profile constraints are read-only and offline.
- Draft evidence only: execution writes exactly one artifact,
  `ExecutionReport.md` in the packet directory, with `Status: pass` and
  `Review Status: draft`. It is ingested through the ordinary
  execution-report path into
  `<runtime>/rdgoal-reports/<project-id>/<packet-id>/execution-summary.json`
  and remains review-pending. It produces no review artifact, no
  `FinalVerdict`, and no acceptance state, and the ingestion guard blocks any
  report that claims review or final acceptance without canonical acceptance
  artifacts.

## Non-Goals

- Not a Skill execution engine: only the two frozen stages are consumed. The
  `implementation` (tdd) and `review` (review-governance-kernel) stages of
  `governed-coding-v1` are not executed, and the paper Profile is untouched.
- Not an acceptance channel: canary output can never set `final_ready`,
  `root_accepted`, or `FinalVerdict`; those fields are actively rejected.
- Not a default: nothing enables the canary except the explicit
  `--workflow-canary` flag on `devframe code`.
- No hooks, no global installation, no non-coding activation, no automatic
  adoption of external skills.

## Functional Map

| Need | File or surface | Role |
|---|---|---|
| Contract constants and binding | `packages/control-plane/control_plane/methodology_dispatch.py` | `prepare_workflow_canary_binding`, `verify_workflow_canary_binding`, `WorkflowCanaryError` |
| Opt-in gating and run lifecycle | `packages/control-plane/control_plane/go_dispatch.py` | `_resolve_workflow_canary_context`, `_execute_workflow_canary`, metadata envelope validation |
| Stage consumption and draft report | `packages/control-plane/control_plane/stage_executor.py` | `execute_coding_workflow_canary` writes the draft `ExecutionReport.md` |
| CLI flag, preview, and exit codes | `packages/control-plane/control_plane/cli/_coding.py` | `devframe code --workflow-canary`, preview, status, execute rendering |
| Prove behavior | `packages/control-plane/tests/test_workflow_profiles.py` and `packages/control-plane/tests/test_cli.py` | Worker-boundary bypass, fail-closed, immutable binding, resume drift, and CLI evidence tests |
