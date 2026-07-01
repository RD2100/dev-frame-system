# Methodology Skills Registry

`devframe` visual-state now includes a top-level `skills` field that is a read-only
snapshot of methodology skills discovered by the control plane.

## Current surface

At present, the runtime-shipped registry contains one shipped skill and one local
repository-local skill:

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

No local skill registry writes are performed by the UI/runtime from this field;
it is projection-only.

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
