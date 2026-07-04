# Graph Projection And Knowledge Canvas Plan

Lifecycle state: External-brain reviewed deferred module plan with v3 PASS;
P1 edits confirmed

Plan status: Proposed deferred projection and context-navigation module. This
is not an implementation claim and must not displace the current
review-governance kernel, Paper KB fixture work, or visual-control-plane
read-model boundary.

Reader: DevFrame maintainers and coding agents deciding whether and how to add
a graph/canvas layer that makes project knowledge, code, evidence, skills,
external-brain feedback, and Paper KB artifacts visible to humans and usable by
AI agents.

Post-read action: keep this module as a P2 deferred projection layer. Do not
build UI, graph stores, code extractors, or writeback behavior until the
review-governance kernel and basic projection derivation have passed.

Related docs: [Document-Driven Transformation Master Plan](document-driven-transformation-master-plan.md), [Visual Control Plane](../agent-runtime/visual-control-plane.md), [Context Management Architecture Plan](context-management-architecture-plan.md), [Paper Knowledge Base Iteration MVP Plan](paper-knowledge-base-iteration-mvp-plan.md), [Reuse-First Constraint Governance Implementation Plan](reuse-first-constraint-governance-implementation-plan.md), [Review-First Governance Kernel Implementation Spec](review-first-governance-kernel-implementation-spec.md)

## Goal

Create a governed graph projection that lets humans and AI agents inspect the
relationships between DevFrame objects:

```text
documents
  -> plans
  -> skills
  -> code modules
  -> runs
  -> artifacts
  -> evidence
  -> decisions
  -> external-brain feedback
  -> Paper KB notes and claims
```

The graph should help humans see, filter, zoom, annotate, and eventually
propose relationship edits through governed proposals. It should help AI
agents select context, trace evidence, understand module boundaries, and avoid
bypassing governance.

The graph is a projection. It is not a new authority layer.

`GraphProjection` is not a phase-one top-level governance object. It is either
an `Artifact(kind=graph_projection)` or a nested `projection.graph` payload
inside a review-governance packet.

## User-Facing Capability

The eventual user experience should support:

- browsing a project capability map instead of searching isolated files;
- zooming from whole-project overview to one module, run, claim, or skill;
- filtering by node type, relationship type, evidence status, freshness, and
  privacy class;
- selecting a node and seeing source refs, authority level, related evidence,
  current decision status, and known blockers;
- asking an AI agent to use the visible graph neighborhood as a context seed;
- dragging nodes and saving layout preferences without changing facts;
- adding human annotations to nodes or edges;
- proposing relationship changes without silently mutating source truth;
- exporting a safe graph slice for external-brain review or Paper KB work.

## Placement In DevFrame

The module belongs between Projection and Context Selection:

```text
Governance core
Project / WorkItem / Run / Artifact / Evidence / Decision
        |
        v
Graph Projection
read-only graph derived from governed facts and selected indexes
        |
        v
Context Selection And Human UI
agents retrieve graph neighborhoods; humans inspect, arrange, and annotate
```

It must not live inside Paper KB alone. Paper KB is one consumer, not the owner.

It must not live inside `Decision`. Graph facts can support or question a
decision, but only DevFrame or a human gate can create an authority-bearing
decision.

It must not live as a private UI state model. The visual surface may store
layout preferences and draft annotations, but source facts must remain tied to
governed objects, source refs, and evidence.

## Priority

Priority: P2.

Rationale:

- It is high value for project navigation, external-brain bundle coverage,
  onboarding, code impact analysis, and Paper KB exploration.
- It depends on P0/P1 foundations: the review-governance kernel and projection
  derivation must exist first.
- Building a full editable graph UI too early would repeat the same failure the
  master plan already blocks: attractive projection work overtaking evidence
  and decision boundaries.

Recommended order:

1. P0: review-governance kernel schema, fixtures, and negative tests.
2. P1: basic projection derivation that proves projection cannot override
   decisions.
3. P2: graph projection contract and read-only graph artifact.
4. P3: interactive graph/canvas UI for zoom, pan, filter, and inspect.
5. P4: annotation and proposal writeback through governed decisions.

## Research And Reuse Notes

Do not hand-roll the visualization stack blindly.

Useful open-source patterns:

| Need | Candidate family | Reuse stance |
|---|---|---|
| Node-based editing and small/medium interactive graphs | React Flow / xyflow | Good for editable nodes, edges, controls, minimap, viewport, and custom node UIs. Pair with a layout engine. |
| Knowledge/network graph exploration | Cytoscape.js | Good for graph analysis, layouts, pan/zoom, selection, and biology-style network exploration. |
| Large graph rendering | sigma.js + Graphology | Good for WebGL rendering and graph algorithms when node counts grow. Editing needs custom work. |
| Directed / hierarchical layout | Dagre, ELK, Graphviz | Use for dependency, workflow, and evidence-chain layouts. |
| Force and clustered layout | D3-force, ForceAtlas2-style algorithms | Use for dense knowledge maps where hierarchy is not natural. |
| Human canvas interchange | JSON Canvas, Obsidian Canvas, tldraw, Excalidraw | Use for annotation, spatial arrangement, and compatibility with knowledge-work tools. |
| Code relationship extraction | CodeGraph, Joern / Code Property Graph | Prefer existing code graph and CPG concepts over custom parsing. |
| Knowledge-graph-assisted retrieval | GraphRAG-style systems | Useful inspiration for graph-guided context selection, not a UI replacement. |

Reuse constraints:

- Reused libraries may render, layout, or manage canvas interactions.
- DevFrame owns graph semantics, provenance, privacy classes, authority levels,
  evidence refs, and decision boundaries.
- No graph, canvas, code-graph, or GraphRAG dependency may be added in
  `graph-projection-contract-v0`. Dependency adoption requires a failing local
  test or documented gap, license check, adapter boundary, fallback, and tests
  proving DevFrame rules still own final decisions.
- No source import, vendoring, or fork is allowed without a reuse assessment,
  license check, attribution plan, and public-surface review.

## Graph Contract

The first graph contract should be small and explicit.

Minimum graph artifact:

```text
graph_projection_id
project_id
created_at
scope
source_snapshot_refs
node_count
edge_count
nodes
edges
omitted_sources
privacy_summary
layout_profiles
validation_summary
```

Minimum node fields:

```text
id
kind
label
source_ref
source_kind
authority_level
privacy_class
freshness
confidence
provenance
evidence_refs
decision_refs
display
```

Recommended node kinds:

```text
project
work_item
document
plan
skill
code_file
code_symbol
run
artifact
evidence
decision
external_review_bundle
external_review_feedback
paper_source
paper_note
paper_claim
annotation
proposal
```

Minimum edge fields:

```text
id
kind
source
target
source_ref
authority_level
privacy_class
freshness
confidence
evidence_refs
decision_refs
provenance
```

Recommended edge kinds:

```text
contains
references
depends_on
implements
tests
generates
supports
rejects
contradicts
reviews
decides
blocks
supersedes
imports
calls
derived_from
bundled_for_review
annotates
proposes_change_to
```

Authority levels:

```text
source_truth
governed_decision
evidence_backed
human_annotation
agent_proposal
inferred
unknown
```

Privacy classes:

```text
public_repo
local_path_only
private_content_summary
sensitive_redacted
forbidden
```

Rule: `forbidden` nodes or edges must not be exported to web AI review bundles,
public snapshot docs, or human-visible public reports.

## Write And Edit Policy

After the read-only UI is accepted, the UI may support layout preferences:

- node positions;
- collapsed groups;
- saved filters;
- visual clusters;
- color or label display preferences.

These are display preferences, not source facts. Layout preferences must not
update node authority, edge truth, evidence, decisions, or source content.

The UI may support annotations later:

- note on node;
- note on edge;
- question about relation;
- suspected missing edge;
- suspected wrong edge;
- proposed rename or grouping.

Annotations become artifacts or proposals. They do not directly mutate graph
facts.

The UI must not directly support:

- accepting an inferred relationship as truth;
- marking a work item complete;
- changing a decision outcome;
- approving skill promotion;
- broad Obsidian writeback;
- external-brain upload;
- code edits;
- changing privacy class to a less restrictive value.

Those actions require governed work items, evidence, and decisions.

## Agent Use Cases

AI agents should be able to consume graph slices for:

1. context packet seed selection;
2. external-brain bundle source selection;
3. code impact analysis before edits;
4. skill discovery and dependency tracing;
5. Paper KB claim/evidence navigation;
6. stale or conflicting plan detection;
7. review checklist generation;
8. onboarding to project capability maps.

The graph slice must include:

- selected nodes and edges;
- omitted high-impact neighbors;
- authority and privacy summaries;
- source refs;
- unresolved gaps;
- recommended must-read docs or files.

The graph slice must not include:

- raw private paper text;
- browser transcripts;
- cookies or browser profile paths;
- secret material;
- unredacted local private paths;
- raw vector payloads.

## Human UI Use Cases

Human users should be able to:

- open a project graph;
- search a module, paper claim, skill, or decision;
- zoom and pan;
- switch between layout profiles;
- click nodes and edges for details;
- hide low-authority inferred edges;
- show only blockers, missing context, or P0 risks;
- inspect what will be sent to an external-brain bundle;
- add annotations and proposed corrections;
- export a graph slice as JSON Canvas or a review bundle source.

The first user-facing surface can be read-only. It does not need batch editing,
real-time collaboration, or generalized graph database features.

## Layout Profiles

Layout is a projection choice, not a data truth.

Required first profiles:

| Profile | Purpose |
|---|---|
| governance_chain | Show Project -> WorkItem -> Run -> Artifact/Evidence -> Decision -> Projection. |
| dependency_dag | Show document/module/schema/test dependencies. |
| external_review_bundle | Show selected sources, omitted sources, required roles, redaction, and review feedback. |
| paper_claim_map | Show paper sources, notes, claims, evidence, and review feedback. |
| code_impact | Show code files, symbols, tests, schemas, and docs affected by a target. |

Future profiles:

- timeline;
- author/principal view;
- risk cluster;
- stale context view;
- skill extraction candidate view.

## Rollout Plan

### Phase 0: Research And Boundary Record

Status: this planning pass.

Goal: record open-source reuse candidates, product boundary, and P2 priority
without authorizing implementation.

Acceptance evidence:

- this plan exists;
- external-brain review bundle passes validation;
- web AI review gives GO, CONDITIONAL PASS with accepted edits, or BLOCKED with
  concrete P0 issues;
- master plan references this only as a deferred module.

### Phase 1A: Graph Projection Contract Fixture

Status: deferred until the review-governance kernel Phase 1A and basic
projection derivation pass.

Goal: prove a graph projection can represent governed facts without creating
new authority.

Allowed outputs:

- one fixture contract or schema fragment under review-governance examples;
- one valid fixture;
- negative fixtures showing forbidden authority and privacy shortcuts;
- focused tests.

Suggested public surface:

```text
schemas/examples/review-governance/graph-projection-valid.json
schemas/examples/review-governance/graph-projection-invalid-decision-from-annotation.json
schemas/examples/review-governance/graph-projection-invalid-forbidden-export.json
schemas/examples/review-governance/graph-projection-invalid-run-success-completion.json
schemas/examples/review-governance/graph-projection-invalid-inferred-edge-as-source-truth.json
schemas/examples/review-governance/graph-projection-invalid-graph-store-authority.json
schemas/examples/review-governance/graph-projection-invalid-graph-driven-code-change.json
packages/control-plane/tests/test_graph_projection_contract.py
```

No UI. No graph database. No auto-extraction. No writeback.

If a schema fragment is needed, it must serve review-governance packet
validation. It must not become an independent graph platform schema family.

Acceptance evidence:

- valid graph fixture maps to existing DevFrame objects;
- annotation cannot become a decision;
- inferred edge cannot become source truth;
- graph database, Joern, GraphRAG, or code-graph output cannot become
  source-truth or decision authority;
- graph edge or proposal cannot directly trigger code edits or acceptance;
- run success cannot be projected as completion without gate decision;
- forbidden privacy nodes fail export validation;
- projection status remains derived from decisions and evidence.

### Phase 1B: Graph Slice Builder

Status: deferred until Phase 1A passes.

Goal: generate a small read-only graph slice from explicit source inputs.

Allowed inputs:

- docs map;
- master plan;
- review-governance fixtures;
- methodology skills registry;
- external-brain bundle manifest;
- code/module references from existing indexes or explicit source lists.

Existing indexes are read-only inputs and must not trigger repo-wide extraction
or code edits.

Allowed outputs:

- `graph_projection.json`;
- `graph_projection_summary.md`;
- omitted-neighbor summary;
- privacy summary.

Stop line: do not scan a whole private vault, browser profile, or arbitrary
filesystem tree.

### Phase 1C: Context Selection Integration

Status: deferred until Phase 1B passes.

Goal: let context packet preparation use a graph neighborhood as an explicit
context seed.

Acceptance evidence:

- selected graph nodes become cited context candidates;
- omitted high-impact neighbors appear in the context ledger;
- low-authority inferred edges are marked as assumptions;
- external-brain bundle preparation can cite the graph slice without treating it
  as complete context.

### Phase 2: Read-Only Visual Graph

Status: deferred until graph slices are useful.

Goal: provide a human UI for search, zoom, pan, filter, select, and inspect.

Reuse direction:

- React Flow when editing-oriented node UI is the immediate need;
- Cytoscape.js when graph exploration and layout variety are more important;
- sigma.js when graph size exceeds DOM-oriented rendering;
- JSON Canvas export for Obsidian-compatible human review.

Acceptance evidence:

- local launch path opens the graph without special setup;
- browser acceptance covers desktop and narrow viewport;
- nodes and labels do not overlap incoherently in default fixture;
- filtering by authority and privacy class works;
- details panel shows source refs and evidence refs;
- UI remains read-only for source facts.

### Phase 3: Human Annotation

Status: deferred until read-only UI is accepted.

Goal: allow annotations and proposed relationship changes without direct source
mutation.

Acceptance evidence:

- annotations become artifacts or proposals;
- proposed edge changes are visibly not accepted facts;
- accepting a proposal requires a governed decision;
- rejected or stale annotations remain traceable.

### Phase 4: Domain Expansion

Status: deferred until annotation flow is safe.

Candidate expansions:

- Paper KB claim maps;
- code impact graph;
- external-brain bundle coverage graph;
- skill dependency graph;
- stale-plan/conflict graph;
- onboarding capability map.

Stop line: do not add broad graph storage or real-time collaborative editing
until at least two domain slices prove repeated value.

## First Acceptable Slice

The first acceptable slice after prerequisites is:

```text
graph-projection-contract-v0-under-review-kernel
```

Preconditions:

- review-governance kernel Phase 1A passes;
- basic projection derivation proves projection cannot override decisions;
- external-brain review of this plan is PASS or CONDITIONAL PASS with accepted
  edits.

Allowed files:

```text
schemas/examples/review-governance/graph-projection-valid.json
schemas/examples/review-governance/graph-projection-invalid-decision-from-annotation.json
schemas/examples/review-governance/graph-projection-invalid-forbidden-export.json
schemas/examples/review-governance/graph-projection-invalid-run-success-completion.json
schemas/examples/review-governance/graph-projection-invalid-inferred-edge-as-source-truth.json
schemas/examples/review-governance/graph-projection-invalid-graph-store-authority.json
schemas/examples/review-governance/graph-projection-invalid-graph-driven-code-change.json
packages/control-plane/tests/test_graph_projection_contract.py
```

Forbidden in the first slice:

- UI;
- graph database;
- whole-repo automatic extraction;
- Paper KB ingestion;
- Obsidian writeback;
- browser submission;
- skill promotion;
- code edits based on graph output;
- external library vendoring.

Must pass:

- valid graph projection maps to existing DevFrame objects;
- graph projection is stored as `Artifact(kind=graph_projection)` or nested
  `projection.graph`, not a new top-level governance object;
- nodes and edges carry source refs, authority level, privacy class, evidence
  refs, decision refs, provenance, freshness, and confidence;
- projection status is derived from backend decisions and evidence.

Must fail:

- annotation becomes `Decision`;
- inferred edge becomes `source_truth`;
- layout preference mutates source facts;
- run success becomes work item completion without a gate decision;
- forbidden privacy node or edge is exported;
- graph database, Joern, GraphRAG, or code-graph output is treated as DevFrame
  authority;
- graph slice triggers code edits or acceptance;
- external review feedback becomes final decision;
- graph projection introduces a new top-level governance object.

## External Review Questions

Ask the external brain:

1. Is the module placed at the correct layer: Projection plus Context Selection,
   not governance authority?
2. Is P2 the right priority, after review-governance kernel and basic
   projection derivation?
3. Does the plan reuse mature open-source graph/canvas/code-graph tooling
   without letting tools own DevFrame authority?
4. Is the first acceptable slice small enough?
5. Are the privacy, source-truth, annotation, and decision boundaries strong
   enough?
6. Should this be linked from the master plan as a deferred module?
7. What P0 issues must be fixed before it is kept in the public planning set?

Expected verdict:

```text
A. Context audit
B. Overall verdict: PASS / CONDITIONAL PASS / BLOCKED
C. GO / NO-GO for master plan deferred-module reference
D. GO / NO-GO for first acceptable graph-projection contract slice
E. Remaining P0
F. Remaining P1
G. Smallest acceptable first slice
```
