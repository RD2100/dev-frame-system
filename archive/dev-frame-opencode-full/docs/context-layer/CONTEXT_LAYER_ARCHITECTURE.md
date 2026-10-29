# Context Layer Architecture

> **阶段**: contract-first 设计
> **状态**: 初始版本
> **创建日期**: 2026-06-11
> **适用项目**: dev-frame-opencode（学术写作辅助框架）

---

## 0. 设计原则

1. **原始文件是 source of truth**，索引和缓存可重建、不可作为唯一依据。
2. **模型只能通过 Context Pack 获取上下文**，禁止直接读全库、读全文件、读敏感内容。
3. **模型输出只能通过 Evidence Pack 离开**，所有输出经过审计边界过滤。
4. **分级策略** 决定哪些数据可以进入 Pack、哪些绝对禁止。
5. **第一层只做 metadata 解析**，不做 embedding、不做向量检索、不做全文索引。

---

## 1. Memory Files — source of truth（项目经验）

### 1.1 位置

```
ai-workflow-hub/memory/
```

### 1.2 当前状态

已存在。当前包含 22 个结构化经验卡片，类型如下：

| 类型 | 命名前缀 | 说明 | 示例文件 |
|------|----------|------|----------|
| `gotcha` | `gotcha_*.md` | 踩坑记录，防止重复犯错 | `gotcha_format_vs_replace.md` |
| `pattern` | `pattern_*.md` | 可复用的工程模式 | `pattern_chain_truth.md` |
| `decision` | `decision_*.md` | 架构/技术决策记录 | `decision_go_langgraph.md` |

### 1.3 格式

每个文件使用 Markdown + YAML frontmatter：

```yaml
---
type: gotcha | pattern | decision
tags: [tag1, tag2]
date: YYYY-MM-DD
---

# Title

## Problem / Context
## Fix / Decision / Pattern
## Avoid / Consequence
## Evidence
```

模板文件：`ai-workflow-hub/memory/_template.md`

### 1.4 合约

- Memory Files 是项目经验的 **唯一真相源**。
- 不依赖模型记忆、不依赖对话历史、不依赖外部知识库来回忆项目经验。
- 任何新增经验必须写入 memory 文件，否则视为不存在。
- 读取时按 `type` 和 `tags` 过滤，按需加载，不一次性全量注入。

---

## 2. Obsidian Sources — writing knowledge source（写作知识）

### 2.1 位置

```
obsidian-sources/        # 待创建
```

### 2.2 当前状态

**not_found** — 目录和文件均不存在，需要新建。

### 2.3 数据来源

从 Obsidian vault 读取以下类型的笔记：

| 笔记类型 | 说明 | 示例 |
|----------|------|------|
| `literature_note` | 文献笔记，对论文的摘要、评价、关联 | 某篇 paper 的核心观点总结 |
| `writing_rule` | 写作规则，项目定义的格式/风格/结构约束 | "Introduction 必须包含 research gap" |
| `bad_example` | 负样本，已知的错误写法或需避免的模式 | "不要使用 'In recent years' 开头" |
| `revision_history` | 修改历史，论文各版本的修改记录和原因 | "v2 将 method 节提前至 results 之前" |
| `project_memory` | 项目记忆，跨会话的项目状态和上下文 | "导师偏好 qualitative approach" |

### 2.4 格式

Markdown + YAML frontmatter：

```yaml
---
type: literature_note | writing_rule | bad_example | revision_history | project_memory
tags: [tag1, tag2]
date: YYYY-MM-DD
source_vault: "vault-name"
source_path: "path/in/vault.md"
---

# Title

## Content

（各类型的正文结构不同，按需定义）
```

### 2.5 第一层合约

- **只做 metadata 解析**：读取 frontmatter 中的 `type`、`tags`、`date` 等字段，建立 metadata 索引。
- **不做 embedding**：第一层不生成向量表示。
- **不做全文索引**：不建立倒排索引或 BM25 索引。
- 检索方式：第一层通过 metadata 字段（type + tags）进行过滤匹配。

---

## 3. Zotero / BibTeX — literature metadata source（文献元数据）

### 3.1 位置

```
zotero-sources/          # 待创建
```

### 3.2 当前状态

**not_found** — 目录和文件均不存在，需要新建。

### 3.3 数据来源

从 Zotero 的 **Better BibTeX export** 读取 `.bib` 文件。

### 3.4 提取字段

从每条 BibTeX entry 提取以下字段：

| 字段 | 说明 | 示例 |
|------|------|------|
| `citekey` | 引用键（Better BibTeX 自动生成） | `@smith2024transformer` |
| `title` | 论文标题 | "Attention Is All You Need" |
| `authors` | 作者列表 | `["Smith, J.", "Lee, K."]` |
| `year` | 发表年份 | `2024` |
| `publication` | 发表刊物/会议 | "NeurIPS 2024" |
| `item_type` | 条目类型 | `article`, `inproceedings`, `book` |
| `doi` | DOI 标识符 | `10.1234/example.2024` |
| `url` | 访问链接 | `https://doi.org/...` |
| `tags` | 标签列表 | `["NLP", "transformer"]` |

### 3.5 第一层合约

- **只做 metadata 解析**：解析 `.bib` 文件，提取上表字段，建立结构化索引。
- **不做 PDF 全文索引**：不解析 PDF 附件内容。
- **不做 embedding**：不生成向量表示。
- 检索方式：第一层通过 `citekey`、`tags`、`year`、`item_type` 进行过滤匹配。

---

## 4. RAG Sources — indexed materials（检索增强素材）

### 4.1 位置

```
rag-sources/             # 待创建
```

### 4.2 当前状态

**not_found** — 无 embedding、无 vector DB、无 chunking 基础设施。

### 4.3 分层演进

| 层级 | 能力 | 说明 |
|------|------|------|
| **第一层** | 本地 FTS5 或 Chroma MVP | 对 Obsidian Sources 和 Zotero metadata 建立全文搜索（FTS5）或轻量向量索引（Chroma），支持关键词检索和基础相似度匹配 |
| **后续** | embedding model + vector store + reranker | 引入 embedding 模型生成向量，使用 vector store 存储，检索后经 reranker 重排序 |

### 4.4 第一层合约

- 索引素材来自 Obsidian Sources 和 Zotero Sources 的 metadata + 正文。
- 第一层不要求语义检索能力，关键词匹配即可。
- 索引结果必须携带来源引用（source_path 或 citekey），用于溯源。

---

## 5. Vector Index — derived cache, not source of truth

### 5.1 定位

Vector Index 是从以下来源 **派生的缓存**：

```
Obsidian Sources (writing knowledge)
    + Zotero Sources (literature metadata)
    + RAG Sources (indexed materials)
        ──embedding──► Vector Index
```

### 5.2 核心约束

| 约束 | 说明 |
|------|------|
| **可重建** | Vector Index 可以随时从原始文件重新生成，丢失不造成数据损失 |
| **不可作为唯一依据** | 任何决策不能仅基于 Vector Index 的检索结果，必须回溯原始文件确认 |
| **不是 source of truth** | source of truth 始终在 Obsidian vault、Zotero library、memory/ 原始文件中 |

### 5.3 合约

- Vector Index 的写入和更新必须记录来源映射（index_entry → source_file）。
- 当原始文件变更时，对应的 index entry 必须失效或更新。
- 重建操作应是幂等的：相同输入产生相同输出。

---

## 6. Context Pack — only approved model input boundary

### 6.1 定位

Context Pack 是模型获取本轮任务上下文的 **唯一合法入口**。

```
┌─────────────────────────────────────────┐
│             Context Pack                │
│                                         │
│  ┌─ project_memory                      │
│  │   (从 memory/ 加载的项目经验卡片)      │
│  │                                      │
│  ├─ task_summary                        │
│  │   (当前任务描述和约束)                 │
│  │                                      │
│  ├─ chapter_function                    │
│  │   (当前章节的角色和功能定义)            │
│  │                                      │
│  ├─ writing_rules                       │
│  │   (从 writing_rule 笔记加载的规则)     │
│  │                                      │
│  ├─ forbidden_patterns                  │
│  │   (从 bad_example 和 gotcha 加载)     │
│  │                                      │
│  ├─ retrieved_literature                │
│  │   (检索命中的文献元数据)               │
│  │                                      │
│  ├─ retrieved_style_examples            │
│  │   (检索命中的风格样本)                 │
│  │                                      │
│  ├─ retrieved_bad_examples              │
│  │   (检索命中的负样本)                   │
│  │                                      │
│  ├─ retrieved_revision_history          │
│  │   (检索命中的修改历史)                 │
│  │                                      │
│  ├─ privacy_filter_result               │
│  │   (隐私过滤的执行结果)                 │
│  │                                      │
│  ├─ allowed_model_inputs                │
│  │   (本次允许模型读取的数据清单)          │
│  │                                      │
│  ├─ excluded_sensitive_sources          │
│  │   (本次被排除的敏感来源清单)            │
│  │                                      │
│  └─ source_manifest                     │
│      (所有注入内容的来源文件清单+校验和)    │
│                                         │
└─────────────────────────────────────────┘
```

### 6.2 核心约束

| 约束 | 说明 |
|------|------|
| **不能直接读全库** | 模型不得遍历整个 Obsidian vault 或 Zotero library |
| **不能读全文件** | 只注入经过筛选的相关片段，不注入整个文件 |
| **不能读敏感内容** | `sensitive` 级别的数据绝对禁止进入 Context Pack |
| **必须经过 privacy filter** | 所有 `private` 级别数据进入前必须经过隐私过滤 |

### 6.3 组装流程

```
1. 确定 task_summary（当前任务）
2. 按 task 需求从各 source 检索相关内容
3. 对检索结果执行 privacy_filter（分级策略见第 8 节）
4. 过滤后的内容组装为 Context Pack
5. 记录 source_manifest（来源清单 + 校验和）
6. Context Pack 作为唯一上下文注入模型 prompt
```

---

## 7. Evidence Pack — output audit boundary

### 7.1 定位

Evidence Pack 是模型输出后生成的 **审计包**，用于记录和审计模型的所有产出。

### 7.2 内容结构

```
Evidence Pack
├── status                  # 执行状态：success / partial / failed
├── security_report         # 安全检查报告（是否泄露敏感信息）
├── diff                    # 输出变更的 diff（对比前后状态）
├── test_results            # 相关测试的执行结果
├── citation_evidence       # 引用证据（输出中引用的文献/来源溯源）
├── review_results          # 审查结果（自动化审查 + 人工审查标记）
└── excluded_from_pack      # 明确排除的内容列表
```

### 7.3 核心约束

| 约束 | 说明 |
|------|------|
| **不含真实论文全文** | Evidence Pack 中不得包含论文的完整正文内容 |
| **不含 API key** | 不得包含任何 API 密钥、token、凭证 |
| **不含个人隐私** | 不得包含作者真实身份、导师意见、个人信息 |
| **可审计** | Evidence Pack 可安全地交给外部审查者（如 GPT reviewer） |

### 7.4 生成流程

```
1. 模型输出完成
2. 执行 security_report（敏感信息扫描）
3. 生成 diff（变更对比）
4. 收集 test_results
5. 整理 citation_evidence（引用溯源）
6. 执行 review_results（自动审查）
7. 打包为 Evidence Pack
```

---

## 8. 分级策略 — sensitive / private / public

### 8.1 分级定义

| 级别 | 定义 | Context Pack | Evidence Pack | 示例 |
|------|------|:------------:|:-------------:|------|
| `public` | 无敏感性的结构化数据 | 允许进入 | 允许进入 | schema 定义、fixture 数据、虚构示例 |
| `private` | 项目相关的非公开信息 | 经 privacy filter 后允许进入 | 允许进入（经脱敏） | 论文元数据、引用关系、写作规则、项目经验卡片 |
| `sensitive` | 高度敏感、不可泄露的信息 | **禁止进入** | **禁止进入** | 论文全文、API key、作者真实身份、导师意见、未发表数据 |

### 8.2 分级规则详解

#### public

- 可直接进入 Context Pack，无需过滤。
- 可直接进入 Evidence Pack，无需脱敏。
- 典型数据：
  - 项目 schema 和配置文件
  - 测试用的 fixture 数据
  - 文档中明确标注为虚构的示例

#### private

- 进入 Context Pack 前必须经过 **privacy filter**：
  - 移除或遮蔽可直接关联到真实个人的信息
  - 限制注入量，避免上下文泄露过多项目细节
- 进入 Evidence Pack 时允许保留，但需审查是否无意中暴露 sensitive 信息。
- 典型数据：
  - 论文元数据（标题、作者、年份 — 不含全文）
  - 引用关系和文献网络
  - 写作规则和项目约定
  - `memory/` 中的 gotcha/pattern/decision 卡片

#### sensitive

- **绝对禁止** 进入 Context Pack，任何情况下都不注入模型。
- **绝对禁止** 进入 Evidence Pack，任何情况下都不对外暴露。
- 典型数据：
  - 论文完整正文（全文）
  - API key、token、密码、凭证
  - 作者真实身份信息（在匿名审稿场景下）
  - 导师的具体意见和评价
  - 未发表的实验数据和结果

### 8.3 privacy filter 执行要求

```
对每个待注入 Context Pack 的 private 数据项：

1. 检查是否包含 sensitive 子串（正则匹配 + 关键词黑名单）
2. 检查是否包含 PII（姓名、邮箱、地址、电话）
3. 检查是否包含凭证模式（API key 格式、token 格式）
4. 如命中上述任一规则 → 拒绝注入，记录到 excluded_sensitive_sources
5. 如未命中 → 允许注入，记录到 allowed_model_inputs
```

---

## 9. 数据流总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Sources of Truth                             │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ memory/       │  │ Obsidian     │  │ Zotero / BibTeX          │  │
│  │ (经验卡片)    │  │ Sources      │  │ (.bib metadata)          │  │
│  │ 22 cards      │  │ (待创建)     │  │ (待创建)                  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────────┘  │
│         │                  │                      │                 │
│         └──────────┬───────┴──────────────────────┘                 │
│                    │                                                │
│              metadata 解析                                          │
│                    │                                                │
│                    ▼                                                │
│         ┌──────────────────┐                                       │
│         │   RAG Sources    │                                       │
│         │  (FTS5/Chroma)   │                                       │
│         │   (待创建)       │                                       │
│         └────────┬─────────┘                                       │
│                  │                                                  │
│            embedding (后续)                                         │
│                  │                                                  │
│                  ▼                                                  │
│         ┌──────────────────┐                                       │
│         │  Vector Index    │  ← derived cache, 可重建               │
│         │  (非 source of   │                                       │
│         │   truth)         │                                       │
│         └────────┬─────────┘                                       │
│                  │                                                  │
│                  ▼                                                  │
│    ┌───────────────────────────────┐                                │
│    │       privacy filter          │                                │
│    │  (sensitive/private/public)   │                                │
│    └───────────────┬───────────────┘                                │
│                    │                                                │
│                    ▼                                                │
│    ┌───────────────────────────────┐                                │
│    │        Context Pack           │  ← 模型唯一输入边界             │
│    └───────────────┬───────────────┘                                │
│                    │                                                │
│                    ▼                                                │
│    ┌───────────────────────────────┐                                │
│    │          Model                │                                │
│    └───────────────┬───────────────┘                                │
│                    │                                                │
│                    ▼                                                │
│    ┌───────────────────────────────┐                                │
│    │       Evidence Pack           │  ← 模型输出审计边界             │
│    │  (不含全文/key/隐私)           │                                │
│    └───────────────────────────────┘                                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 10. 实施优先级

| 优先级 | 组件 | 当前状态 | 行动 |
|--------|------|----------|------|
| P0 | Memory Files | 已存在（22 cards） | 维护，确保所有新经验写入 |
| P1 | Obsidian Sources | not_found | 新建目录结构，定义 frontmatter schema，实现 metadata 解析器 |
| P1 | Zotero / BibTeX | not_found | 新建目录结构，实现 .bib 解析器，定义字段映射 |
| P2 | RAG Sources | not_found | 搭建 FTS5 或 Chroma MVP，对接 Obsidian + Zotero metadata |
| P2 | Vector Index | not_found | 在 RAG 基础上实现 embedding pipeline（后续） |
| P0 | Context Pack | 概念存在 | 定义组装逻辑和 privacy filter，实现 Pack builder |
| P0 | Evidence Pack | 概念存在 | 定义生成逻辑和审计规则，实现 Pack generator |
| P0 | 分级策略 | 本文定义 | 实现 privacy filter 规则引擎 |

---

## 11. 开放问题

| 编号 | 问题 | 状态 |
|------|------|------|
| Q1 | Obsidian vault 的同步方式（手动导出 vs 自动监听）？ | 待决定 |
| Q2 | Better BibTeX 的自动导出触发机制？ | 待决定 |
| Q3 | privacy filter 的具体正则规则和关键词黑名单？ | 待定义 |
| Q4 | Context Pack 的 token 预算上限？ | 待确定 |
| Q5 | Evidence Pack 的存储和版本管理策略？ | 待确定 |
| Q6 | Vector Index 的失效检测机制（原始文件变更后如何标记 stale）？ | 待设计 |
