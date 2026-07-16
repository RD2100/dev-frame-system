# Agent Acceptance

Agent Acceptance is the acceptance-contract layer of dev-frame-system. It defines
the machine-enforceable contracts, behavioral policies, governance file lists,
and CI preflight templates that decide whether agent work is allowed to be
reported as done.

It does not run workers itself. The control-plane runtime and workflow tools
consume these contracts and policies so that an ExecutionReport cannot claim
success unless the evidence and exit-code rules are satisfied.

## What ships here

| Path | Purpose |
|---|---|
| `contracts/` | Normative JSON schemas (`FLOW_OUTCOME`, `TASKSPEC`, `DISPATCH_RESULT`, runner schemas) and contract YAML for flow, dispatch, paper, and context-compression work |
| `policies/` | Normative behavioral policies (outcome-first delivery, terminal state, dispatcher, stage gate, run-until-terminal, runner failure, evidence pack) that complement the schemas |
| `governance/` | `expected-files.txt` and `manifest-ignore.txt` describing which files a project should protect and which to exclude from manifest checks |
| `templates/ci-preflight/` | One-time pre-commit / pre-push governance hook installer (`register-hooks.ps1`, `ci-preflight.ps1`, hooks, governance lists) |

## Core conventions

- Exit code contract: `0 = PASS`, `1 = BLOCKED`, `2 = FAILED`.
- No fake green: `FAILED` and `BLOCKED` must never be reported as `PASS`.
- Default dry-run: real, irreversible actions require an explicit opt-in flag.
- Outcome-first scope: governance intensity follows milestone risk; process
  activity does not substitute for a product, research, test, review, or
  delivery outcome.
- Precedence: **Contracts > Policies > Conventions**. If a policy contradicts a
  contract, the contract wins because contracts are machine-enforceable.

## Contracts vs policies

- **Contracts** (`contracts/`) define WHAT the data must look like. They are the
  single source of truth; automation must validate its output against them
  rather than against Markdown reports.
- **Policies** (`policies/`) define HOW automation must behave, and carry the
  rationales and decision matrices that the contracts reference.

See `contracts/README.md` and `policies/README.md` for the full schema and
policy index, including the AA-2 runner layer that adds runner-level enforcement
on top of the AA-1 normative layer.

## CI preflight

To activate the governance hooks in a target project, copy
`templates/ci-preflight/` into that project and run its `register-hooks.ps1`.
See `templates/ci-preflight/README.md` for the per-project setup and
customization steps.

## License

Apache License 2.0, inherited from the repository root.
