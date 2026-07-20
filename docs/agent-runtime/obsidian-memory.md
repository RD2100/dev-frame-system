# Governed Obsidian Working Plans

Lifecycle state: implemented MVP contract

## Purpose

DevFrame can keep one project working plan in a user-owned Obsidian Vault while
the repository remains understandable without that private Vault.

The authority order is fixed:

1. repository rules and current source;
2. `docs/status/HANDOFF.md` for the formal milestone and next action;
3. Git, tests, evidence, independent review, and FinalVerdict for what happened;
4. the Obsidian working plan as untrusted, private guidance.

The working plan never replaces `HANDOFF.md`, TaskSpec, tests, review, or
FinalVerdict.

## One Runtime Path

```text
CLI or consented MCP client
        |
        v
control_plane.obsidian_memory
  - immutable project-version path
  - project/source validation
  - secret and size checks
        |
        v
existing control_plane.writeback
  - preview/proposal
  - human gate
  - source precondition
  - atomic create-only apply and audit
        |
        v
Obsidian Markdown Vault
```

There is no second proposal store, write authority, evidence store, workflow
engine, or memory database. CLI and MCP are adapters over the same production
functions.

## Managed Notes

Each approved plan is an immutable version:

```text
wiki/memories/<project-id>-now-<handoff-sha16>-<version>-<plan-sha16>.md
```

Its filename and metadata bind the project id, `working_only` authority, the
relative `HANDOFF.md` source path and SHA-256, a canonical UTC version token,
and the plan SHA-256. CRLF input is normalized to LF before hashing and writing.
The version token also binds the recorded update time, so
editing frontmatter cannot change which version recall selects. Publication is
create-only: approval cannot overwrite an existing note, including when a
different writer wins the race after preview. The Vault root never appears in
a client response.

If the current `HANDOFF.md` bytes no longer match the recorded source hash,
recall returns `stale` with an empty plan. When several valid versions match the
current source, recall returns the newest recorded version. Older versions stay
recoverable; the MVP does not retire or delete them. A new plan must be proposed
from the new authority bytes. A fresh Vault with no managed plan directory or
version returns `missing` rather than an error.

## CLI

Stage a proposal without writing the Vault:

```powershell
devframe memory plan propose `
  --project-root D:\work\project `
  --project-id project-id `
  --vault-root D:\private\vault `
  --contents-file .\working-plan.md `
  --runtime-dir D:\private\devframe-runtime `
  --format json
```

Proposal exits `3`, matching the existing human-gate convention. It returns a
`requestId`. A separate, exact approval applies that same staged proposal and
records the existing writeback audit:

```powershell
devframe memory plan approve `
  --request-id wb-0123456789abcdef `
  --runtime-dir D:\private\devframe-runtime `
  --confirm `
  --format json
```

Without `--confirm`, approval remains at the human gate and exits `3`.

Recall:

```powershell
devframe memory plan recall `
  --project-root D:\work\project `
  --project-id project-id `
  --vault-root D:\private\vault `
  --format json
```

`--vault-root` may be omitted when the server-owned
`DEVFRAME_OBSIDIAN_MEMORY_ROOT` is configured.

## MCP

- `propose_project_plan`: stages a bounded plan through the existing writeback
  proposal store. It never writes the Vault.
- `recall_project_plan`: returns the current bounded plan only when the project
  and authoritative source bytes still match.

The AI cannot supply a Vault root or target path through MCP. The server owns
the Vault configuration and derives the immutable version path. Approval still
uses the existing human writeback gate; there is no plan-specific bypass.
Existing MCP connection consent and audit still apply.

## Safety Boundaries

- Plan body limit: 16 KiB; managed note limit: 32 KiB.
- Only a plain local Obsidian Vault with a plain `.obsidian` directory is
  accepted.
- Existing writeback traversal, sensitive-path, symlink, and reparse checks are
  reused.
- Common private-key, access-key, bearer-token, credential, password, and token
  shapes are rejected before staging and before recall output.
- Approval rechecks the proposal-time `HANDOFF.md` SHA-256. A source change
  rejects the write before publication. The same source and root bindings are
  checked immediately before and after the atomic publish boundary; a failed
  post-check removes the uncommitted target.
- The staged action remains bound to the human preview, proposal kind, thread,
  project, create-only policy, and proposal-time physical identities of the
  Vault and source roots. Dashboard approval routes managed plans through the
  same plan-specific validation as CLI approval.
- A request-ID decision holds an OS file lock. Concurrent approve/reject calls
  cannot both report success, and process exit automatically releases the lock.
- If exact create-only bytes and their matching audit were persisted before the
  terminal proposal status, retry reuses that one audit and completes the
  record. A target with no matching audit is not accepted as DevFrame output,
  even when its bytes match; different bytes also fail closed.
- Retrying an already-applied request re-reads the published note through the
  bounded handle path. Missing or different bytes fail instead of returning a
  successful approval status.
- Managed notes use atomic create-only publication. An existing or concurrently
  created target fails instead of overwriting newer bytes.
- Publication stays bound to an opened OS file/directory handle through the
  atomic rename and verifies the final handle path before success. A concurrent
  parent rename or junction replacement either cannot proceed or deletes the
  uncommitted file and fails closed without reporting the proposal as applied.
- Recall reads through an opened file handle, verifies its final OS path, and
  rejects a file whose identity or metadata changes during the bounded read.
- Recall reads at most the newest 64 filename-bound versions for the current
  `HANDOFF.md` source. Older notes remain recoverable Vault history and cannot
  make current recall fail merely by increasing the version count.
- Pending-proposal and approval responses expose only the managed relative path;
  Vault, resolved-target, project-root, and local audit paths remain private.
- No automatic apply, overwrite policy, hard deletion, watcher, vector store,
  graph store, custom Obsidian plugin, or global configuration mutation exists
  in this MVP.

## Candidate And Cutover

The earlier `codex/obsidian-codex-memory-mvp` branch is reviewed migration
source, not a second supported product. Its large activation controller is not
part of this MVP. A live installation may switch only after isolated wheel and
Vault-copy verification, configuration/runtime hash capture, explicit human
approval, and a fresh-session recall canary. The old runtime stays recoverable
until that canary passes.
