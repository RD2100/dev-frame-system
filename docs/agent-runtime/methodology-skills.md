# Methodology Skills Registry

`devframe` visual-state includes a top-level `skills` field that is a read-only
snapshot of built-in methodology skills discovered by the control plane.

Methodology skills have two related surfaces:

- built-in repository skills under `tools/skills/<skill-id>/SKILL.md`;
- runtime custom skills stored as scoped `skills.json` records and editable from
  the local client.

They are methodology selectors for DevFrame runs. They are not automatically
loaded into every model conversation, and they are not stable runtime contracts
by themselves.

For shared coding-discipline behavior, methodology skills should cite
[Agent Coding Discipline](agent-coding-discipline.md) rule IDs instead of
copying broad discipline prose. A discipline rule remains behavior guidance and
governance input until review-governance evidence and gate decisions validate a
specific run.

## Current surface

At present, the runtime-shipped registry contains one shipped skill and multiple
repository-local skills:

- `agent-acceptance`
  - title: `agent-acceptance`
  - source_path: `templates/runtime-bootstrap/SKILL.md`
  - source_kind: `local_repository_asset`
  - triggers: from markdown frontmatter description, such as `@go`
  - status: `registered`

- `tdd`
  - title: `tdd`
  - source_path: `tools/skills/tdd/SKILL.md`
  - source_kind: `local_repository_asset`
  - triggers: from markdown frontmatter description, such as `@tdd`
  - status: `registered`

- `evidence-driven-acceptance`
  - title: `evidence-driven-acceptance`
  - source_path: `tools/skills/evidence-driven-acceptance/SKILL.md`
  - source_kind: `local_repository_asset`
  - triggers: from markdown frontmatter description, such as `@evidence`
  - status: `registered`

- `context-pack-builder`
  - title: `context-pack-builder`
  - source_path: `tools/skills/context-pack-builder/SKILL.md`
  - source_kind: `local_repository_asset`
  - triggers: from markdown frontmatter description, such as `@context-pack`
  - status: `registered`

- `bind-chrome`
  - title: `bind-chrome`
  - source_path: `tools/skills/bind-chrome/SKILL.md`
  - source_kind: `local_repository_asset`
  - triggers: from markdown frontmatter description, such as `@bind-chrome`
  - status: `registered`
  - runtime support: `devframe web-ai bind-conversation` and
    `devframe web-ai bind-chrome`

- `external-brain`
  - title: `external-brain`
  - source_path: `tools/skills/external-brain/SKILL.md`
  - source_kind: `local_repository_asset`
  - triggers: from markdown frontmatter description, such as `@external-brain`
  - status: `registered`
  - runtime support: `devframe web-ai prepare-review-bundle` and
    `devframe web-ai validate-review-bundle`

- `review-governance-kernel`
  - title: `review-governance-kernel`
  - source_path: `tools/skills/review-governance-kernel/SKILL.md`
  - source_kind: `local_repository_asset`
  - triggers: from markdown frontmatter description, such as `@review-kernel`
  - status: `registered`

- `intent-framing-gate`
  - title: `intent-framing-gate`
  - source_path: `tools/skills/intent-framing-gate/SKILL.md`
  - source_kind: `local_repository_asset`
  - triggers: from markdown frontmatter description, such as `@intent-frame`
  - status: `registered`

The visual-state `skills` field is projection-only. Runtime custom skill edits
use the scoped customization API and the `custom_skills.py` store described
below.

## Functional map

| Need | File or surface | Role |
|---|---|---|
| Discover built-in skills | `packages/control-plane/control_plane/skill_registry.py` | Scans `tools/skills/*/SKILL.md` and the shipped bootstrap skill |
| Resolve a leading trigger for a run | `packages/control-plane/control_plane/methodology_dispatch.py` | Converts `@trigger goal` into run methodology plus the effective goal text |
| Store editable custom skills | `packages/control-plane/control_plane/custom_skills.py` | Validates and persists scoped custom skills |
| Validate custom skill shape | `schemas/custom_skills.schema.json` | Machine-readable custom skill contract |
| Project skills to visual state | `packages/control-plane/control_plane/visual_state.py` | Shows discovered methodology skills and selected run methodology |
| Edit skills from the local client | `/api/t3/skills` in `dashboard.py` | Loopback/origin-gated scoped customization endpoint |
| Prove behavior | `packages/control-plane/tests/test_custom_skills.py` and related CLI tests | Covers loading, overriding, trigger resolution, and run projection |
| Bind ChatGPT conversation | `devframe web-ai bind-conversation` and `tools/skills/bind-chrome/SKILL.md` | Creates summary-only runtime session plus user-level project binding files |
| Prepare external review bundles | `packages/control-plane/control_plane/external_review_bundle.py` | Creates ZIP, manifest, context ledger, prompt, redaction report, and validation result |
| Validate external review bundles | `devframe web-ai validate-review-bundle` | Checks manifest/ZIP consistency and per-file hashes before Web AI submission |

## Trigger behavior

Methodology skills are selected when a DevFrame run goal starts with a registered
trigger, for example:

```text
@tdd add parser tests
@bind-chrome bind https://chatgpt.com/c/<id>
@external-brain prepare a GPT review prompt
@context-pack build a handoff packet
@intent-frame check whether this directory prevents future misses
@review-kernel implement Phase 1A
```

`resolve_methodology(...)` removes the matched leading trigger from the user goal
and attaches the matching methodology record to the prepared run. The run then
records and projects that methodology.

Important boundaries:

- Adding a built-in `tools/skills/<skill-id>/SKILL.md` makes it discoverable to
  DevFrame's methodology registry.
- It does not make this repository's current coding agent automatically load
  that skill body during normal chat.
- It does not auto-trigger on ordinary words unless the run goal begins with the
  registered `@trigger`.
- Future route inference may use skills as metadata, but current safe behavior
  is explicit trigger or configured run default.
- Discipline rule IDs may be cited by a skill or review report, but rule
  citation is not acceptance evidence by itself.

## Custom skill behavior

Custom skills are stored outside the public repository in scoped runtime
configuration:

```text
<runtime>/skills.json
<runtime>/<project-id>/skills.json
```

The effective view merges built-in, global, and project scopes. More specific
project-scope records override global records, and custom skills can override a
built-in skill by id. Capability flags are resolved conservatively: restrictive
project rules and P0 hard denies win over permissive skill settings.

## Optional extensions

If a local `tools/skills/<skill-id>/SKILL.md` is present in the repository,
`control_plane.skill_registry.list_methodology_skills()` adds it to the same
read-only list (deduplicated by normalized `skill_id`, then sorted by id).

To expose a new methodology skill, add a standard SKILL.md under the local
`tools/skills` directory and restart the runtime read path. If absent, the
registry still remains valid with only the shipped bootstrap skill.

## Data shape and read-only nature

Each registry item matches the schema in `schemas/methodology-skill.schema.json`:
`skill_id`, `title`, `source_path`, `source_kind`, `triggers`, and `status`.
`source_kind` indicates where the descriptor came from, and `status` is read-only
state (`registered`) today.
