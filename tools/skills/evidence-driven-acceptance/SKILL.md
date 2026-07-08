---
name: evidence-driven-acceptance
description: Evidence-driven acceptance workflow. Use when user says "@evidence", "@acceptance", "验活", "证据化验收", "评价这个交付", "看这个截图有没有公信力", "判断模型有没有真干活", or when reviewing long-context coding tasks, model benchmark outputs, multi-agent handoffs, safety/privacy boundary work, product release evidence, screenshots plus written evaluations, or any delivery where claims must be checked against runnable evidence.
---

# evidence-driven-acceptance - Evidence-Driven Acceptance

Role: methodology skill, not a runtime executor. Use it to decide whether a delivery is real, runnable, trustworthy, and worth accepting.

The core idea is simple: do not trust a polished report by itself. Check whether the work can prove itself.

## Six Acceptance Questions

Every review must answer these six questions:

1. **Did it read the right context?**
   Check task docs, corpus packs, schemas, rules, prompts, source files, context coverage ledgers, and stated constraints. Treat "I read it" as weak unless exact files or coverage evidence are listed.

2. **Did it produce real artifacts?**
   Look for changed code, tests, schemas, fixtures, verifier scripts, manifests, matrices, screenshots, logs, or handoff files. Separate implementation artifacts from summary-only artifacts.

3. **Did it run?**
   Prefer command output, test logs, schema validation, smoke tests, runtime probes, or reproducible scripts. A claim without an observable result is not enough.

4. **Did it test bad cases?**
   Look for negative coverage: missing files, invalid schema, blocked-as-pass, fake green, duplicate IDs, wrong project IDs, permission failures, privacy leaks, unsafe writes, stale evidence, forged results, and environment failures.

5. **Do the evidence files agree?**
   Cross-check report claims against actual paths, counts, manifest entries, failure matrix rows, reviewer index, terminal logs, and screenshots. Flag mismatched counts or missing files.
   Also check whether verifier logic uses real schema fields and source paths. A verifier that invents field names or validates non-existent properties is weak evidence even if it reports PASS.

6. **Is it connected to the real path?**
   Distinguish production-integrated work from synthetic labs, fixtures, mocks, manual-only screenshots, and evidence-only packages. Lab work can be valuable, but it must not be scored as final production acceptance.

## Evidence Tiers

Classify evidence before scoring:

| Tier | Meaning |
|---|---|
| Strong | Production path touched, commands run, tests pass, negative cases hit real code paths, manifest paths exist, caveats are explicit. |
| Medium | Lab or fixture coverage is meaningful, tests run, matrix is coherent, but integration or runtime proof is partial. |
| Weak | Mostly narrative, screenshots without commands, unverified context claims, missing reviewer index, broad PASS claims with thin artifacts. |
| Risk | Report contradicts files, final verdict hides blockers, tests are not runnable, production path is untouched, or sensitive-data boundaries are unclear. |

## Batch Output Review

When the evidence comes as many ZIPs or repeated model outputs:

1. **Pick the latest comparable package first.**
   If files have suffixes like `(1)`, `(2)`, `(3)`, treat the latest timestamp as the active candidate. Keep older packages as iteration history, not final evidence.

2. **Group by task and model.**
   Compare like with like: same task ID, same model name, same round. Do not mix a first-round package with another model's continuation round.

3. **Do not score by ZIP size or file count.**
   Large packages can be bloated with copied corpus, duplicated reports, generated fixtures, or full source snapshots. Smaller packages can be stronger if they contain focused verifier output, real artifacts, and a clean reviewer index.

4. **Open the reviewer route first.**
   Prefer files named `reviewer-index`, `final-report`, `final-verdict`, `verification-commands`, `evidence-manifest`, `zip-contents-audit`, `context-coverage-ledger`, and `failure-matrix`. These files usually tell the reviewer where the real proof should be.

5. **Check package hygiene.**
   A strong package should state what is intentionally included and excluded. Give extra credit for zip contents audit, whitelist packaging, no `.git`, no `node_modules`, no secrets, no unrelated corpus padding, and exact generated artifact paths.

6. **Treat final verdict as a claim, not proof.**
   `PASS`, `ACCEPT`, or `COMPLETE` only matters after tests, schema validation, failure cases, real-path links, and package audit agree with it.

## High-Value Signals From Test Results

Upgrade confidence when the package shows:

- Context consumption with exact corpus files, source paths, rule IDs, or line references.
- Real generated artifacts saved under explicit paths, not just synthetic examples.
- Schema validation against actual schema files, with `additionalProperties` and exact field names enforced.
- Failure matrix rows mapped to concrete tests or fixture verdicts, not just listed as categories.
- Negative fixtures that produce expected BLOCKED/FAIL outcomes, not only clean PASS cases.
- Command logs with exit codes, not just prose summaries.
- Reviewer focus items that point to exact files a human can re-check.
- Known gaps that are specific and bounded, such as manual-only screenshots, lab-only coverage, missing production integration, or environment limits.

Downgrade confidence when the package shows:

- Invented schema fields, renamed concepts, or verifier checks that do not match the real source.
- Repeated evidence files that inflate counts without adding distinct proof.
- Context claims without exact corpus citations.
- Large fixture labs with weak production integration.
- Screenshots or reports that contain human scoring text instead of natural development evidence.
- A clean final verdict that hides residual blockers, manual gates, or conditional context requirements.

## Screenshot Evidence Guidance

When preparing or judging screenshots:

- Show real paths, file tabs, command outputs, test counts, schema results, manifest counts, and known caveats.
- Use green only for concrete passes: files present, tests passed, schema valid, failure rows covered.
- Use red only for concrete gaps: missing files, not integrated, manual-only, failed command, conditional pass, unresolved reviewer gate.
- Keep most of the screen as normal development text. Avoid large decorative red/green blocks.
- Do not put human scoring text, star ratings, or form-style comments inside the simulated development screenshot.
- Prefer source/test evidence in the main panes, terminal verification below, and a real file tree or task path visible.

## Human Evaluation Template

When the user needs form-ready Chinese evaluation text, use this structure:

```text
截图概要：
说明这个交付实际做了什么，列出最有公信力的证据，不评价截图是否好看。

质量评价：
从验收角度判断它是否扎实。说清楚它是生产集成、实验室成果、证据包，还是条件性通过。

评分：X.X星

交付效率评价：
评价项目本身的交付效率和后续返工/审核成本，不评价图片清不清楚。

评分：X.X星
```

Use human reviewer language: concrete, slightly subjective, and evidence-backed. Avoid robotic phrases such as "完全符合预期" unless the evidence really supports them.

## Scoring Heuristics

| Score | Meaning |
|---|---|
| 8.0-9.0 | Production path is integrated, tests and negative cases are strong, evidence is complete, caveats are minor. |
| 7.0-7.9 | Useful and mostly credible, but has integration, environment, or reviewer-gate gaps. |
| 6.0-6.9 | Meaningful work exists, but it is lab-only, conditional, thinly packaged, or likely to need follow-up. |
| Below 6.0 | Hard to trust, mostly narrative, missing runnable proof, or important claims do not match artifacts. |

Do not give similar scores to every model/package if the evidence quality differs. Make the ranking visible in the language.

## Reviewer Stance

Prefer honest, bounded phrases:

- "在现有证据下，我倾向认可..."
- "它的问题不在工作量，而在..."
- "我不会把它判成失败，但也不会当成最终生产验收。"
- "这版更适合证明...，不适合包装成..."

Final verdicts must keep the boundary clear: real work can still be partial, and partial work can still be valuable.
