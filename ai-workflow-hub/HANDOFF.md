# SADP Governance Handoff Document
## ai-workflow-hub — 从 QoderWork 交接给 Codex

**日期**: 2026-06-14
**最后完成**: A100 (Cumulative Acceptance Chain Validation) — CDP ACCEPTED
**当前 Schema**: `1.41`
**下一个 Acceptance**: A101

---

## 1. CDP 审查配置（最关键）

| 配置项 | 值 |
|--------|-----|
| **GPT 审查对话 URL** | `https://chatgpt.com/c/6a2e02e2-5ff8-83ee-8718-95ff5ac4242f` |
| **CHAT_ID** | `6a2e02e2-5ff8-83ee-8718-95ff5ac4242f` |
| **CDP 端点** | `http://127.0.0.1:9222` |
| **Chrome 启动参数** | 必须带 `--remote-debugging-port=9222` |
| **Playwright** | 所有 CDP 脚本用 `playwright.async_api` 的 `connect_over_cdp` |

### CDP 脚本位置

| 脚本 | 路径 | 用途 | 参数 |
|------|------|------|------|
| **submit** | `D:\dev-frame-opencode\scripts\submit_a16_to_gpt.py` | 上传 ZIP + 发送 prompt | `ZIP_PATH PROMPT_PATH OUTPUT_PATH` |
| **check** | `D:\dev-frame-opencode\_check_cdp.py` | 检查回复长度和消息数 | 无参数 |
| **recapture** | `D:\dev-frame-opencode\recapture_cdp.py` | 捕获完整回复 | `OUTPUT_PATH` |
| **ask** | `D:\dev-frame-opencode\ai-workflow-hub\_ask_gpt_question.py` | 向 GPT 提问 | `QUESTION_FILE OUTPUT_FILE` |
| **messages** | `D:\dev-frame-opencode\ai-workflow-hub\_get_messages.py` | 获取最近 N 条消息 | 无参数 |

**注意**: submit 脚本虽然名叫 `submit_a16_to_gpt.py`，但实际上用于**所有** acceptance 的提交（A16-A100+）。名字是历史遗留。

---

## 2. 项目结构

```
D:\dev-frame-opencode\ai-workflow-hub\          # 项目根目录
├── src\ai_workflow_hub\
│   └── cli.py                                   # 主源码 (~6000行, _AUDIT_SCHEMA_VERSION 定义在此)
├── tests\
│   └── test_paper_a*.py                         # 83 个测试文件 (A19-A100 + acceptance_gate)
├── scripts\
│   ├── validate_a*.py                           # 验证脚本 (A52-A100)
│   ├── pack_a*.py                               # 打包脚本 (A52-A100)
│   └── GPT_REVIEW_PROMPT_A*.txt                 # GPT 审查提示 (A52-A100)
├── output\                                      # 运行时输出
│   ├── REGRESSION_OUTPUT_A*.txt
│   ├── IN_SCOPE_TEST_RESULTS_A*.txt
│   ├── VALIDATION_OUTPUT_A*.txt
│   └── SELF_CONTAINMENT_OUTPUT_A*.txt
├── CDP_EVIDENCE_A*.zip                          # Evidence ZIP 包
├── CDP_VERDICT_A*.txt                           # GPT 裁决文件 (43个, A57-A100)
├── COUNTS_MANIFEST_A*.json                      # 计数清单
├── SCOPE_DECLARATION_A*.txt                     # 范围声明
├── known_flaky_tests.json                       # 已知不稳定测试注册表 (2条: A20, A24)
└── _fix_schema_*.py                             # 批量更新脚本 (历史)
```

---

## 3. 当前状态快照

| 指标 | 值 |
|------|-----|
| `_AUDIT_SCHEMA_VERSION` | `"1.41"` |
| 测试文件数 | 83 |
| Verdict 文件数 | 43 (A57-A100) |
| 回归测试通过 | 1953 passed, 0 failed |
| In-scope 通过 | 829 passed, 0 failed |
| known_flaky_tests.json | 2 条 (A20: date-dependent, A24: state-contamination) |
| Out-of-scope 文件 (恒定10个) | test_paper_a19, a20, a21, a22, a23, a23b, a24, acceptance_gate, a45, a46 |
| cli.py 行数 | ~6000+ |
| Bundle hash 计算方式 | `SHA256(concat(SHA256(cli) + SHA256(scope) + SHA256(reg) + SHA256(inscope) + SHA256(flaky_json) + SHA256(manifest_meta)))` |
| 排除在 bundle hash 外 | VALIDATION_OUTPUT, SELF_CONTAINMENT_OUTPUT |

---

## 4. 完整的 Acceptance 流程（A101 为例）

### Phase 1: 代码实现

**4.1 cli.py 改动**
- 在 `cli.py` 中找到 `_AUDIT_SCHEMA_VERSION`，将 `"1.41"` 改为 `"1.42"`
- 在最后一个 contract comment (A100) 之后添加 A101 的 contract comment
- contract comment 格式: `# A101: <标题>` + 若干行描述 + `Schema bumped to 1.42.`

**4.2 测试文件**
- 创建 `tests/test_paper_a101_<名称>.py`
- 必须包含: schema version 测试, contract 测试, forward_compat 测试, 不变量测试
- `_PROJECT_ROOT = Path(__file__).resolve().parent.parent`
- 读取 cli 源码: `_read_cli_source()` → 读 `src/ai_workflow_hub/cli.py`

**4.3 交付物三件套**
- `scripts/validate_a101.py` — 验证脚本（schema 检查、manifest 验证、bundle hash、transcript chain 等）
- `scripts/pack_a101.py` — 打包脚本（9 步流程，见下文）
- `scripts/GPT_REVIEW_PROMPT_A101.txt` — GPT 审查提示（必须包含: A101, 1.42, schema, test, pass, evidence, bundle, tamper/hash/integrity, ACCEPTED, REJECTED）

### Phase 2: 批量更新 OR chains

**4.4 创建 `_fix_schema_142.py`**

每次 schema bump 都要更新所有测试文件中的 OR chain。模式:
```python
# 标准 OR chain: 在 "1.41" 后添加 "1.42"
src = src.replace(
    'or \'_AUDIT_SCHEMA_VERSION = "1.41"\' in cli',
    'or \'_AUDIT_SCHEMA_VERSION = "1.41"\' in cli or \'_AUDIT_SCHEMA_VERSION = "1.42"\' in cli'
)

# Tuple 模式: 在 tuple 末尾的 "1.41" 后添加 "1.42"
src = re.sub(r'(in \([^)]*)"1\.41"(\))', r'\1"1.41", "1.42"\2', src)
```

**4.5 边缘 case（每次都要手动检查）**

| 文件 | 问题 | 修复方式 |
|------|------|---------|
| **A80/A81** | 多行 `\` 续行链 + 第二个测试方法 | 在 `"1.41"` 后添加 `or \\\n '_AUDIT_SCHEMA_VERSION = "1.42"' in cli` |
| **A80/A81** | 批量脚本导致 `"1.42"` 重复 | 替换 `'...1.42"\' in cli or \'_AUDIT_SCHEMA_VERSION = "1.42"\' in cli` → 去重 |
| **A94-A100 forward_compat** | 多行 `\` 链以 `"1.41" in cli, (` 结尾 | 在 `"1.41"` 行后添加 `'_AUDIT_SCHEMA_VERSION = "1.42"' in cli, (` |
| **A96-A100 exact match** | `assert '_AUDIT_SCHEMA_VERSION = "1.41"' in cli` (硬编码) | 改为 `or '_AUDIT_SCHEMA_VERSION = "1.42"' in cli` |

**验证**: 运行 `grep` 确认所有包含 "1.41" 的测试文件也包含 "1.42"。

### Phase 3: 回归测试

**4.6 运行回归**
```bash
cd D:\dev-frame-opencode\ai-workflow-hub
python -m pytest tests/ --tb=short -q \
  --deselect tests/test_paper_a20_real_e2e.py::TestA20CLIAgainstRealData::test_cli_list_shows_real_run \
  --deselect tests/test_paper_a24_artifact_binding.py::TestA24ArtifactChain::test_hash_stable_without_changes \
  --deselect tests/test_paper_a101_*.py::TestA101*::test_evidence_bundle_hash_in_manifest \
  --deselect tests/test_paper_a85_command_fidelity.py::TestA85CommandEcho::test_command_echo_contains_deselect
```

- A20, A24: known_flaky, 始终 deselect
- A101 circular test: 需要 finalized manifest, 只能 post-pack 验证
- A85 `test_command_echo_contains_deselect`: 读历史 manifest, 不反映新的 known_flaky 条目

### Phase 4: 打包 (pack_a101.py)

**4.7 九步流程**

| Step | 内容 | 输出 |
|------|------|------|
| 1 | Full Regression (带 deselects) | `output/REGRESSION_OUTPUT_A101.txt` |
| 2 | In-Scope Tests (从临时目录运行, ignore out-of-scope, deselect flaky+circular+A85) | `output/IN_SCOPE_TEST_RESULTS_A101.txt` |
| 3 | 计算 SHA256 (transcript hash + command hash + chain hash) | |
| 4 | 统计新测试数 | |
| 5 | 生成 Manifest (不含 bundle hash) | |
| 6 | 计算 evidence_bundle_hash | |
| 7 | 运行 validate_a101.py (pre-pack) | `output/VALIDATION_OUTPUT_A101.txt` |
| 8 | 构建 Evidence ZIP | `CDP_EVIDENCE_A101.zip` |
| 9 | **Post-Pack**: 解包 ZIP → 运行 validate → 运行 self-containment test → 重建 ZIP | `output/SELF_CONTAINMENT_OUTPUT_A101.txt` |

**关键**: Step 9 的 SELF_CONTAINMENT_OUTPUT 不进入 bundle hash（避免自引用哈希漂移）。

**4.8 Pack 要运行两次**: 第一次运行产生干净的 post-pack output；第二次 Step 7 读取第一次的 clean output 才能通过验证。

### Phase 5: CDP 提交

**4.9 提交 + 等待 + 捕获**
```bash
# 1. 提交
cd D:\dev-frame-opencode
python scripts/submit_a16_to_gpt.py \
  "D:\dev-frame-opencode\ai-workflow-hub\CDP_EVIDENCE_A101.zip" \
  "D:\dev-frame-opencode\ai-workflow-hub\scripts\GPT_REVIEW_PROMPT_A101.txt" \
  "D:\dev-frame-opencode\ai-workflow-hub\CDP_VERDICT_A101.txt"

# 2. 等待 120 秒 (GPT 通常需要 60-120s 生成回复)
python -c "import time; time.sleep(120)"

# 3. 检查回复是否就绪
python _check_cdp.py
# 看 "Last message length" 是否 > 500 chars 且 "Stop button visible: False"

# 4. 捕获完整回复
python recapture_cdp.py "D:\dev-frame-opencode\ai-workflow-hub\CDP_VERDICT_A101.txt"
```

**4.10 验证裁决**: 读取 `CDP_VERDICT_A101.txt`，确认第一行是 `ACCEPTED`。

---

## 5. validate 脚本必须检查的内容（从 A98 起的标准清单）

1. Schema version exact match (`"1.42"`)
2. Contract comment present (`"A101"`)
3. `_emit_json` at module level
4. Zero `console.print(json.dumps` calls
5. Click pin `>=8.2.0,<9` in pyproject.toml
6. known_flaky_tests.json valid (`total_known_flaky >= 1`)
7. Scope declaration exists
8. **Manifest 验证**: 所有 required keys, 正整数 counts, SHA256 格式 hashes
9. **Command echo hash binding**: regression_command_hash == SHA256(regression_command_echo)
10. **A87 Transcript chain**: chain_hash == SHA256(reg_sha + inscope_sha)
11. **A88 Bundle hash**: 重新计算并对比
12. **A89 Bundle coverage**: evidence_bundle_artifacts 列表精确匹配
13. **A90 Regression fail-closed**: transcript exit code = 0, 无 failed/error
14. **Cross-count consistency**: total = in_scope + out_of_scope, regression_passed >= in_scope_passed
15. **Validation determinism**: 无 random/time/datetime imports
16. **Verdict chain completeness**: A66-A100 (35个) verdict 文件全部存在且含 ACCEPTED/REJECTED
17. **Tamper detection summary**
18. **Known-flaky registry integrity**: JSON valid, required fields, deselect coverage
19. **ZIP self-containment**: ZIP 存在, 包含所有 required patterns
20. **_find_root() 动态路径发现**: validate 脚本不硬编码路径
21. **SELF_CONTAINMENT_OUTPUT**: 存在且包含 "ALL A101 CHECKS PASSED"
22. **GPT prompt integrity**: 长度 >= 200, 含 A101/1.42/schema/test/evidence/tamper/ACCEPTED/REJECTED

---

## 6. In-Scope 测试的特殊 Deselect 处理

在 pack 脚本的 Step 2 (in-scope tests) 中，以下测试必须 deselect:

| 测试 | 原因 |
|------|------|
| `test_evidence_bundle_hash_in_manifest` (当前 acceptance) | 循环依赖: 需要 finalized manifest, 但 manifest 在 Step 5 才生成 |
| `test_command_echo_contains_deselect` (A85) | 读 A85 历史 manifest, 不含新的 known_flaky 条目 |
| **verdict chain 测试** (如果检查 CDP verdict 文件) | 临时目录没有 verdict 文件（它们在 `context/` 子目录，但 in-scope 运行不复制 verdict 文件）|
| 所有 known_flaky (A20, A24) | 已知不稳定 |

**In-scope deselect 必须用相对路径** (如 `tests/test_paper_a101_xxx.py::Class::method`)，不能用绝对路径。绝对路径在 Windows 临时目录下会导致 pytest 无法匹配。

---

## 7. GPT Review Prompt 模板

```
A[N] Review Prompt — [标题]

You are reviewing the A[N] evidence pack for the ai-workflow-hub project.

A[N] validates [描述]:
- [检查项1]
- [检查项2]
- Preserves all A82-A[N-1] invariants including tamper detection

Schema version: [1.XX]
Key changes from A[N-1] ([1.XX-1]):
1. [变更1]
2. Preserves all A82-A[N-1] evidence, hash, and tamper detection

Evidence bundle artifacts (ordered):
1. src/ai_workflow_hub/cli.py
2. SCOPE_DECLARATION_A[N].txt
3. output/REGRESSION_OUTPUT_A[N].txt
4. output/IN_SCOPE_TEST_RESULTS_A[N].txt
5. known_flaky_tests.json
6. manifest_metadata

Evidence bundle hash integrity is verified via SHA256 chain.
VALIDATION_OUTPUT is EXCLUDED from bundle by design (prevents self-referential hash drift).
SELF_CONTAINMENT_OUTPUT is EXCLUDED from bundle by design (post-pack validation evidence).

Please review the evidence and respond with:
- ACCEPTED if all checks pass and the pack is complete
- REJECTED with specific blocking issues if any problems are found

For each rejection, provide the exact GPT directive for the next acceptance.
```

**必须包含的关键词**: A[N], schema版本号, schema, test, pass/result, evidence, bundle, tamper/hash/integrity, ACCEPTED, REJECTED

---

## 8. 已知问题与 Workaround

| 问题 | Workaround |
|------|-----------|
| Pack 脚本 Step 7 验证失败 (读旧 SELF_CONTAINMENT_OUTPUT) | **运行 pack 两次**: 第一次生成干净输出，第二次读取并通过 |
| A85 `test_command_echo_contains_deselect` 失败 | Deselect 该测试节点 (不改 A85 历史 manifest, 会破坏另一个测试) |
| 批量更新脚本导致 A80/A81 出现重复版本条目 | 手动替换 `'..."1.XX"' in cli or '..."1.XX"' in cli` → 去重 |
| A94-A100 多行 forward_compat 链漏更新 | 手动在 `"1.XX" in cli, (` 前添加新版本行 |
| A96-A100 exact match 断言硬编码旧版本 | 改为 `or '_AUDIT_SCHEMA_VERSION = "1.XX"' in cli` |
| CDP 首次捕获只拿到短回复 (GPT 还在生成) | 等 120s → `_check_cdp.py` 检查 → `recapture_cdp.py` 重新捕获 |
| In-scope verdict chain 测试在临时目录找不到 verdict 文件 | Deselect 这些测试 (它们验证外部 artifact, 由 validate 脚本覆盖) |

---

## 9. 技术架构要点（A98 起确立）

### 分阶段验证 (Phased Validation)
解决循环依赖的核心思路: pre-pack 生成 transcript (不含 circular test), post-pack 解包最终 ZIP 运行完整验证。

### Bundle Hash 排除策略
- `VALIDATION_OUTPUT`: 排除（因为验证结果本身会改变 transcript）
- `SELF_CONTAINMENT_OUTPUT`: 排除（因为是 post-pack 产物，生成时 bundle hash 已确定）

### Evidence ZIP 内部结构
```
a[N]-evidence/
├── src/ai_workflow_hub/cli.py (+ support modules)
├── pyproject.toml
├── tests/test_paper_a*.py (全部 83 个)
├── known_flaky_tests.json
├── SCOPE_DECLARATION_A[N].txt
├── COUNTS_MANIFEST_A[N].json
├── scripts/validate_a[N].py
├── scripts/GPT_REVIEW_PROMPT_A[N].txt
├── scripts/pack_a[N].py
├── output/VALIDATION_OUTPUT_A[N].txt
├── output/REGRESSION_OUTPUT_A[N].txt
├── output/IN_SCOPE_TEST_RESULTS_A[N].txt
├── output/SELF_CONTAINMENT_OUTPUT_A[N].txt
└── context/CDP_VERDICT_A{66-N-1}.txt (所有历史 verdict)
```

### _find_root() 模式
所有 validate 脚本必须用 `_find_root()` 动态发现项目根目录，支持两种运行环境:
- **project-root**: `scripts/` 的 parent 就是项目根
- **unpacked-ZIP**: `scripts/` 的 parent 是 `a[N]-evidence/` 目录

---

## 10. 快速启动检查清单 (给 Codex)

开始 A101 前确认:

- [ ] Chrome 已启动并带 `--remote-debugging-port=9222`
- [ ] ChatGPT 对话 `https://chatgpt.com/c/6a2e02e2-5ff8-83ee-8718-95ff5ac4242f` 可访问
- [ ] `_check_cdp.py` 能连接到 CDP 并返回消息数
- [ ] `submit_a16_to_gpt.py` 的 CHAT_ID 是 `6a2e02e2-5ff8-83ee-8718-95ff5ac4242f`
- [ ] `recapture_cdp.py` 的 CHAT_ID 同上
- [ ] `_check_cdp.py` 的 CHAT_ID 同上
- [ ] `cli.py` 的 `_AUDIT_SCHEMA_VERSION` 当前是 `"1.41"` (将 bump 到 `"1.42"`)
- [ ] `known_flaky_tests.json` 有 2 条记录 (A20, A24)
- [ ] 测试文件数: 83 (A101 后应为 84)
- [ ] Verdict 文件: A66-A100 全部存在

### A101 执行命令序列
```bash
# 1. Bump schema + 添加 contract comment
# (编辑 cli.py)

# 2. 创建测试/validate/pack/prompt 文件
# (基于 A100 模板修改)

# 3. 批量更新 OR chains
python _fix_schema_142.py

# 4. 手动修复边缘 case (A80/A81, A94-A100 forward_compat, exact match)

# 5. 回归测试
python -m pytest tests/ --tb=short -q [deselects...]

# 6. 打包 (第一次)
python scripts/pack_a101.py

# 7. 打包 (第二次 - 获取干净的 SELF_CONTAINMENT_OUTPUT)
python scripts/pack_a101.py

# 8. 提交 CDP
cd D:\dev-frame-opencode
python scripts/submit_a16_to_gpt.py [ZIP] [PROMPT] [OUTPUT]

# 9. 等待 + 捕获
python -c "import time; time.sleep(120)"
python _check_cdp.py
python recapture_cdp.py [OUTPUT]

# 10. 验证裁决
head -1 D:\dev-frame-opencode\ai-workflow-hub\CDP_VERDICT_A101.txt
# 应为: ACCEPTED
```

---

## 11. 用户偏好

- **语言**: 中文
- **核心指令**: "继续，不要停下来，走流程" / "继续推进，对于这种推进的事情，不用询问我"
- **遇到问题时**: "向GPT询问解决办法，然后执行"
- **不要问**: 不需要在推进过程中询问用户确认
- **自动化程度**: 最大化自动化，只在真正的 blocker 处停下报告
