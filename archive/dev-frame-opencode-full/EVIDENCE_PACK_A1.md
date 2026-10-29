# Evidence Pack: PAPER-CONTEXT-CONTRACTS-A1

REVIEW_RUN_ID: paper-context-contracts-a1-v1-20260611

## 1. Task Summary

为 Obsidian + Zotero + RAG + paper workflow 的高水平落地建立第一层工程边界。本轮只新增 paper domain 与 context layer 的 contract、schema、设计文档和 dry-run fixture，不实现完整 RAG，不迁移 WriteLab，不重构主 workflow。

## 2. Files Read

| File | Purpose |
|---|---|
| `D:\dev-frame-opencode\AGENTS.md` | Project state: PRODUCTION PROMOTED |
| `D:\dev-frame-opencode\CLAUDE.md` | Monorepo overview: codegraph + ai-workflow-hub + ai-workflow-hub-e2e |
| `D:\dev-frame-opencode\CURRENT_ROUTE.json` | Routing decisions, blocked items |
| `D:\dev-frame-opencode\ai-workflow-hub\src\ai_workflow_hub\workflows\coding_graph.py` | LangGraph StateGraph (7 nodes, 5 routers) |
| `D:\dev-frame-opencode\ai-workflow-hub\src\ai_workflow_hub\schemas.py` | WorkflowState, TaskEntry, Pydantic models |
| `D:\dev-frame-opencode\ai-workflow-hub\src\ai_workflow_hub\task_spec_adapter.py` | SADP TaskSpec adapter |
| `D:\dev-frame-opencode\ai-workflow-hub\src\ai_workflow_hub\acceptance.py` | Acceptance test framework (81.7KB) |
| `D:\writelab\cssci_writing_lab_design_doc.md` | WriteLab design doc (37.7KB, 23 sections) |
| `D:\writelab\backend\app\core\llm_gateway.py` | LLM Gateway + rule fallback (12.3KB) |
| `D:\writelab\backend\app\analyzers\expression_detector.py` | 21 template patterns (6.1KB) |

## 3. Files Added

### Architecture Documents (3 files)

| File | Size | Content |
|---|---|---|
| `docs/paper/PAPER_DOMAIN_ARCHITECTURE.md` | ~24KB | Paper domain 与 workflow core / WriteLab / Obsidian / Zotero / RAG 的关系，contract-first 原因，A1-A8 路线图，human_required 场景，privacy 边界 |
| `docs/context-layer/CONTEXT_LAYER_ARCHITECTURE.md` | ~20KB | Memory Files / Obsidian Sources / Zotero / RAG / Vector Index / Context Pack / Evidence Pack / 分级策略 / 数据流总览 / 实施优先级 |
| `docs/paper/WRITELAB_ADAPTER_PLAN.md` | ~15KB | WriteLab 独立项目策略，4 阶段 adapter 规划，字段映射表，文件映射表，schema validation dry-run |

### Schema Files (7 files)

| File | Title | Required Fields |
|---|---|---|
| `ai-workflow-hub/src/ai_workflow_hub/domains/paper/contracts/paper_task_spec.schema.json` | PaperTaskSpec | 6 |
| `ai-workflow-hub/src/ai_workflow_hub/domains/paper/contracts/paper_context_pack.schema.json` | PaperContextPack | 5 |
| `ai-workflow-hub/src/ai_workflow_hub/domains/paper/contracts/paper_review_issue.schema.json` | PaperReviewIssue | 5 |
| `ai-workflow-hub/src/ai_workflow_hub/domains/paper/contracts/paper_acceptance_result.schema.json` | PaperAcceptanceResult | 5 |
| `ai-workflow-hub/src/ai_workflow_hub/domains/paper/contracts/paper_evidence_manifest.schema.json` | PaperEvidenceManifest | 5 |
| `ai-workflow-hub/src/ai_workflow_hub/domains/paper/contracts/obsidian_note_metadata.schema.json` | ObsidianNoteMetadata | 4 |
| `ai-workflow-hub/src/ai_workflow_hub/domains/paper/contracts/zotero_reference_metadata.schema.json` | ZoteroReferenceMetadata | 5 |

### Fixture Files (7 files)

| File | Size | Format | Schema Validated |
|---|---|---|---|
| `ai-workflow-hub/src/ai_workflow_hub/domains/paper/fixtures/paper_task_spec.sample.yaml` | 869B | YAML | PASS |
| `ai-workflow-hub/src/ai_workflow_hub/domains/paper/fixtures/obsidian_literature_note.sample.md` | 940B | Markdown+YAML | PASS |
| `ai-workflow-hub/src/ai_workflow_hub/domains/paper/fixtures/obsidian_bad_example.sample.md` | 914B | Markdown+YAML | PASS |
| `ai-workflow-hub/src/ai_workflow_hub/domains/paper/fixtures/obsidian_writing_rule.sample.md` | 817B | Markdown+YAML | PASS |
| `ai-workflow-hub/src/ai_workflow_hub/domains/paper/fixtures/zotero_reference.sample.json` | 615B | JSON | PASS |
| `ai-workflow-hub/src/ai_workflow_hub/domains/paper/fixtures/paper_context_pack.sample.json` | 1819B | JSON | PASS |
| `ai-workflow-hub/src/ai_workflow_hub/domains/paper/fixtures/paper_acceptance_result.sample.json` | 1018B | JSON | PASS |

### Validation Script (1 file)

| File | Purpose |
|---|---|
| `scripts/validate_paper_contract_fixtures.py` | Schema validation + privacy check for all fixtures |

## 4. Files Modified

| File | Change |
|---|---|
| `D:\agent-acceptance\.agent\PROJECT_REGISTRY.json` | Added `dev-frame-opencode` project (active, total_projects: 11) |

## 5. Commands Run

| Command | Result |
|---|---|
| `python scripts/validate_paper_contract_fixtures.py` | ALL PASS (7/7 validated, privacy OK) |
| `python smoke_test.py` | 5/5 PASS (0 errors, 147 core + 216 e2e tests) |

## 6. Validation Results

### Schema Validation

```
--- Schema Files ---
Found 7 schema files
  [OK] obsidian_note_metadata.schema.json (ObsidianNoteMetadata, 4 required)
  [OK] paper_acceptance_result.schema.json (PaperAcceptanceResult, 5 required)
  [OK] paper_context_pack.schema.json (PaperContextPack, 5 required)
  [OK] paper_evidence_manifest.schema.json (PaperEvidenceManifest, 5 required)
  [OK] paper_review_issue.schema.json (PaperReviewIssue, 5 required)
  [OK] paper_task_spec.schema.json (PaperTaskSpec, 6 required)
  [OK] zotero_reference_metadata.schema.json (ZoteroReferenceMetadata, 5 required)

--- Schema Validation ---
  [PASS] paper_task_spec.sample.yaml -> paper_task_spec.schema.json: schema validated
  [PASS] paper_context_pack.sample.json -> paper_context_pack.schema.json: schema validated
  [PASS] paper_acceptance_result.sample.json -> paper_acceptance_result.schema.json: schema validated
  [PASS] obsidian_literature_note.sample.md -> obsidian_note_metadata.schema.json: schema validated
  [PASS] obsidian_bad_example.sample.md -> obsidian_note_metadata.schema.json: schema validated
  [PASS] obsidian_writing_rule.sample.md -> obsidian_note_metadata.schema.json: schema validated
  [PASS] zotero_reference.sample.json -> zotero_reference_metadata.schema.json: schema validated

--- Privacy Check ---
  [PASS] No sensitive content detected in fixtures

RESULT: ALL PASS (7/7 validated, privacy OK)
```

### Smoke Test

```
  #    Command                                  Exit   Status     Key Output
  0    Documentation staleness check            0      PASS       0 errors
  1    Readiness score diagnostic               0      PASS       0 errors
  2    CodeGraph type-check                     0      PASS       0 errors
  3    ai-workflow-hub core state tests         0      PASS       147 passed, 1 skipped
  4    ai-workflow-hub-e2e evidence + gate      0      PASS       216 passed

  Summary: 5 passed, 0 known issues, 0 failed
  Verdict: PASS
```

## 7. Contract Summary

| Contract | Schema Fields | Fixture Coverage | Notes |
|---|---|---|---|
| PaperTaskSpec | 13 props, 6 required | 1 YAML fixture | task_type enum: draft/revise/review/restructure/citation_check/abstract |
| PaperContextPack | 15 props, 5 required | 1 JSON fixture | privacy_filter_result 嵌套结构验证通过 |
| PaperReviewIssue | 8 props, 5 required | Referenced by acceptance result | issue_type enum: structure/argument/citation/expression/format/privacy/methodology |
| PaperAcceptanceResult | 7 props, 5 required | 1 JSON fixture | status enum: accepted/accepted_with_limitation/needs_more_evidence/blocked/human_required |
| PaperEvidenceManifest | 5 props, 5 required | No fixture (structural) | privacy_attestation 三项断言 |
| ObsidianNoteMetadata | 10 props, 4 required | 3 Markdown fixtures | type enum: 6 种笔记类型；chapter 允许 null |
| ZoteroReferenceMetadata | 12 props, 5 required | 1 JSON fixture | item_type enum: 6 种文献类型 |

## 8. Privacy / Safety Checks

| Check | Result |
|---|---|
| No real API keys in fixtures | PASS (regex `sk-[a-zA-Z0-9]{20,}` 无匹配) |
| No real paper full text | PASS (所有 fixture 使用虚构教育学内容) |
| No real author identities | PASS (使用"张明华""李晓红"等虚构名) |
| No OPENCODE_API_KEY / DEEPSEEK_API_KEY 变量名 | PASS |
| No writelab.db 引用 | PASS |
| No real DOI / URL | PASS (使用 example.org 占位) |

## 9. Known Limitations

1. **PaperEvidenceManifest 无 fixture**：该 schema 用于运行时生成，不适合静态 fixture。后续 A2 阶段应补充动态生成测试。
2. **jsonschema Draft 2020-12 的 $ref**：paper_acceptance_result 中内联了 paper_review_issue 的定义（因 file-relative $ref 解析需要 resolver）。后续可引入 schema registry 统一管理引用。
3. **Obsidian / Zotero 解析器未实现**：本轮只有 schema + fixture，没有 Markdown frontmatter parser 和 BibTeX parser。这是 A2 阶段的工作。
4. **Context Pack Builder 未实现**：paper_context_pack.sample.json 是手工构造的静态 fixture，自动化 builder 是 A3 阶段工作。
5. **WriteLab adapter 只有 contract**：实际 API 调用 / CLI 集成是 A5 阶段工作。

## 10. Acceptance Status

**Status: accepted_with_limitation**

**Accepted because:**
- 项目中明确出现 paper domain contract 位置（7 schema + 7 fixture + 1 validator）
- 项目中明确出现 context layer 架构说明（475 行，含数据流图）
- Obsidian + Zotero + RAG 与 workflow 的关系已文档化
- WriteLab 明确定位为外部能力提供方（adapter plan 含字段映射表）
- 7 个 schema 通过 jsonschema Draft 2020-12 验证
- 7 个 fixture 通过 schema 验证
- fixture 不包含真实论文内容、API key、个人隐私
- 验证脚本通过（exit 0）
- smoke test 5/5 PASS，现有 680+ 测试未受影响

**Limitation because:**
- PaperEvidenceManifest 无 fixture（结构性限制，A2 补充）
- schema $ref 采用内联而非引用（工程简化，后续可引入 registry）
- Obsidian/Zotero parser、Context Pack Builder、WriteLab adapter 均为 not_found（属于后续阶段）

## 11. Recommended Next Task

**PAPER-CONTEXT-INGEST-MVP-A2**

目标：读取安全 fixture 中的 Obsidian Markdown / Zotero JSON，生成最小 paper_context_pack。

具体任务：
1. 实现 Markdown + YAML frontmatter parser（读取 obsidian_note_metadata）
2. 实现 BibTeX parser（读取 zotero_reference_metadata）
3. 实现最小 Context Pack Builder（从 parsed notes → paper_context_pack）
4. Privacy filter：排除 sensitive 级内容
5. 验证：fixture 输入 → Context Pack 输出 → schema 验证通过

预计新增文件：
- `src/ai_workflow_hub/context_layer/parsers/obsidian_parser.py`
- `src/ai_workflow_hub/context_layer/parsers/bibtex_parser.py`
- `src/ai_workflow_hub/context_layer/builders/context_pack_builder.py`
- `tests/test_context_layer_parsers.py`
