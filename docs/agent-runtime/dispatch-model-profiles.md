# Dispatch Model Profiles -- RD2100 Agent Runtime

> 2026-05-28 | Purpose: Document practical limits of each model used in SADP dispatch.
> Update when: New model tested, existing model behavior changes, new failure pattern discovered.

---

## Quick Reference (for agent before dispatch)

| If task involves... | Use | Max files/batch |
|---------------------|-----|:---:|
| **Audit / review tasks** | `deepseek-v4-pro` | 2 (report + 1 source) |
| .md files only, <=2 files | `deepseek-v4-pro` | 2 |
| .md files, 3-5 files | `deepseek-chat` | 5 |
| .ps1 / .py / code files | `deepseek-chat` or Codex direct | 1 |
| 6+ files of any type | Codex direct (grep/shell) | unlimited |
| Tool-heavy operations (init, create) | Skip dispatch, Codex direct | unlimited |
| Narrow single-file public-surface edit (post-TaskSpec) | `stepfun/step-3.7-flash` | 1 |

**Audit dispatch**: Always use `deepseek-v4-pro --model deepseek/deepseek-v4-pro`. Audits read only the report + at most 1 source file for cross-check. Audit quality > speed.

---

## deepseek/deepseek-v4-pro

- **Provider**: DeepSeek (your API key)
- **Cost**: ~$0.00016/simple task
- **Strengths**: Fast simple replies, concise output, low cost
- **Limitations**:
  - NO: Max 2 `.md` files per dispatch (tool-call timeout ~15s)
  - NO: Cannot handle `.ps1`/`.py` (Read tool times out on files >100 lines)
  - NO: Multi-file prompts (3+) hang at 30s
  - NO: `agent create` tool hangs indefinitely
  - NO: `--add-dir` flag not supported by `opencode run`
- **Full pass rate**: 4/8 tasks (50%) -- file size sensitive
- **Best for**: Quick single-file reads, simple code generation, "say hi" validation

## deepseek/deepseek-chat

- **Provider**: DeepSeek (your API key)
- **Cost**: ~$0.002/task (10x v4-pro but more capable)
- **Strengths**: Handles .ps1 files, multi-file prompts, tool calling
- **Limitations**:
  - WARN: Higher cost per task
  - WARN: Slower responses (15-20s vs v4-pro 5-10s)
- **Full pass rate**: 5/5 tasks (100%)
- **Best for**: Multi-file audits, code file reading, complex tool operations

## stepfun/step-3.7-flash

- **Provider**: StepFun (opencode built-in)
- **Cost**: Included with opencode runtime
- **Strengths**: Narrow single-file edits, public-surface markdown/code maintenance, fast iteration after TaskSpec is written
- **Observed successful run**: Edited `scripts/verify-control-plane-wheel.ps1` through `opencode run -m stepfun/step-3.7-flash --agent build`
- **Limitations**:
  - NO: External temp evidence directory writes may be blocked by `external_directory` permission checks
  - WARN: Use only for narrow single-file public-surface edits; broader work should go to `deepseek-chat` or Codex direct
- **Best for**: Single-file public-surface edits after TaskSpec is written

## opencode build agent

- **Permissions**: bash, read, edit, glob, grep, webfetch, task, todowrite, websearch, lsp, skill
- **Limitations**:
  - NO: No `--add-dir` support in `opencode run`
  - NO: `agent create` hangs (generates config via model call)
  - WARN: Filesystem access requires explicit absolute paths
  - WARN: Desktop app conflicts with CLI dispatch (process lock)

## Codex Goal Agent (direct)

- **Strengths**: Native file reading, grep, shell, no tool-call timeout
- **Best for**: Large file audits, batch operations, PS1/Python analysis
- **SADP role**: Planning, evaluation, and tasks exceeding dispatch model limits

---

## Failure Pattern Library

| Pattern | Symptom | Models affected | Mitigation |
|---------|---------|:---:|------------|
| Desktop app conflict | All dispatches 30s timeout | All | Close opencode desktop before CLI dispatch |
| PS1 file timeout | No output, 30s wall time | v4-pro | Use chat model or Codex direct |
| Multi-file overload | 3+ files -> hang | v4-pro | Limit to 2 files/batch |
| Tool creation hang | "Generating..." endless loop | v4-pro | Skip `agent create`, use `build` |
| Large prompt | No output, immediate timeout | v4-pro | Keep prompt <500 chars, files <5KB |
| External evidence-dir write blocked | Executor cannot write to temp evidence path | step-3.7-flash | Orchestrator captures stdout/stderr and creates SADP evidence files |

---

> **Update log**: 2026-06-23 -- Added `stepfun/step-3.7-flash` profile for narrow single-file post-TaskSpec edits; added external evidence-dir permission failure pattern.
