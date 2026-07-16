# Documentation

Use this directory for durable repository knowledge.

## Reading Order

- [Architecture](./architecture/README.md): current system shape, subsystem maps, and cross-cutting technical context.
- [Conventions](./conventions/README.md): stable coding, layering, naming, testing, review, and storage rules.
- `AGENTS.md` files: scoped action guides for agents and contributors working in a specific part of the tree.

## Source Of Truth

Keep the documentation layers distinct:

- use `AGENTS.md` for quick routing, required checks, and high-priority local instructions
- use `docs/conventions` for durable rules that should survive individual implementation changes
- use `docs/architecture` for the intended structure and current subsystem model
- keep temporary plans out of these directories unless the enduring decision has landed

When a rule changes, update the narrowest durable document that owns the rule, then keep the relevant `AGENTS.md` file as a pointer rather than a second explanation.
