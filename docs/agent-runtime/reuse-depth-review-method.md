# Reuse-Depth Review Method

A repeatable method for auditing a project that claims to be "built on top of"
mature open-source software (clients, runtimes, editors, agents, bridges). It
answers one blunt question: **did the reuse actually happen, or is the project
only adjacent to the software it claims to stand on?**

This method is downstream of `rules/recon.md` and `rules/open-source-reuse.md`.
Those rules say *do not hand-roll mature capabilities*. This method checks
whether a capability that was supposedly reused is reused **deeply enough to
deliver value**, or whether it stalled at the shallowest possible adapter.

Use it for any milestone that integrates an external runtime, client, editor,
provider, or bridge.

## Why this exists

A project can pass every governance gate, accumulate thorough assessments and
probes, and still ship almost no real capability — because integration keeps
stopping at the thinnest layer (a read-only projection, a subprocess call, a
summary-only probe). Documentation and projections then grow far richer than
the real data underneath them. This method names that failure mode and forces
it into the open.

## The reuse-depth ladder

Rate every external-capability integration on this ladder. The gap between the
**highest level a probe has proven** and the **level production actually uses**
is the single most important signal.

| Level | Name | What it means |
|---|---|---|
| L0 | Assessed | A reuse assessment / Recon Receipt exists; nothing runs. |
| L1 | Shallow adapter | One-way read-only projection, subprocess black box, or summary-only probe. Output is text/markdown that gets re-parsed. |
| L2 | Structured adapter | Real structured data crosses the boundary (events, sessions, tool calls, token/cost, diffs) and lands in first-class objects. |
| L3 | Deep integration | Bi-directional: the project drives and is driven by the reused software (event streams, write-back, live protocol), with governance still owned locally. |

Most stalls live at **L1**. The danger is that L0 assessments and L1 adapters
*look* like progress while the product value lives at L2/L3.

## The five recurring patterns (checklist)

Run this checklist against the whole project, not one module:

1. **Probe-to-production gap.** Has a probe proven a capability (L2/L3) that
   production still consumes at L1? Search for probe/readiness modules and
   compare what they prove against what the main execution path actually uses.
2. **Hollow projection.** Is the read-model / projection layer much richer than
   the real data feeding it? Check whether contract fields (cost, tokens,
   tool_calls, diffs, messages) are populated by real runs or left empty.
3. **Two-of-everything.** Do two subsystems implement overlapping concepts
   (two orchestrators, two gate systems, two session models) without a single
   declared source of truth?
4. **Unsafe concurrency.** Does parallel/dispatch execution have real isolation
   (worktrees, write-set serialization, locks), or does it rely on retries and
   luck? Look for "lock", "retry", "database is locked" in status notes.
5. **Missing core delivery.** Is the headline product value (e.g. an editor's
   edit-review-accept loop, or a bridge's bi-directional call) actually
   shipped, or is the surface read-only / one-way only?

## Diagnostic procedure

For each external capability domain (client, runtime, provider, bridge):

1. **Find the seams.** Read the production integration point and the
   probe/assessment for the same domain. Cite exact files.
2. **Rate both ends.** Production level on the ladder vs highest proven level.
3. **Name the gap.** If production < proven, that is a probe-to-production gap;
   record the exact missing wiring.
4. **Check the projection.** For each contract field the domain should fill,
   verify it is real data, not empty/derived.
5. **Check concurrency and write safety** if the domain mutates state.
6. **Classify** with keep / build / borrow, and set a **target reuse level**
   plus the **smallest verifiable slice** that raises production one rung.

## Hollow-projection test

For any read model or projection, list its richest fields and ask, for each:
*does a real run populate this, or is it always empty / copied / inferred?* A
projection whose marquee fields are never really filled is decoration, not
capability. Prefer raising real data (L2) over adding projection shapes.

## Standards & Ecosystem Scan (blind-spot prevention)

The ACP/MCP confusion is a worked example of a predictable failure mode:
reconnaissance scanned candidate *products* (T3Code, OpenCode) but not the
*protocols and standards* underneath them, so the team almost built a
CLI-subprocess integration without noticing ACP — the actual standard for
driving coding agents. Reuse-first without ecosystem recon produces these blind
spots.

Before committing to *how* to integrate a capability, run a short scan and
record it (one paragraph is enough):

1. **Standards/protocols in this domain.** What open standard already governs
   this (e.g., MCP for model->tools, ACP for editor->agent, LSP, OpenAI-compatible
   API, A2A)? Integrating against a standard beats integrating against one
   product.
2. **Capability vs product.** Separate "what the product does" from "what
   protocol/interface it exposes". The reusable thing is usually the interface.
3. **Time-sensitive facts get a live check.** Vendor plan gating, protocol
   support, and ecosystem membership change fast. For these, search and cite
   with a date rather than relying on training memory.
4. **Name the assumption.** Write down the load-bearing assumption ("we assume
   X integrates via Y"). An unverified load-bearing assumption is a finding, the
   same way fake-green is a finding.
5. **Record verified facts in a cited landscape ledger** (e.g.
   `docs/agent-runtime/agent-protocol-landscape.md`) so the same blind spot is
   not rediscovered.

Blind spots can never be fully eliminated — you do not know what you do not
know. But they are systematically reduced by: standards-first recon, a cited
landscape ledger, search-first on time-sensitive facts, a reviewer/red-team that
challenges unverified assumptions, and cheap spikes before commitment. Treat
"we assumed and did not verify" as a defect, not a detail.

## Output template

A review using this method should produce:

```markdown
## Reuse-Depth Review: <date>

### Domain ratings
| Domain | Production level | Highest proven level | Gap |
|---|---|---|---|

### Pattern findings
- Probe-to-production gap: ...
- Hollow projection: ...
- Two-of-everything: ...
- Unsafe concurrency: ...
- Missing core delivery: ...

### Plan (priority-ordered)
For each item: goal, what to reuse, target reuse level, governance prerequisite
(Recon Receipt?), risk/cost accepted, smallest verifiable slice, acceptance gate.
```

## Cost-acceptance principle

Raising reuse depth has a real cost: heavier dependencies, more complex
adapters, more real (non-mock) verification. This method makes that trade
explicit. Staying at L1 forever to keep things "clean" is itself a cost — it
ships hollow capability. When a probe has already proven L2/L3 is feasible,
defaulting to L1 in production is a finding, not a safe choice.

## Non-negotiables

- Raising reuse depth never bypasses `rules/recon.md`: mature-capability work
  still needs a Recon Receipt before write-capable changes.
- Real verification beats mock verification for the value claim. If the value
  (e.g. real token/cost) can only be proven with the real external tool, say so
  explicitly; do not let a mock test masquerade as proof of the value.
- No fake green. A slice that wires structured data but cannot yet verify it
  end-to-end is reported as partial, not done.
