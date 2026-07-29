# Governed Obsidian Project Memory

Lifecycle state: implemented local contract

## Purpose

DevFrame can keep bounded project memory in a user-owned Obsidian Vault while
the repository remains understandable without that private Vault. Memory has
three deliberately different lifecycles:

1. **Working Plan**: current project guidance bound to the exact
   `docs/status/HANDOFF.md` bytes.
2. **Project Lessons and Session Checkpoints**: immutable, project-scoped
   long-lived guidance that does not expire when HANDOFF changes.
3. **Global Playbooks**: a project lesson may be marked as a candidate, but
   publication into the global layer requires a separate human approval.

The authority order is fixed:

1. repository rules and current source;
2. `docs/status/HANDOFF.md` for the formal milestone and next action;
3. Git, tests, evidence, independent review, and FinalVerdict for what happened;
4. all recalled Obsidian memory as untrusted, private guidance.

The working plan never replaces `HANDOFF.md`, TaskSpec, tests, review, or
FinalVerdict.

## One Runtime Path

```text
CLI or consented MCP client
        |
        v
control_plane.obsidian_memory
  - server-derived immutable paths
  - project/source/idempotency validation
  - secret and size checks
        |
        v
existing control_plane.writeback
  - atomic create-only publication
  - proposal + human gate for plans/promotions
  - source preconditions
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

Agent-owned automatic notes use only server-derived paths:

```text
wiki/memories/devframe-agent/projects/<project-id>/checkpoints/<event-sha256>.md
wiki/memories/devframe-agent/projects/<project-id>/lessons/<event-sha256>.md
wiki/memories/devframe-agent/global-playbooks/<project-id>-<lesson-sha256>.md
```

The caller supplies no Vault root or target path. Checkpoint and lesson ids are
derived from a bounded event/session idempotency key plus the verified project
identity. Identical retries return `duplicate`; different bytes under the same
key fail as an idempotency conflict. Atomic create-only publication means
concurrent retries can produce at most one logical note. A lesson has no
HANDOFF hash, so it remains searchable across milestone changes.

## CLI

Resolve/register the current SessionStart project and recall fail-open:

```powershell
devframe memory session-start `
  --cwd D:\work\project\src `
  --runtime-dir D:\private\devframe-runtime `
  --vault-root D:\private\vault `
  --format json
```

For a Git working tree, nested paths resolve to the repository top level. An
existing non-Git directory is treated as its own project root. Exact roots
already present in the canonical RuntimeStore journal retain their project id;
new roots use a folder slug plus a normalized-path hash so equally named
projects remain isolated. The command returns `current`, `missing`, `stale`, or
`unavailable`, never an absolute root, and always exits successfully for a
well-formed SessionStart invocation. Registration is local control-plane
metadata, not a Vault write.

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

Native PreCompact capture uses the bounded transcript reducer:

```powershell
devframe memory checkpoint capture-from-transcript `
  --cwd D:\work\project `
  --transcript-path <codex-home>\sessions\...\rollout.jsonl `
  --session-id <session-id> `
  --turn-id <turn-id> `
  --trigger auto `
  --runtime-dir D:\private\devframe-runtime `
  --vault-root D:\private\vault `
  --format json
```

The transcript must be a plain file under the configured Codex `sessions`
directory. Only a bounded tail is read. The reducer retains the latest bounded
goal plus lines explicitly classified as decisions, failed attempts,
verification, blockers, or next action. It never stores the transcript path,
raw session id, or unclassified conversation.

## MCP

- `propose_project_plan`: stages a bounded plan through the existing writeback
  proposal store. It never writes the Vault.
- `recall_project_plan`: returns the current bounded plan only when the project
  and authoritative source bytes still match.
- `list_project_lessons` and `search_project_lessons`: bounded project-only
  reads.
- `capture_project_checkpoint` and `create_project_lesson`: immutable,
  create-only writes at server-derived paths. These are safe to pre-approve
  only for an exact trusted client.
- `propose_global_playbook_promotion`: stages a create-only promotion. It does
  not publish until the existing human approval path accepts the proposal.

SessionStart registration makes the resolved project visible to the existing
server-side MCP project resolver without restarting the service. Native tool
availability still requires the existing loopback MCP server to be registered
with the Codex client; a prompt or Hook cannot substitute for that client
registration. `codex mcp list` is the direct diagnostic for the CLI client.

The MCP server advertises Codex's `codex/sandbox-state-meta` capability. For
every memory call, Codex supplies the current turn's `sandboxCwd` as a canonical
local `file://` URI outside the model-controlled tool arguments. DevFrame
resolves/registers that cwd and requires the caller's `projectId` to match the
derived project exactly before touching the Vault. Missing or malformed
metadata, remote URI authorities, dot segments/path traversal, reparse roots,
forged ids, and cross-project ids fail with a path-private
`project_scope_rejected` result.

One minimal Codex registration is:

```toml
[mcp_servers.devframe_memory]
url = "http://127.0.0.1:8765/mcp"
bearer_token_env_var = "DEVFRAME_MCP_TOKEN"
enabled_tools = [
  "recall_project_plan",
  "search_project_lessons",
  "list_project_lessons",
  "capture_project_checkpoint",
  "create_project_lesson",
  "propose_project_plan",
  "propose_global_playbook_promotion",
]

[mcp_servers.devframe_memory.tools.recall_project_plan]
approval_mode = "approve"

[mcp_servers.devframe_memory.tools.search_project_lessons]
approval_mode = "approve"

[mcp_servers.devframe_memory.tools.list_project_lessons]
approval_mode = "approve"

[mcp_servers.devframe_memory.tools.capture_project_checkpoint]
approval_mode = "approve"

[mcp_servers.devframe_memory.tools.create_project_lesson]
approval_mode = "approve"
```

Only those five read/safe-create tools receive client-side automatic approval.
`propose_project_plan` and `propose_global_playbook_promotion` deliberately
have no automatic approval entry. This setting does not bypass DevFrame's
connection grant, proposal, exact approval, or create-only publication
boundaries.

Durable `allow_always` is accepted only when the client presents complete
canonical MCP `clientInfo` and the connection is bound to the configured
loopback bearer token. The durable v3 trust key binds the stable client name to
that token. Display title and version remain visible in the connection record
for audit, but an ordinary Codex upgrade does not invalidate the grant. A
name-only client, tokenless connection, changed client name, or changed token
still requires a new decision. Legacy exact-version grants are not silently
promoted. The loopback server answers the optional standalone Streamable HTTP
`GET /mcp` with `405` and `Allow: POST`; all tool requests remain
authenticated POST messages. After a service restart, a request carrying an
unknown stale `MCP-Session-Id` receives HTTP 404 so a conforming client
re-initializes and reuses the durable family grant instead of creating an
identity-less pending connection.

The AI cannot supply a Vault root or target path through MCP. The server owns
the Vault configuration and derives the immutable version path. Approval still
uses the existing human writeback gate; there is no plan-specific bypass.
Existing MCP connection consent and audit still apply.

Every memory tool carries MCP safety annotations. Reads are `readOnlyHint`;
immutable creates are non-destructive and idempotent; plan/promotion proposals
remain destructive-hinted so clients do not silently pre-approve them. All
memory tools are `openWorldHint=false`.

## Global SessionStart Adapter

The public rendering source is
`templates/runtime-bootstrap/recall-obsidian-working-plan.template.ps1`.
One registered Hook can serve every local project because target repository and
project id are derived from bounded SessionStart `cwd`; only runtime, Vault,
and optional loopback-start paths are server-owned activation values.

The Hook is suitable for `startup`, `resume`, `clear`, and `compact`. Malformed
input, an unavailable Git executable, missing Vault/service state, or a project
without a plan cannot block Codex: the Hook emits a bounded `missing` or
`unavailable` envelope and exits zero. A valid current plan is capped again
before context injection and is labeled private, untrusted guidance. The
optional loopback service is checked with a short local probe and started in
the background only when absent; recall itself stays on the direct local CLI
path and does not wait for service startup.

Projects without a current managed note can be resolved and registered without
having `docs/status/HANDOFF.md`; they return `missing`. The existing proposal
path still requires that authoritative file before a persistent plan may be
staged. Choosing another formal authority for non-DevFrame repositories is a
separate contract decision and is not inferred from README or chat content.

## Native PreCompact Adapter

The public rendering source is
`templates/runtime-bootstrap/checkpoint-obsidian-session.template.ps1`.
Codex 0.143.0 exposes a native `PreCompact` command hook with `session_id`,
`turn_id`, `transcript_path`, `cwd`, and `trigger`. The hook validates bounded
JSON input, invokes the transcript reducer in a bounded background job, hides
all CLI output, and always emits a fail-open continue response. The hook
registration also has an outer timeout.

The event id is deterministic, so an automatic retry or concurrent delivery
does not duplicate the checkpoint. A malformed event, unavailable runtime,
unavailable Vault, unsafe transcript, secret-like signal, or timeout creates
nothing and does not block compaction.

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
- `DEVFRAME_OBSIDIAN_MEMORY_READ_ONLY=true` removes memory write tools from
  discovery and independently rejects direct create, plan proposal, promotion,
  and proposal apply validation.
- Native MCP memory calls are bound to the exact current Codex cwd through the
  negotiated sandbox-state metadata. A model-supplied project id alone is
  insufficient, and a non-canonical or cross-project cwd is rejected before
  Vault resolution.
- Automatic writes are limited to immutable agent-owned checkpoints and
  project lessons. No automatic overwrite, edit, move, delete, command
  execution, global promotion, vector store, graph store, or custom Obsidian
  plugin exists.
- SessionStart never captures chat/task output and never stages or applies a
  working plan. Persistent publication remains a separate exact human gate.
- PreCompact stores only the structured high-signal subset described above,
  never a raw conversation.

## Candidate And Cutover

The earlier `codex/obsidian-codex-memory-mvp` branch remains migration source,
not a second supported product. Live activation requires exact configuration
and runtime backups, focused/full verification, a fresh native client probe,
and a deterministic checkpoint canary. Local Git snapshotting is not enabled:
it needs a separate opt-in Recon covering Vault dirty state, exact-path commit
scope, recovery, and disable behavior. No automatic remote push is permitted.
