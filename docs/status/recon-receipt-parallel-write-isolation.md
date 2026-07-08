# Recon Receipt: parallel write isolation (P0-2)

> Governs write-capable work that makes concurrent `/go` execution safe, per
> `rules/recon.md` recon-001/005/008 and
> `docs/agent-runtime/reuse-depth-review-method.md`. Closes the risk recorded in
> `docs/status/recon-receipt-local-agent-client-mainline.md` ("OpenCode workers
> edit overlapping files") and the `database is locked` failure noted in
> `docs/status/devframe-code-opencode-handoff.md`.

## Target
- user_goal: Make parallel coding-agent execution safe instead of relying on
  retries and luck.
- current_slice_goal: Serialize agents whose write sets (targets) overlap, while
  keeping non-overlapping agents parallel. Executor-agnostic.
- requested_outcome: No two concurrently running workers can write the same
  target; keep all tests green; verifiable hermetically without spending tokens.
- date: 2026-06-26
- planner_agent_id: kiro
- approval: Human owner authorized the P0 reuse-depth plan and full automation.

## Design principle (from OpenCode's philosophical position)
OpenCode is a replaceable "hand", not the product identity. Isolation therefore
splits into two layers, and only the first is in scope here:

- **Generic isolation (executor-agnostic):** write-set serialization and (later)
  worktree working-directory isolation. Any executor that writes the same file
  concurrently corrupts state, so this belongs in the dispatch layer and must
  not reference OpenCode.
- **Executor-specific isolation (deferred):** OpenCode's sqlite
  `database is locked` is an OpenCode-internal lock. Its fix (per-worktree
  `OPENCODE_HOME`/state dir) must stay inside the OpenCode adapter boundary and
  must not leak into generic dispatch logic.

## Resource Map
- `control_plane/go_dispatch.py`: `_execute_parallel` runs all agents in one
  ThreadPoolExecutor with no overlap analysis; `_run_one_agent` -> `CommandWorker`.
- `control_plane/coding_dispatch.py`: target resolution / shard sizing only; no
  conflict control.
- agents carry `targets: list[str]` (shard file/dir paths) on `GoAgentDispatch`.

## Capability Matrix
- parallel write isolation
  - current production level: L1 (full parallel, no isolation; relies on retry).
  - target level: L2 (write-set serialization in the dispatch layer).
  - gap: no overlap analysis exists; overlapping shards race.

## Build-vs-Buy Decision
- must_reuse: stdlib only (`concurrent.futures`, set algebra). No new dependency.
- should_adapt: group agents by write-set overlap; run groups in parallel,
  agents within a group serially.
- must_build_new: a pure, executor-agnostic `plan_write_set_groups` function and
  the grouped scheduler in `_execute_parallel`.
- rationale: file-level write conflict is universal; the fix is a scheduling
  policy, not an OpenCode feature.

## Overlap semantics
- Two agents conflict if their normalized target sets intersect.
- An agent with no targets (project-scope) is treated as writing the whole repo:
  it conflicts with every other agent.
- Conflict is transitive: a~b and b~c put a, b, c in one serial group
  (union-find).
- Groups run in parallel with each other; agents inside a group run serially in
  shard order.

## Integration Risk Table
- risk: changing the scheduler regresses existing parallel-execution tests.
  - type: correctness | severity: medium
  - mitigation: results per agent are unchanged; only ordering changes.
    Non-overlapping shards (the common test case) still run fully parallel. Full
    pytest is the gate.
- risk: project-scope (empty-target) agents serialize everything.
  - type: performance | severity: low
  - mitigation: intended and safe; preview/dispatch already encourage explicit
    targets. Documented as the conservative default.

## Recommended Slice (this receipt unlocks)
1. New `control_plane/execution_plan.py`: pure `plan_write_set_groups(
   targets_per_agent) -> list[list[int]]` (agent-index groups), union-find by
   target overlap, empty-target = conflicts-with-all. Fixture-tested.
2. `go_dispatch._execute_parallel`: schedule groups in parallel, agents within a
   group serially, preserving all existing per-agent status/event handling.
- files_out_of_scope: worktree creation, OpenCode home isolation, T3 client.
- evidence_required_for_completion: new hermetic tests pass; full
  `python -m pytest -q` stays green; `verify-public-snapshot.ps1` and
  `verify-control-plane-wheel.ps1` stay green.

## Deferred (requires updated receipt)
- Per-worktree OpenCode state isolation to remove `database is locked`
  (OpenCode-specific, kept inside the adapter boundary). *(Unlocked below as the
  executor-specific half of slice 2; kept inside the go_dispatch OpenCode layer.)*

---

# Slice 2: worktree working-directory isolation (M4, opt-in)

> Second slice under the same governance. Unlocks the worktree half deferred
> above. Date: 2026-06-26. planner_agent_id: kiro. approval: human owner granted
> full automation with mandatory independent review.

## Target
- current_slice_goal: Give each parallel coding agent its own git worktree
  working directory so two agents physically cannot touch the same file tree,
  and give the OpenCode executor a per-agent state dir so its sqlite
  `database is locked` failure cannot occur during concurrent runs.
- requested_outcome: Opt-in via `--isolate`; default OFF and byte-identical to
  today (no regression). Hermetic verification with a throwaway temp git repo;
  real-token end-to-end verification with OpenCode 1.17.9 (owner authorized).

## Design principle (two-layer, unchanged)
- **Generic layer:** `control_plane/worktree.py` knows only git. It creates and
  removes worktrees and never references OpenCode. `CommandWorker.run_packet`
  gains generic, backward-compatible `cwd`/`env_overrides` parameters.
- **Executor-specific layer:** the per-agent OpenCode state-dir override is
  computed in `go_dispatch` (the OpenCode adapter boundary) and passed as a
  generic env override. It never leaks into `worktree.py` or `worker.py`.

## Verified facts (real OpenCode 1.17.9, not assumed)
- OpenCode stores its session sqlite + snapshot/log/repos state under
  `XDG_DATA_HOME` (it creates `<XDG_DATA_HOME>/opencode/...`). The earlier
  assumption that `OPENCODE_HOME` controls this was **wrong** and was corrected
  to `XDG_DATA_HOME` after an empirical probe. A fresh per-agent `XDG_DATA_HOME`
  still authenticates and runs (auth is not lost), confirmed by a passing run.
- The executor reads its project root from the dispatch packet
  (TASKSPEC.md `Project Root` + packet.json). With only `cwd` set to the
  worktree, the agent followed the packet's absolute root and edited the shared
  tree — working-directory isolation was defeated. Fix: rebase the packet's
  `project_root` to the worktree (`DispatchPacketStore.rebase_packet`) so the
  executor's writes land in the worktree. Verified: main tree untouched, edits
  appeared only in each agent's worktree, per-agent `.opencode-data/opencode`
  state dirs were created, and no `database is locked` occurred.

## Resource Map
- `control_plane/worker.py`: `CommandWorker.run_packet` runs `subprocess.run`
  with `cwd=packet.project_root` and `env=os.environ.copy()+RDGOAL_*`.
- `control_plane/dispatch_packet.py`: `DispatchPacketStore.rebase_packet`
  repoints a packet at a worktree and re-renders packet.json + TASKSPEC.md.
- `control_plane/go_dispatch.py`: `_execute_parallel` -> `_run_group` ->
  `_run_agent_in_place` -> `_resolve_isolation` -> `_run_one_agent` ->
  `CommandWorker`.
- `git worktree add --detach <path> HEAD` is the stdlib-free reuse primitive.

## Capability Matrix
- execution isolation
  - current production level: L2 (write-set serialization only; agents share one
    working directory and one OpenCode state dir).
  - target level: L2+ (per-agent worktree + per-agent OpenCode state, opt-in).
  - gap: no working-directory or executor-state isolation existed.

## Build-vs-Buy Decision
- must_reuse: git's own `worktree` command and stdlib `subprocess`; OpenCode's
  own `XDG_DATA_HOME` support. No new dependency.
- must_build_new: a thin, defensive `worktree.py` wrapper, `rebase_packet`, and
  the opt-in wiring.
- rationale: git worktrees are the standard mechanism for multiple working trees
  on one repo; hand-rolling file-tree copies would be inferior.

## Integration Risk Table
- risk: `--isolate` changes default behavior and regresses existing runs.
  - type: correctness | severity: high
  - mitigation: flag defaults OFF; when off, cwd/env are unchanged so the path
    is byte-identical. Full pytest is the gate.
- risk: worktree creation fails (not a git repo, git missing, detached HEAD).
  - type: correctness | severity: medium
  - mitigation: `create_worktree` is defensive and returns None on any failure;
    dispatch falls back to in-place execution (still protected by write-set
    serialization) and records `isolated=false` honestly. No fake green.
- risk: redirecting `XDG_DATA_HOME` loses OpenCode auth.
  - type: correctness | severity: medium
  - mitigation: empirically verified that a fresh per-agent `XDG_DATA_HOME`
    still authenticates and a real run passes.
- risk: absolute worktree paths leak into the public read model.
  - type: privacy/public-surface | severity: medium
  - mitigation: runtime metadata (outside the repo) records the path for
    inspection, but the schema/visual_state projection surfaces only an
    `isolated` boolean, never the path.
- risk: a worktree checks out HEAD, missing uncommitted changes in the main tree.
  - type: correctness | severity: low
  - mitigation: documented behavior of the opt-in mode; isolation is for clean
    parallel writes from a committed base. Default (off) keeps today's behavior.

## Delivered slice
1. `control_plane/worktree.py`: `git_repo_root`, `create_worktree`,
   `remove_worktree`; pure-defensive, returns None on any failure.
2. `DispatchPacketStore.rebase_packet`: repoint a packet at the worktree.
3. `CommandWorker.run_packet(..., cwd=None, env_overrides=None)`: generic and
   backward-compatible; default cwd stays `packet.project_root`.
4. `go_dispatch`: `isolate` param on `run_go_dispatch`; per-agent worktree +
   packet rebase + per-agent `XDG_DATA_HOME`; record `isolated`/`worktree_path`
   (runtime only). `execute_go_run` reuses the stored `isolated` flag.
5. CLI `--isolate` on `devframe code`/`go` (default off).
6. schema/visual_state: surface `isolated` boolean only (never the path).
- evidence: hermetic git tests (`test_worktree.py`, `test_go_worktree.py`) pass;
  full `python -m pytest -q` green; `verify-public-snapshot.ps1` and
  `verify-control-plane-wheel.ps1` green; real OpenCode 1.17.9 two-agent
  `--isolate --execute` run verified (main tree untouched, edits only in
  worktrees, per-agent state dirs, no `database is locked`); independent
  reviewer sub-agent returns a verdict.
