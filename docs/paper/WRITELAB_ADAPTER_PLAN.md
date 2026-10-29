# WriteLab Adapter Plan

> WriteLab 与 ai-workflow-hub (paper domain) 的集成设计文档。
> 核心原则：**WriteLab 保持独立项目，不合并代码；只通过 Adapter Contract 对接。**

---

## 1. 设计原则

| 编号 | 原则 | 说明 |
|------|------|------|
| P-1 | 独立仓库 | WriteLab 代码不迁入 ai-workflow-hub，保持独立版本管理和发布节奏 |
| P-2 | Contract-First | 第一阶段只定义 adapter contract（数据格式 + 调用协议），不写集成代码 |
| P-3 | 最小权限 | Adapter 不读取 writelab.db，不读取 .env，不访问 WriteLab 内部状态 |
| P-4 | 隐私安全 | 所有跨系统传输数据必须通过 privacy filter，符合 `PaperContextPack.privacy_filter_result` 约束 |
| P-5 | 可降级 | WriteLab 不可用时，paper domain 退化为纯 LLM + deterministic rule 流程，不阻塞 |

---

## 2. 阶段规划

### Phase 1: Adapter Contract 定义（当前）

- 定义 WriteLab 输出 -> paper domain contract 的**字段映射规范**
- 定义 handoff ZIP 的文件结构和命名约定
- 产出：本文档 + fixture 文件 + schema 补充
- **不写任何集成代码**

### Phase 2: CLI / File-Based 接入

- WriteLab 提供 CLI 命令导出 handoff ZIP
- ai-workflow-hub 提供 CLI 命令导入 handoff ZIP 并转换为 `PaperEvidenceManifest`
- 通信方式：文件系统（无网络依赖）

### Phase 3: API 接入（可选）

- WriteLab 暴露 HTTP API（expression_detector、paragraph_diagnosis）
- ai-workflow-hub 的 Context Pack Builder 可调用 WriteLab API 获取诊断结果
- 通信方式：HTTP + JSON，Bearer token 鉴权

### Phase 4: Metadata Handoff ZIP（可选）

- 双向：ai-workflow-hub 也可导出 metadata handoff ZIP 供 WriteLab 使用
- 包含：paper_task_spec、context_pack（只读）、已有 review issues
- 用途：WriteLab 可基于任务约束做针对性诊断

---

## 3. WriteLab 可复用能力清单

| 能力 | 说明 | 输出格式 | 对接方式 |
|------|------|----------|----------|
| **expression_detector** | 21 条表达风险规则（W1-W21），检测模板化表达、抽象名词堆叠、政策套话等 | JSON（rule_id, severity, location, evidence） | Phase 2: CLI 导出；Phase 3: API 调用 |
| **paragraph_diagnosis** | 段落功能诊断（LLM + rule fallback），识别论点段/证据段/过渡段/总结段 | JSON（paragraph_index, detected_function, confidence, mismatch） | Phase 2: CLI 导出；Phase 3: API 调用 |
| **handoff_exporter** | 将诊断结果打包为隐私安全的 ZIP 文件 | ZIP（manifest.json + 诊断结果 + 证据文件） | Phase 2: CLI 导出 |
| **rules (YAML)** | 表达风险规则库，YAML 格式，可独立更新 | YAML 文件 | Phase 1: 复制规则文件；Phase 3: API 拉取 |

### 不迁移的内容

| 排除项 | 原因 |
|--------|------|
| `writelab.db` | SQLite 数据库含用户交互历史、未脱稿内容，隐私风险高 |
| `.env` | 包含 API keys、本地路径等环境配置，不属于集成范围 |
| WriteLab UI 层 | 前端组件与 paper domain 无关，保持独立 |
| WriteLab 内部状态管理 | 会话状态、缓存等运行时数据不跨系统传递 |

---

## 4. 字段映射表：WriteLab Diagnosis -> PaperReviewIssue

WriteLab 的 diagnosis 输出结果需要转换为 paper domain 的 `PaperReviewIssue` 格式（schema: `paper_review_issue.schema.json`）。

### 4.1 expression_detector 映射

| WriteLab 输出字段 | PaperReviewIssue 字段 | 转换规则 |
|-------------------|----------------------|----------|
| `detection_id` | `issue_id` | 前缀转换：`wl-expr-{detection_id}` |
| 固定值 `"expression"` | `issue_type` | expression_detector 的输出统一映射为 `"expression"` |
| `risk_level` (`high`/`medium`/`low`) | `severity` | `high` -> `"major"`, `medium` -> `"minor"`, `low` -> `"info"` |
| `chapter` + `paragraph_index` | `location` | 直接映射为 `{"chapter": ..., "paragraph_index": ...}` |
| `matched_text` + `rule_description` | `evidence` | 拼接：`"[{rule_id}] {rule_description}: \"{matched_text}\""` |
| `suggestion` | `recommendation` | 直接映射 |
| `risk_level == "high"` 且 `rule_id in [W1, W3, W7]` | `blocking` | 高风险 + 核心规则命中时为 `true`，否则 `false` |
| 固定值 `false` | `human_required` | 表达类问题默认不需人工介入；如涉及真实数据引用则需上下文判断 |

**示例转换：**

```
WriteLab 输出:
{
  "detection_id": "0042",
  "rule_id": "W1",
  "risk_level": "high",
  "chapter": "引言",
  "paragraph_index": 3,
  "matched_text": "不是……而是……",
  "rule_description": "双重模板结构叠加",
  "suggestion": "拆分两个论述点，分别用具体证据支撑"
}

转换为 PaperReviewIssue:
{
  "issue_id": "wl-expr-0042",
  "issue_type": "expression",
  "severity": "major",
  "location": {"chapter": "引言", "paragraph_index": 3},
  "evidence": "[W1] 双重模板结构叠加: \"不是……而是……\"",
  "recommendation": "拆分两个论述点，分别用具体证据支撑",
  "blocking": true,
  "human_required": false
}
```

### 4.2 paragraph_diagnosis 映射

| WriteLab 输出字段 | PaperReviewIssue 字段 | 转换规则 |
|-------------------|----------------------|----------|
| `diagnosis_id` | `issue_id` | 前缀转换：`wl-para-{diagnosis_id}` |
| 条件判断（见下） | `issue_type` | 功能不匹配 -> `"structure"`；缺少证据 -> `"argument"` |
| `confidence` | `severity` | `confidence < 0.4` -> `"major"`；`0.4-0.6` -> `"minor"`；`> 0.6` -> `"info"` |
| `chapter` + `paragraph_index` | `location` | 直接映射 |
| `expected_function` + `detected_function` + `confidence` | `evidence` | 拼接：`"段落功能不匹配: 期望={expected}, 实际={detected}, 置信度={confidence}"` |
| `improvement_hint` | `recommendation` | 直接映射 |
| `confidence < 0.4` 且为论点段 | `blocking` | 核心论点段功能严重不匹配时 blocking |
| `involves_real_data == true` | `human_required` | 涉及真实数据时标记为需人工确认 |

### 4.3 映射汇总：WriteLab rule_id -> PaperReviewIssue.issue_type

| WriteLab 来源 | issue_type | 说明 |
|---------------|-----------|------|
| expression_detector (W1-W21) | `"expression"` | 表达风险类 |
| paragraph_diagnosis (功能不匹配) | `"structure"` | 段落结构类 |
| paragraph_diagnosis (缺少证据) | `"argument"` | 论证不足类 |
| citation_checker (未来) | `"citation"` | 引用校验类 |
| format_checker (未来) | `"format"` | 格式规范类 |

---

## 5. 文件映射表：WriteLab Handoff ZIP -> PaperEvidenceManifest

WriteLab 的 handoff_exporter 生成的 ZIP 文件需要转换为 paper domain 的 `PaperEvidenceManifest` 格式。

### 5.1 Handoff ZIP 内部结构约定

```
writelab-handoff-{timestamp}.zip
├── manifest.json              # ZIP 元数据清单（必须）
├── diagnosis/
│   ├── expression_results.json    # expression_detector 输出
│   └── paragraph_results.json     # paragraph_diagnosis 输出
├── evidence/
│   ├── highlighted_text.json      # 标注文本片段（脱敏后）
│   └── statistics.json            # 统计数据（仅聚合值，无原始数据）
└── rules/
    └── applied_rules.yaml         # 本次诊断使用的规则快照
```

### 5.2 manifest.json 格式（ZIP 内部）

```json
{
  "handoff_id": "wl-handoff-20260610-001",
  "writelab_version": "2.3.0",
  "created_at": "2026-06-10T14:30:00Z",
  "task_id": "paper-task-001-draft-intro",
  "privacy_attestation": {
    "no_full_text": true,
    "no_api_keys": true,
    "no_personal_identity": true
  },
  "files": [
    {"path": "diagnosis/expression_results.json", "sha256": "abc123...", "size_bytes": 2048},
    {"path": "diagnosis/paragraph_results.json", "sha256": "def456...", "size_bytes": 1536},
    {"path": "evidence/highlighted_text.json", "sha256": "ghi789...", "size_bytes": 1024},
    {"path": "evidence/statistics.json", "sha256": "jkl012...", "size_bytes": 512},
    {"path": "rules/applied_rules.yaml", "sha256": "mno345...", "size_bytes": 4096}
  ]
}
```

### 5.3 ZIP -> PaperEvidenceManifest 映射

| Handoff ZIP 字段 | PaperEvidenceManifest 字段 | 转换规则 |
|-----------------|---------------------------|----------|
| `manifest.handoff_id` | `manifest_id` | 前缀转换：`wl-{handoff_id}` |
| `manifest.task_id` | `task_id` | 直接映射 |
| 条件判断 | `status` | 所有文件 sha256 校验通过 -> `"complete"`；部分失败 -> `"partial"`；全部失败 -> `"failed"` |
| `manifest.files[].path` (basename) | `files[].filename` | 取文件名（不含路径） |
| `manifest.files[].sha256` | `files[].sha256` | 直接映射，导入时重新校验 |
| `manifest.files[].size_bytes` | `files[].size_bytes` | 直接映射，导入时重新校验 |
| 根据文件扩展名推断 | `files[].content_type` | `.json` -> `"application/json"`；`.yaml` -> `"application/yaml"` |
| `manifest.privacy_attestation` | `privacy_attestation` | 直接映射三个 boolean 字段 |
| `manifest.created_at` | `created_at` | 直接映射 |

### 5.4 Privacy Attestation 校验

导入 handoff ZIP 时，adapter 必须验证以下条件，任一失败则拒绝导入：

| 校验项 | 条件 | 失败处理 |
|--------|------|----------|
| `no_full_text` | 必须为 `true` | 拒绝导入，返回 `"privacy violation: full text detected"` |
| `no_api_keys` | 必须为 `true` | 拒绝导入，返回 `"privacy violation: API keys detected"` |
| `no_personal_identity` | 必须为 `true` | 拒绝导入，返回 `"privacy violation: personal identity detected"` |
| SHA-256 完整性 | 所有文件 sha256 与 manifest 一致 | 标记为 `status: "partial"` 或 `"failed"` |

---

## 6. Adapter Contract 接口定义（Phase 1 规范）

以下为 adapter contract 的逻辑接口定义，不涉及具体实现语言。

### 6.1 WriteLab -> Paper Domain（出站）

```
interface WritelabDiagnosisAdapter {
  // 将 expression_detector 结果转换为 PaperReviewIssue 数组
  convertExpressionResults(results: ExpressionResult[]): PaperReviewIssue[]

  // 将 paragraph_diagnosis 结果转换为 PaperReviewIssue 数组
  convertParagraphResults(results: ParagraphResult[]): PaperReviewIssue[]

  // 将 handoff ZIP 转换为 PaperEvidenceManifest
  convertHandoffZip(zipPath: string): PaperEvidenceManifest

  // 验证 handoff ZIP 的隐私合规性
  validatePrivacyAttestation(manifest: HandoffManifest): PrivacyValidationResult
}
```

### 6.2 Paper Domain -> WriteLab（入站，Phase 4 可选）

```
interface PaperMetadataExporter {
  // 将 paper_task_spec + context_pack 导出为 WriteLab 可读的 metadata ZIP
  exportTaskContext(taskSpec: PaperTaskSpec, contextPack: PaperContextPack): MetadataZipPath

  // 将已有 review issues 导出供 WriteLab 参考
  exportExistingIssues(issues: PaperReviewIssue[]): IssuesJsonPath
}
```

---

## 7. PaperAcceptanceResult 中的 reviewer 标识

`PaperAcceptanceResult` schema 的 `reviewer` 字段枚举值已包含 `"writelab_adapter"`：

| reviewer 值 | 含义 |
|-------------|------|
| `"deterministic_gate"` | 纸域内置的规则引擎审查 |
| `"gpt"` | GPT 审查（通过 review task） |
| `"human"` | 人工审查 |
| `"writelab_adapter"` | 通过 WriteLab Adapter 的诊断结果转换而来 |

当 reviewer 为 `"writelab_adapter"` 时：
- `evidence_pack_ref` 指向对应的 `PaperEvidenceManifest.manifest_id`
- `blocking_issues` 和 `non_blocking_issues` 中的 `issue_id` 以 `wl-` 前缀标识来源

---

## 8. 可选：Schema Validation Dry Run

在正式集成前，可使用 fixture 文件做 schema validation dry run，验证映射逻辑的正确性。

### 8.1 Dry Run 步骤

1. **准备输入**：使用 `fixtures/` 下的 7 个 sample 文件作为测试输入
2. **模拟 WriteLab 输出**：基于 `obsidian_bad_example.sample.md` 中的坏示例，构造一个虚构的 expression_detector 输出 JSON
3. **执行映射转换**：按照第 4 节映射规则，将虚构输出转换为 `PaperReviewIssue[]`
4. **Schema 校验**：使用 `paper_review_issue.schema.json` 校验转换结果的格式合规性
5. **构造 Handoff ZIP**：将虚构诊断结果打包为符合 5.1 节结构的 ZIP
6. **执行 ZIP 转换**：按照第 5 节映射规则，将 ZIP 转换为 `PaperEvidenceManifest`
7. **Schema 校验**：使用 `paper_evidence_manifest.schema.json` 校验转换结果
8. **Privacy Attestation 校验**：验证 5.4 节的校验逻辑

### 8.2 Dry Run 通过标准

| 校验项 | 通过条件 |
|--------|----------|
| PaperReviewIssue schema | 所有必填字段存在且类型正确 |
| PaperEvidenceManifest schema | 所有必填字段存在且类型正确 |
| issue_id 前缀 | 所有来自 WriteLab 的 issue 以 `wl-` 开头 |
| severity 映射 | 无未预期的 severity 值 |
| privacy_attestation | 三个 boolean 均为 `true` |
| SHA-256 完整性 | ZIP 内文件 hash 与 manifest 一致 |
| reviewer 字段 | 值为 `"writelab_adapter"` |

### 8.3 Dry Run 命令示例（伪代码）

```bash
# Step 1: 生成虚构 WriteLab 诊断输出
writelab-cli diagnose \
  --input fixtures/obsidian_bad_example.sample.md \
  --rules fixtures/rules/applied_rules.yaml \
  --output /tmp/writelab-diagnosis.json

# Step 2: 转换为 PaperReviewIssue[]
paper-adapter convert-diagnosis \
  --source /tmp/writelab-diagnosis.json \
  --mapping writelab-to-paper.json \
  --output /tmp/paper-review-issues.json

# Step 3: Schema 校验
paper-adapter validate \
  --schema contracts/paper_review_issue.schema.json \
  --data /tmp/paper-review-issues.json

# Step 4: 打包 handoff ZIP
writelab-cli export-handoff \
  --diagnosis /tmp/writelab-diagnosis.json \
  --output /tmp/writelab-handoff.zip

# Step 5: 转换为 PaperEvidenceManifest
paper-adapter convert-handoff-zip \
  --source /tmp/writelab-handoff.zip \
  --output /tmp/paper-evidence-manifest.json

# Step 6: Schema 校验
paper-adapter validate \
  --schema contracts/paper_evidence_manifest.schema.json \
  --data /tmp/paper-evidence-manifest.json
```

---

## 9. 风险与约束

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| WriteLab 规则版本与 paper domain 不同步 | 误报/漏报 | applied_rules.yaml 作为快照随 handoff ZIP 传递 |
| handoff ZIP 被篡改 | 虚假诊断结果 | SHA-256 完整性校验 + 可选签名验证 |
| WriteLab 输出格式变更 | 映射失败 | adapter contract 版本化，breaking change 需升级 major version |
| 大文件 ZIP 传输慢 | 延迟 | evidence/ 目录仅含聚合数据，不含全文 |

---

## 10. 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-06-11 | WriteLab 不合并入 ai-workflow-hub | 独立仓库、独立发布节奏、不同技术栈 |
| 2026-06-11 | Phase 1 仅定义 contract，不写代码 | 先对齐数据格式，避免过早耦合实现 |
| 2026-06-11 | 不迁移 writelab.db | 隐私风险高，含用户交互历史和未脱稿内容 |
| 2026-06-11 | 不读取 .env | 环境配置属于运行时细节，不属于集成范围 |
| 2026-06-11 | issue_id 使用 `wl-` 前缀 | 在 paper domain 内可区分 issue 来源，便于追溯 |
