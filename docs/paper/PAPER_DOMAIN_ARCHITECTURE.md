# Paper Domain Architecture

> 阶段：contract-first 设计 | 日期：2026-06-11 | 作者：RD
> 状态：Phase 1 contract 已冻结（7 schema + 7 fixture），尚未进入 runtime

---

## 1. paper domain 与 workflow core 的关系

### 1.1 workflow core 现状（coding domain）

ai-workflow-hub 中已有完整的 coding domain 实现，基于 LangGraph StateGraph 构建：

**状态图定义**（`coding_graph.py`，10.0 KB）：
- 7 个节点：`plan_auditor_node` / `human_gate_node` / `execute_node` / `test_node` / `reviewer_node` / `fix_node` / `final_node`
- 5 个路由函数：`_plan_auditor_route` / `_human_gate_route` / `_side_effect_route` / `_test_route` / `_reviewer_route`
- 入口：`plan_auditor_node` -> 路由 -> `human_gate_node` -> 路由 -> `execute_node` -> ...
- 决策文件驱动的可干预 pipeline（`decisions/human-gate.json`、`decisions/fix-before-round-{N}.json`、`decisions/fix-control.json`）

**核心基础设施**：

| 组件 | 文件 | 说明 |
|------|------|------|
| TaskSpec adapter | `task_spec_adapter.py` (1.1 KB) | @go TaskSpec -> ai-workflow-hub 任务格式转换 |
| ExecutionReport adapter | `execution_report_adapter.py` (2.0 KB) | run evidence -> @go ExecutionReport 格式 |
| Acceptance Gate | `acceptance.py` (81.7 KB) | 验收门禁：多阶段审查、evidence 验证、gate 裁定 |
| Issue Ledger | `issue_ledger.py` (3.9 KB) | P0/P1 问题跨 run 追踪，JSON 持久化 |
| Human Gate | `nodes/human_gate.py` (9.7 KB) | 人工审批门：pending/approved/rejected 状态机 |
| Safety Checks | `safety.py` (9.4 KB) | 安全检查：路径边界、危险变更检测 |
| Policy Gate | `policy_gate.py` (3.1 KB) | 策略门：统一检查 push/pr/deploy 等高风险动作 |
| Run Governance | `run_governance.py` (4.4 KB) | 审计链、evidence 状态、chain-of-custody |
| WorkflowState | `schemas.py` (6.3 KB) | Pydantic 状态模型，贯穿所有节点 |
| Run Decisions | `run_decisions.py` (4.6 KB) | 决策文件读写、状态判定 |

### 1.2 paper domain 定位

paper domain 是一个**新域**，与 coding domain **并行存在**，不替代 coding domain。

```
dev-frame-opencode / ai-workflow-hub
  |
  +-- workflows/
  |     +-- coding_graph.py          # coding domain 状态图
  |     +-- (future: paper_graph.py) # paper domain 状态图
  |
  +-- domains/
  |     +-- paper/
  |           +-- contracts/          # 7 个 JSON Schema（已冻结）
  |           +-- fixtures/           # 7 个 sample fixture（已冻结）
  |
  +-- nodes/                          # coding domain 节点
  +-- schemas.py                      # coding domain WorkflowState
  +-- acceptance.py                   # coding domain Acceptance Gate (81.7 KB)
  +-- issue_ledger.py                 # coding domain Issue Ledger
  +-- safety.py                       # coding domain Safety
  +-- policy_gate.py                  # coding domain Policy Gate
  +-- run_governance.py               # coding domain Run Governance
```

### 1.3 复用关系

paper domain 复用 workflow core 的以下基础设施，但通过独立的 paper-specific 节点和 schema 实现领域逻辑：

| 基础设施 | 复用方式 |
|---------|---------|
| StateGraph 模式 | paper_graph.py 将采用与 coding_graph.py 相同的 LangGraph StateGraph 构建方式，但使用 PaperWorkflowState |
| Evidence 收集 | 复用 evidence 收集模式（collector + formatters），但 paper evidence 包含 context pack、diagnosis report 等 |
| Acceptance Gate | 复用 acceptance 多阶段审查框架，但 paper acceptance 检查结构/论证/引用/表达/隐私 |
| Issue Ledger | 复用 P0/P1 issue 追踪模式，但 paper issue 类型包含 structure/argument/citation/expression/format/privacy/methodology |
| Human Gate | 复用 pending/approved/rejected 状态机，但 paper human gate 触发条件不同 |
| Policy Gate | 复用策略检查模式，但 paper 策略包含隐私审查、文献引用验证等 |

### 1.4 paper domain 独有概念

以下概念只存在于 paper domain，coding domain 中没有对应物：

- **PaperTaskSpec**：包含 paper_type、target_journal、chapter、section、input_policy、confidentiality
- **PaperContextPack**：包含 project_memory、writing_rules、forbidden_patterns、retrieved_literature、privacy_filter_result
- **ObsidianNoteMetadata**：literature_note / writing_rule / bad_example / style_example / revision_history
- **ZoteroReferenceMetadata**：citekey / authors / publication / item_type / doi / citation_allowed
- **PaperReviewIssue**：issue_type 枚举为 structure / argument / citation / expression / format / privacy / methodology
- **PaperAcceptanceResult**：reviewer 枚举为 deterministic_gate / gpt / human / writelab_adapter
- **PaperEvidenceManifest**：包含 privacy_attestation（no_full_text / no_api_keys / no_personal_identity）

---

## 2. paper domain 与 WriteLab 的关系

### 2.1 WriteLab 现状

WriteLab（`D:\writelab`）是独立项目，技术栈与 dev-frame-opencode 完全不同：

| 层 | 技术 | 说明 |
|---|------|------|
| 后端 | FastAPI (`backend/app/main.py`, 2.6 KB) | Python Web 框架 |
| 前端 | Next.js (`frontend/`) | React SSR 框架 |
| 数据库 | SQLite (`core/database.py`, 454 B) | 本地持久化 |
| LLM | DeepSeek (`core/llm_gateway.py`, 15.1 KB) | OpenAI-compatible API + 确定性规则 fallback |
| 打包 | PyInstaller (`packaging/launcher.py`, 4.1 KB) | 本地 exe 分发 |

**已实现能力**：

| 能力 | 文件 | 状态 |
|------|------|------|
| 21 类表达检测规则 | `analyzers/expression_detector.py` (7.3 KB) | 已实现 |
| 段落诊断（LLM + 规则 fallback） | `core/llm_gateway.py` + 11 种段落功能类型 | 已实现 |
| 论证链分析 | `analyzers/argument_chain.py` | 已实现 |
| 功能分类 | `analyzers/function_classifier.py` | 已实现 |
| 引用适配检查 | `analyzers/citation_fit.py` | 已实现 |
| 项目管理 | `api/projects.py` + `models/project.py` | 已实现 |
| 段落管理 | `api/paragraphs.py` + `models/paragraph.py` | 已实现 |
| 诊断报告 | `api/reports.py` (6.2 KB) + `models/report.py` | 已实现 |
| 诊断 schema | `schemas/diagnosis.py` (2.4 KB) | 已实现 |
| 改写 schema | `schemas/rewrite.py` | 已实现 |
| 版本 schema | `schemas/version.py` | 已实现 |
| Metadata handoff ZIP 导出 | `services/writelab_handoff_exporter.py` (7.3 KB) | 已实现 |
| 隐私安全 attestation | handoff exporter 内置 | 已实现 |

**表达检测 21 类规则明细**（`expression_detector.py`）：

W1 阶段（11 类）：是否结构、不是而是结构、若则结构、一方面另一方面结构、既又结构、不仅更结构、从到结构、关键在于、有必要、应当表达、需要表达。

W2 阶段（10 类）：政策套话\_贯彻、政策套话\_推进、空泛因果、万能转折、概念堆叠、路径空转、意义拔高、主体缺失、否定铺陈、抽象名词密度检测。

### 2.2 第一阶段不合并 WriteLab

第一阶段不将 WriteLab 代码合入 dev-frame-opencode。只定义 adapter contract，使 WriteLab 作为"写作诊断能力提供方"通过标准化接口接入。

**接入方式**（三选一，按优先级）：

1. **API 接入**：WriteLab FastAPI 作为本地服务运行，paper domain 通过 HTTP 调用 `/api/analysis`、`/api/paragraphs`、`/api/reports` 等端点
2. **CLI 接入**：WriteLab 打包为 exe/CLI，paper domain 通过 subprocess 调用，解析 JSON/YAML 输出
3. **Metadata handoff ZIP**：WriteLab 导出 metadata-only ZIP（`WRITELAB_HANDOFF.yaml` + `DIAGNOSIS_RESULT.json` + `PRIVACY_ATTESTATION.yaml` + `PACK_MANIFEST.md`），paper domain ingest 该 ZIP

### 2.3 handoff ZIP 隐私设计

WriteLab handoff exporter 已实现 metadata-only 导出，**故意丢弃**以下内容：
- 原始段落文本（original text）
- 文本片段（text spans）
- 改写文本（rewrite text）
- 自由评论（free-form comments）

保留的内容：
- 诊断指标（severity counts, problem types, expression metrics）
- 隐私 attestation（no_full_text, no_api_keys, no_personal_identity）
- 导出 manifest（文件清单、校验和）

---

## 3. paper domain 与 Obsidian / Zotero / RAG 的关系

### 3.1 现状：三者均未实现

在 dev-frame-opencode 和 WriteLab 两个项目中，Obsidian 集成、Zotero/BibTeX 集成、RAG 检索层**均未实现**（not_found）。

当前阶段只有 contract schema 和 sample fixture，没有 runtime 代码。

### 3.2 Obsidian = 写作知识源

Obsidian vault 作为 paper domain 的知识源，提供以下类型的笔记：

| 笔记类型 | schema 枚举值 | 用途 | fixture 示例 |
|---------|--------------|------|-------------|
| 项目记忆 | `project_memory` | 论文项目的决策、教训、上下文 | - |
| 文献笔记 | `literature_note` | 文献阅读笔记，关联 citekey | `obsidian_literature_note.sample.md` |
| 写作规则 | `writing_rule` | 作者个人写作规则 | `obsidian_writing_rule.sample.md` |
| 反面例子 | `bad_example` | 应避免的表达/结构模式 | `obsidian_bad_example.sample.md` |
| 风格范例 | `style_example` | 目标期刊的风格参考 | - |
| 修改历史 | `revision_history` | 段落/章节的修改记录 | - |

**ObsidianNoteMetadata schema**（`obsidian_note_metadata.schema.json`）定义了：
- `note_id`：笔记唯一标识
- `type`：上述 6 种类型枚举
- `project_id` / `paper_id`：关联到具体论文项目
- `confidentiality`：public / private / sensitive
- `citation_allowed`：是否允许引用入 Context Pack
- `status`：active / archived / deprecated

### 3.3 Zotero / BibTeX = 文献元数据源

**ZoteroReferenceMetadata schema**（`zotero_reference_metadata.schema.json`）定义了：
- `citekey`：文献引用键（如 `zhang2024policy`）
- `title` / `authors` / `year` / `publication`：基本文献信息
- `item_type`：journal_article / book / book_section / thesis / conference_paper / report
- `doi` / `url`：数字标识和链接
- `local_pdf_ref`：本地 PDF 路径（**不入 pack**，仅用于本地查阅）
- `citation_allowed`：是否允许引用
- `confidentiality`：默认 public

### 3.4 RAG = 检索层

RAG 检索层在 contract 阶段体现为 **Context Pack Builder** 的检索接口设计：

- **输入**：task 相关的查询条件（chapter、section、task_type、constraints）
- **输出**：PaperContextPack，包含从 Obsidian vault / Zotero / 本地索引中检索到的相关内容
- **隐私过滤**：`privacy_filter_result` 确保 sensitive/private 来源被排除或脱敏
- **检索范围**：project_memory、writing_rules、forbidden_patterns、retrieved_literature、retrieved_style_examples、retrieved_bad_examples、retrieved_revision_history

当前 Context Pack fixture（`paper_context_pack.sample.json`）展示了检索结果的结构：
- `allowed_model_inputs`：明确列出允许进入模型的输入类型
- `excluded_sensitive_sources`：列出被隐私过滤排除的来源
- `source_manifest`：列出所有来源的类型、ID、保密级别

---

## 4. 为什么第一阶段不合并 WriteLab

### 4.1 技术栈差异大，直接合并成本高

WriteLab 有独立的完整技术栈：

- **FastAPI** 后端（`backend/app/main.py`）与 ai-workflow-hub 的 LangGraph + CLI 架构不兼容
- **Next.js** 前端（`frontend/`）与 dev-frame-opencode 无前端的状态不同
- **SQLite** 数据库（`writelab.db`）与 ai-workflow-hub 的 run_dir 文件存储模式不同
- **DeepSeek LLM gateway**（`core/llm_gateway.py`, 15.1 KB）与 ai-workflow-hub 的 model_config 不同
- **PyInstaller 打包**（`packaging/launcher.py`）生成本地 exe，与 dev-frame-opencode 的 Python 包模式不同

直接合并会导致：两套 HTTP 框架、两套数据库、两套 LLM 调用方式、两套配置系统混在一个仓库中，边界混乱。

### 4.2 WriteLab 处于 Phase 0-2，API 不稳定

根据 `cssci_writing_lab_design_doc.md` 的 MVP 范围：

- **已实现**（Phase 0-2）：项目管理、段落诊断、表达检测、诊断报告、handoff 导出
- **未实现**（Phase 3-5）：CSSCI 风格改写、版本对比、个人写作规则库、投稿适配、多人协作

Phase 3-5 的实现可能改变 API 契约、数据模型、LLM 调用方式。在 API 不稳定时合并，后续每次 WriteLab 迭代都会影响 dev-frame-opencode。

### 4.3 先固化 contract，后续通过 adapter 接入

第一阶段策略：
1. 在 dev-frame-opencode 中定义 paper domain contract（7 schema，已冻结）
2. WriteLab 的 handoff ZIP 格式作为第一个 adapter contract
3. 后续 WriteLab API 稳定后，增加 HTTP adapter
4. 最终根据 WriteLab Phase 3-5 完成情况决定是否合并

---

## 5. 为什么第一阶段 contract-first

### 5.1 避免碎片化

如果不先定义边界就直接写功能代码，会形成第二套碎片化系统：
- coding domain 有 `WorkflowState` + `schemas.py`
- paper domain 可能随手写一套新的 state/model，与 coding domain 不一致
- 两套 Acceptance Gate、两套 Issue Ledger、两套 Evidence 收集，各自演进，难以统一

### 5.2 与 evidence-first 风格一致

dev-frame-opencode 的核心方法论是 evidence-first（先 schema，后 runtime）：
- coding domain 先有 `schemas.py`（WorkflowState），再有节点实现
- acceptance.py 先定义 gate 规则，再有执行逻辑
- paper domain 遵循同样的路径：先 7 个 JSON Schema，再有 runtime 实现

### 5.3 最小可验证边界

7 个 schema + 7 个 fixture = 最小可验证边界：

| # | Schema | Fixture | 验证什么 |
|---|--------|---------|---------|
| 1 | `paper_task_spec.schema.json` | `paper_task_spec.sample.yaml` | paper 任务的输入结构 |
| 2 | `paper_context_pack.schema.json` | `paper_context_pack.sample.json` | LLM 输入包的结构和隐私过滤 |
| 3 | `paper_review_issue.schema.json` | （内嵌于 acceptance_result） | 单个审查 issue 的结构 |
| 4 | `paper_acceptance_result.schema.json` | `paper_acceptance_result.sample.json` | 验收裁定的结构 |
| 5 | `paper_evidence_manifest.schema.json` | - | evidence 清单和隐私 attestation |
| 6 | `obsidian_note_metadata.schema.json` | `obsidian_literature_note.sample.md` / `obsidian_writing_rule.sample.md` / `obsidian_bad_example.sample.md` | Obsidian 笔记元数据 |
| 7 | `zotero_reference_metadata.schema.json` | `zotero_reference.sample.json` | Zotero 文献元数据 |

验证脚本可对每个 fixture 跑 schema validation，确认 contract 一致性。

---

## 6. 后续如何从 contract 进入 runtime

### 6.1 阶段路线图

```
A1 contracts          A2 fixture ingest       A3 Context Pack Builder
   [DONE]                 [NEXT]                   [PLANNED]
   7 schema               加载 fixture 到           从 Obsidian/Zotero
   7 fixture              paper domain state        检索 -> 组装 Context Pack
   |                      |                        |
   v                      v                        v
A4 local retrieval    A5 WriteLab Adapter      A6 Paper Acceptance Gate
   [PLANNED]             [PLANNED]                 [PLANNED]
   本地索引检索            dry-run 模式接入          paper-specific 验收门禁
   (vault + citekey)     WriteLab 诊断能力           检查结构/论证/引用/表达/隐私
   |                      |                        |
   v                      v                        v
A7 Evidence Ledger    A8 learnable feedback
   [PLANNED]             [PLANNED]
   paper evidence        从 acceptance 结果和
   持久化 + 审计链        human feedback 中学习
                          更新 writing_rules 和
                          forbidden_patterns
```

### 6.2 各阶段详细说明

| 阶段 | 名称 | 输入 | 输出 | 验证方式 |
|------|------|------|------|---------|
| A1 | contracts | - | 7 schema + 7 fixture | schema validation |
| A2 | fixture ingest | fixture files | PaperWorkflowState 初始化 | state 符合 schema |
| A3 | Context Pack Builder | task + vault + zotero | PaperContextPack | pack 符合 schema + privacy_filter passed |
| A4 | local retrieval | vault 索引 + citekey 索引 | retrieved_literature / rules / examples | 检索结果在 allowed_model_inputs 中 |
| A5 | WriteLab Adapter dry-run | Context Pack | diagnosis report (mocked) | adapter contract 验证 |
| A6 | Paper Acceptance Gate | diagnosis + Context Pack | PaperAcceptanceResult | result 符合 schema + 状态机正确 |
| A7 | Evidence Ledger | run evidence | PaperEvidenceManifest | manifest 完整 + privacy_attestation 通过 |
| A8 | learnable feedback | acceptance result + human feedback | 更新后的 writing_rules / forbidden_patterns | 规则增量可追溯 |

---

## 7. human_required 场景

### 7.1 触发条件

paper domain 中以下场景必须触发 `human_required`，由人工确认后才能继续：

| 场景 | 触发原因 | 对应 contract 字段 |
|------|---------|-------------------|
| 真实学术内容审查 | paper 涉及真实学术内容时，AI 不得自行判断内容正确性 | `PaperAcceptanceResult.status = "human_required"` |
| 文献引用验证 | citekey 对应的文献是否真正支撑当前论点，需要人工确认 | `PaperReviewIssue.issue_type = "citation"` + `human_required = true` |
| 论文隐私审查 | 真实论文全文、作者身份、机构名称是否泄露，需要人工确认 | `PaperEvidenceManifest.privacy_attestation` 三项全部 true 需人工复核 |
| 改写/润色结果审核 | AI 生成或修改的学术文本是否保留作者意图，需要人工审核 | `PaperTaskSpec.human_required_rules` 定义具体规则 |

### 7.2 与 coding domain human_gate 的区别

coding domain 的 human_gate 关注：
- TaskSpec scope 是否合理（`plan_audit_result`）
- 代码变更是否安全（`dangerous_change`）
- 测试失败后是否继续修复（`fix-before-round-{N}` 决策）

paper domain 的 human_required 关注：
- 学术内容真实性（不能由 AI 判断论文观点是否正确）
- 文献引用准确性（不能由 AI 判断引用是否恰当）
- 隐私合规性（不能由 AI 自行确认隐私 attestation）
- 改写忠实度（不能由 AI 判断改写是否保留作者意图）

### 7.3 PaperTaskSpec 中的 human_required_rules

`PaperTaskSpec.human_required_rules` 是一个字符串数组，定义该任务的 human_required 触发规则，例如：

```json
{
  "human_required_rules": [
    "citation_must_be_verified_by_human",
    "full_text_must_not_enter_model",
    "rewrite_requires_author_approval",
    "privacy_review_before_export"
  ]
}
```

---

## 8. privacy / confidentiality 边界

### 8.1 三级分类

paper domain 的所有数据源均使用三级保密分类：

| 级别 | 枚举值 | 含义 | 处理规则 |
|------|--------|------|---------|
| 公开 | `public` | 可自由进入 Context Pack 和 Evidence Pack | 无需特殊处理 |
| 私有 | `private` | 可进入 Context Pack，但需标记来源 | 在 source_manifest 中记录 |
| 敏感 | `sensitive` | 不得进入 Context Pack | 被 privacy_filter 排除 |

**contract 中的体现**：
- `ObsidianNoteMetadata.confidentiality`：默认 `private`
- `ZoteroReferenceMetadata.confidentiality`：默认 `public`
- `PaperTaskSpec.confidentiality`：枚举 `public` / `private` / `sensitive`，默认 `private`

### 8.2 硬性禁止规则

以下数据**永远不得**进入 Context Pack 或 Evidence Pack：

| 禁止项 | 原因 | contract 体现 |
|--------|------|-------------|
| 真实论文全文 | 全文可能包含未发表数据、受访者信息 | `PaperEvidenceManifest.privacy_attestation.no_full_text = true` |
| API key | DeepSeek 或其他服务的密钥 | `PaperEvidenceManifest.privacy_attestation.no_api_keys = true` |
| 作者身份信息 | 真实姓名、机构名称、联系方式 | `PaperEvidenceManifest.privacy_attestation.no_personal_identity = true` |
| writelab.db | WriteLab SQLite 数据库包含用户项目全文 | 不迁移，handoff ZIP 只导出 metadata |
| 本地 PDF 文件 | `ZoteroReferenceMetadata.local_pdf_ref` 仅用于本地查阅 | schema 注释：`"本地 PDF 文件路径（不入 pack）"` |

### 8.3 Context Pack 隐私过滤

`PaperContextPack.privacy_filter_result` 结构：

```json
{
  "passed": true,
  "excluded_sources": ["sensitive-note-001", "private-fulltext-ref"]
}
```

- `passed = true`：所有来源已通过隐私过滤
- `excluded_sources`：被排除的来源 ID 列表
- `excluded_sensitive_sources`：因 confidentiality = sensitive 被排除的来源
- `source_manifest`：列出所有来源的 `source_type` / `source_id` / `confidentiality`

### 8.4 Evidence Pack 隐私 attestation

`PaperEvidenceManifest.privacy_attestation` 三项布尔断言：

```json
{
  "no_full_text": true,
  "no_api_keys": true,
  "no_personal_identity": true
}
```

三项必须全部为 `true`，evidence manifest 才被视为合规。任一为 `false` 时，acceptance gate 必须 `block`。

### 8.5 占位符策略

对于需要引用但包含敏感信息的来源，使用占位符替代：
- 作者姓名 -> `[AUTHOR_1]`
- 机构名称 -> `[INSTITUTION_A]`
- 具体数据 -> `[DATA_REDACTED]`

占位符在 `source_manifest` 中保留映射关系，但映射关系本身标记为 `confidentiality: sensitive`，不进入 Context Pack。

---

## 附录 A：当前 paper domain 文件清单

```
D:\dev-frame-opencode\ai-workflow-hub\src\ai_workflow_hub\domains\paper\
  +-- contracts\
  |     +-- paper_task_spec.schema.json          (1.3 KB)
  |     +-- paper_context_pack.schema.json        (1.4 KB)
  |     +-- paper_review_issue.schema.json         (850 B)
  |     +-- paper_acceptance_result.schema.json    (850 B)
  |     +-- paper_evidence_manifest.schema.json    (898 B)
  |     +-- obsidian_note_metadata.schema.json     (902 B)
  |     +-- zotero_reference_metadata.schema.json  (954 B)
  +-- fixtures\
        +-- paper_task_spec.sample.yaml           (869 B)
        +-- obsidian_literature_note.sample.md     (940 B)
        +-- obsidian_bad_example.sample.md         (914 B)
        +-- obsidian_writing_rule.sample.md        (817 B)
        +-- zotero_reference.sample.json           (615 B)
        +-- paper_context_pack.sample.json         (1.8 KB)
        +-- paper_acceptance_result.sample.json   (1.0 KB)
```

## 附录 B：关键文件路径索引

| 文件 | 路径 | 说明 |
|------|------|------|
| coding_graph.py | `D:\dev-frame-opencode\ai-workflow-hub\src\ai_workflow_hub\workflows\coding_graph.py` | coding domain 状态图 |
| schemas.py | `D:\dev-frame-opencode\ai-workflow-hub\src\ai_workflow_hub\schemas.py` | coding domain WorkflowState |
| acceptance.py | `D:\dev-frame-opencode\ai-workflow-hub\src\ai_workflow_hub\acceptance.py` | Acceptance Gate (81.7 KB) |
| task_spec_adapter.py | `D:\dev-frame-opencode\ai-workflow-hub\src\ai_workflow_hub\task_spec_adapter.py` | TaskSpec 适配器 |
| execution_report_adapter.py | `D:\dev-frame-opencode\ai-workflow-hub\src\ai_workflow_hub\execution_report_adapter.py` | ExecutionReport 适配器 |
| issue_ledger.py | `D:\dev-frame-opencode\ai-workflow-hub\src\ai_workflow_hub\issue_ledger.py` | Issue Ledger |
| safety.py | `D:\dev-frame-opencode\ai-workflow-hub\src\ai_workflow_hub\safety.py` | Safety Checks |
| policy_gate.py | `D:\dev-frame-opencode\ai-workflow-hub\src\ai_workflow_hub\policy_gate.py` | Policy Gate |
| run_governance.py | `D:\dev-frame-opencode\ai-workflow-hub\src\ai_workflow_hub\run_governance.py` | Run Governance |
| expression_detector.py | `D:\writelab\backend\app\analyzers\expression_detector.py` | 21 类表达检测规则 |
| llm_gateway.py | `D:\writelab\backend\app\core\llm_gateway.py` | DeepSeek LLM + fallback |
| writelab_handoff_exporter.py | `D:\writelab\backend\app\services\writelab_handoff_exporter.py` | Metadata-only handoff ZIP |
| cssci_writing_lab_design_doc.md | `D:\writelab\cssci_writing_lab_design_doc.md` | WriteLab 设计文档 |

## 变更审计

| 日期 | 变更人 | 变更内容 |
|------|--------|---------|
| 2026-06-11 | RD | 初始创建：paper domain architecture 设计文档 |
