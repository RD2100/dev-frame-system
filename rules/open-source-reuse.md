# Open Source Reuse Rules

These rules apply when dev-frame-system work overlaps a mature open-source
project, especially visual agent clients, local coding-agent runtimes, browser
automation, and provider adapters.

These rules are downstream of `rules/recon.md`. For mature capability work,
first produce a Recon Receipt, then record the open-source reuse decision.

## RULE reuse-000: No Blind Hand-Rolling

- **Priority**: P0
- **Trigger**: Proposing, planning, or implementing a client, agent UI,
  session UI, coding-agent runtime, terminal, diff viewer, browser adapter,
  provider adapter, orchestration server, or desktop/mobile shell.
- **Rule**: Blind hand-rolling is forbidden. An agent must not build from
  scratch before explicitly checking whether a mature open-source project,
  existing local module, or proven library can be reused, adapted, wrapped, or
  forked. Defaulting to hand-written implementation without this analysis is
  inefficient, lower quality, and less stable than standing on proven software.
- **Verification**: The plan, status note, or review report includes a Recon
  Receipt or reuse assessment with inspected candidates, reuse boundary,
  rejection reason when not reused, license/public-surface check, and the
  smallest custom code that still needs to be owned by devframe.
- **Conflict Handling**: If no reuse assessment exists, stop the work and mark
  the milestone `blocked` until the assessment is written. P0 safety, license,
  privacy, and public-surface rules still override any reuse choice.

## RULE reuse-001: Reuse Before Hand-Rolling

- **Priority**: P1
- **Trigger**: Building UI, runtime, orchestration, session, terminal, diff,
  provider, or browser-control behavior that likely exists in a mature
  open-source project.
- **Rule**: Inspect reusable open-source options before building from scratch.
  Prefer adapting a proven project, library, protocol shape, or UI pattern when
  it can satisfy the product goal without weakening devframe governance.
- **Verification**: The plan or status note names the candidates inspected and
  records why one was reused, adapted, or rejected.
- **Conflict Handling**: P0 safety, license, privacy, and public-surface rules
  override reuse pressure.

## RULE reuse-002: Devframe Owns The Control Plane

- **Priority**: P1
- **Trigger**: Reusing a visual client or coding-agent runtime.
- **Rule**: Reused software may provide UI structure, session transport,
  terminal behavior, editor integration, or executor mechanics. Devframe must
  continue to own project contracts, goal state, evidence, review, gates,
  decisions, and external-brain workflow semantics.
- **Verification**: The integration boundary identifies which objects remain
  devframe-owned and which objects are delegated to the reused project.
- **Conflict Handling**: If reuse would make governance objects invisible or
  unenforceable, choose a thinner adapter or reject the reuse.

## RULE reuse-003: Default Reuse Candidates

- **Priority**: P2
- **Trigger**: Planning or building the visual control plane.
- **Rule**: Treat `/go` as the development orchestration loop that dispatches
  planners, reviewers, and coding agents; do not treat `/go` itself as the
  product objective or visual client. Treat T3Code / T3 Code as the primary
  visual-client reuse candidate for coding-agent session visibility and
  control-plane interaction patterns. Treat OpenCode as the first local
  coding-agent runtime/provider reference. A lightweight web dashboard can
  exist for snapshots, diagnostics, or narrow public-surface checks, but it
  must not become the main client unless that scope is explicitly approved.
  These are defaults, not hard dependencies.
- **Verification**: The implementation plan states whether T3Code / T3 Code,
  OpenCode, both, or neither are being used for the current slice. If a web
  dashboard is used, the plan records whether it is support-only or explicitly
  scoped as the main client.
- **Conflict Handling**: A better-fitting project can replace a default
  candidate when the reason is recorded.

## RULE reuse-004: No Silent Vendoring

- **Priority**: P0
- **Trigger**: Copying source, assets, styles, schemas, or build configuration
  from another project into this repository.
- **Rule**: Do not vendor, fork, or copy external project material without a
  recorded source URL, license, commit or version, attribution requirement, and
  public-repo suitability check.
- **Verification**: The review report lists the imported paths, source, license,
  and reason for inclusion.
- **Conflict Handling**: Missing or incompatible license information blocks the
  import.

## RULE reuse-005: Keep Reference Clones Out Of The Public Repo

- **Priority**: P0
- **Trigger**: Cloning or downloading external source for inspection.
- **Rule**: Store external reference clones outside this repository unless a
  dedicated, reviewed, and ignored reference location is created. Do not add
  submodules, browser profiles, local runtime state, or downloaded reference
  trees to the public distribution surface.
- **Verification**: `git status --short` does not show external reference trees
  or generated local runtime state.
- **Conflict Handling**: If a reference must become product code, route it
  through RULE reuse-004 first.

## RULE reuse-006: Visual Reuse Must Be User-Visible

- **Priority**: P2
- **Trigger**: Claiming progress on a reused visual product slice.
- **Rule**: Verification must include a zero-configuration way to open the
  visual surface and inspect the current product state. CLI-only checks can
  support the claim, but they cannot be the only acceptance evidence for a
  visual control-plane milestone.
- **Verification**: The status note includes the local launch command or URL and
  a browser-based acceptance result.
- **Conflict Handling**: If browser verification is impossible, mark the visual
  milestone as blocked or partial instead of complete.
