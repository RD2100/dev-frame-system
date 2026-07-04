# Early Adopter User Asset Governance Plan

Lifecycle state: Draft active planning record

Plan status: Accepted as the early-adopter and user-asset layer for the
document-driven transformation plan. Not yet an implementation claim.

Reader: DevFrame and RDCode maintainers deciding what customization and
extension surface should exist before a broad plugin marketplace.

Post-read action: prioritize import, governance, and reuse of experienced
users' existing work assets before building generic extension APIs.

Related docs: [Document-Driven Transformation Master Plan](document-driven-transformation-master-plan.md), [Reuse-First Constraint Governance Implementation Plan](reuse-first-constraint-governance-implementation-plan.md), [Human Attention Governance And Automation Maturity Plan](human-attention-governance-and-automation-maturity-plan.md), [Review-First Governance Kernel Implementation Spec](review-first-governance-kernel-implementation-spec.md)

## Purpose

New open-source developer tools are usually tried first by experienced users,
not blank-slate beginners.

Those users already have assets:

- skills;
- prompts;
- MCP servers;
- scripts;
- command aliases;
- review checklists;
- evidence routines;
- workflow templates;
- project rules;
- model preferences;
- report templates;
- team operating habits.

RDCode should not ask these users to abandon that work. It should help them
import, classify, constrain, test, share, and improve it.

The first extensibility moat is therefore not a generic plugin marketplace. It
is governed user-asset migration.

## External Lessons

| Source | Lesson for DevFrame/RDCode |
|---|---|
| Eric von Hippel's lead-user work | Early users in fast-moving domains often understand needs before the general market. RDCode should design for advanced users who already invented local workflows. |
| End-user software engineering research | User-created artifacts need support for reuse, testing, debugging, and sharing. RDCode should not merely import scripts; it should govern them. |
| Continue rules and MCP configuration | Coding-agent users already expect project rules and external tools to be configurable. RDCode should make those assets governable and portable. |
| Backstage catalog, templates, and plugins | A developer platform becomes useful when it catalogs software assets and provides templates, not only when it exposes APIs. |
| Node-RED flows and reusable libraries | Power users value reusable flows/functions that can be composed visually or declaratively. RDCode should support reusable workflow assets with guardrails. |
| Dify plugins and reusable workflows | AI workflow platforms gain value when external tools and workflows can be reused. DevFrame should add evidence and decision governance around that reuse. |
| Malleable software thinking | Tools become more valuable when users can reshape them at the point of use. RDCode should enable adaptation without letting customization bypass governance. |

## Core Decision

Prioritize user work assets before generic plugins.

The product should say:

```text
Bring your own skills.
Bring your own prompts.
Bring your own MCP.
Bring your own rules.
Bring your own evidence recipes.
Bring your own workflows.
DevFrame will govern them.
```

This is different from saying every internal API is open. User assets enter
through governed asset types with scope, version, validation, dry-run, and
activation rules.

Governance must not mean asking the user to approve every asset action. The
default should be policy-based activation for routine, low-risk personal use,
with escalation only when the asset changes shared defaults, expands authority,
weakens evidence, or conflicts with higher-priority rules.

## Asset Types

Phase one should recognize these user asset types conceptually, even if only a
small subset is implemented at first.

| Asset type | User value | Governance requirement |
|---|---|---|
| Skill Pack | Reuse personal or team methods | Scope, version, safety notes, evidence expectations |
| Prompt Pack | Reuse proven prompts | Source, model assumptions, intended task kind |
| MCP Tool Connector | Bring existing tools | Capability declaration, permission class, output mapping |
| Command Alias | Keep familiar commands | Must produce governed requests, not final status |
| Rule Pack | Encode project/team constraints | Scope, precedence, activation or adoption rule |
| Workflow Template | Reuse process patterns | Required context, evidence, decisions, stop lines |
| Context Profile | Standardize what to retrieve | Source refs, freshness, forbidden context |
| Evidence Recipe | Standardize proof collection | Commands, artifacts, freshness, expected claims |
| Report Template | Preserve delivery habits | Must cite evidence and decisions |
| Model/Agent Profile | Route work to preferred executors | Advisory only; cannot override gates |

## Asset Lifecycle

User assets should move through this lifecycle:

```text
Import
  -> classify
  -> quarantine/draft
  -> validate shape
  -> dry-run
  -> scope
  -> enable under policy for personal/project/team use
  -> observe outcomes
  -> propose promotion
  -> adopt/supersede/archive by policy or human decision
```

Do not let imported assets become active authority immediately. Low-risk
personal assets may become active under policy after validation and dry-run.
Project, team, and organization defaults need stronger evidence and an explicit
adoption path, which may be automated only when the policy already defines that
path.

## Scope And Precedence

Use this precedence order:

```text
organization policy
  > project policy
  > team asset
  > personal asset
  > temporary command/session override
```

Personal customization should improve fit, but it must not silently weaken
project or organization rules.

## Import UX

The import path should be friendly to experienced users:

1. user points RDCode at a folder, config, MCP definition, prompt file, or skill
   directory;
2. RDCode classifies likely asset type;
3. RDCode marks unknown or risky fields;
4. user supplies only missing required metadata;
5. asset starts in draft or quarantine;
6. dry-run shows what the asset would do;
7. low-risk personal enablement can proceed under policy;
8. shared/default enablement requires the right scope, evidence, and activation
   or adoption rule.

This avoids making experienced users write a large manifest before the system
has even inspected their assets.

## Minimal Manifest Shape

Every governed asset should eventually expose:

```json
{
  "asset_id": "string",
  "asset_type": "skill_pack",
  "display_name": "string",
  "version": "string",
  "scope": "personal|project|team|organization",
  "owner_principal_id": "string",
  "capabilities": [],
  "required_context": [],
  "required_evidence": [],
  "risk_level": "low|medium|high",
  "status": "draft|quarantined|enabled|disabled|adopted|superseded",
  "activation_mode": "manual|policy|blocked",
  "source_ref": "string"
}
```

This is a conceptual manifest, not yet a schema commitment.

## Relationship To Existing Object Model

Do not add a new top-level governance object in phase one.

Represent user assets as:

- `Artifact` when imported or captured;
- `DocumentRevision` when promoted into durable rules/templates/docs;
- `Decision(kind=adopt)` when made authoritative beyond routine policy scope;
- `Evidence` when dry-run or usage proves behavior;
- projection data when RDCode displays asset state.

If user assets later need independent lifecycle, fact source, and authority
boundary, the top-level object admission test can be reopened.

## What To Build First

Do not build a plugin marketplace first.

Phase one must not build a user-asset system.

The only allowed phase-one user-asset work is a placeholder fixture for one of:

- `evidence_recipe`;
- `review_checklist`.

That placeholder may be represented through existing phase-one objects. Do not
create an asset registry, asset lifecycle manager, MCP execution path, team-wide
enablement flow, marketplace, or workflow-template runtime in phase one.

The first user-asset work should be:

1. document the asset types and lifecycle;
2. add one fixture for an `evidence_recipe` or `review_checklist` after the
   review kernel exists;
3. validate scope and status;
4. show imported asset state in projection;
5. require a policy or adoption decision before project/team default use.

The first useful user story is:

```text
As an experienced user,
I can import my existing review checklist or evidence recipe,
see it classified as a draft asset,
dry-run it against a review work item,
enable it personally when policy allows,
and promote it to a project/team default only through a policy or adoption
decision.
```

## What Not To Build First

Do not start with:

- public plugin marketplace;
- arbitrary extension API;
- remote code execution;
- asset registry;
- asset lifecycle service;
- MCP connector execution;
- workflow template runtime;
- one-click team-wide asset adoption;
- UI-only asset enablement;
- marketplace ratings;
- cloud account system;
- automatic import of every local script.

These may matter later, but they are not the first moat.

## Product Positioning

Avoid positioning RDCode as another blank AI IDE.

Better positioning:

```text
RDCode is a governed shell for your existing AI development workflow assets.
Bring your skills, prompts, MCP tools, rules, evidence recipes, and workflows.
DevFrame turns them into scoped, testable, reviewable automation.
```

This fits early adopters who already have workflows and want better control.

## Impact On Review-First Kernel

The review-first kernel should not implement the full asset system.

It should leave room for it by:

- treating report templates and evidence recipes as future artifacts;
- keeping projection read-only;
- requiring policy or adoption decisions for defaults;
- preserving scope and principal identity;
- validating that customization cannot complete work without evidence and gate
  decision.

## Stop Lines

Stop and revise if:

- "customization" means arbitrary code with no scope or dry-run;
- imported user assets bypass evidence or decisions;
- personal preferences override project rules;
- plugin-marketplace work starts before governed import works;
- assets become team defaults without policy or adoption decision;
- routine low-risk personal assets require repeated human approval even after
  policy, validation, and dry-run allow them.
- phase-one work expands from a single `evidence_recipe` or `review_checklist`
  placeholder into a general asset system.

## Summary

Early adopters bring accumulated workflow capital.

RDCode's moat is not merely extensibility. It is the ability to transform that
workflow capital into governed, reusable, evidence-backed project assets.
