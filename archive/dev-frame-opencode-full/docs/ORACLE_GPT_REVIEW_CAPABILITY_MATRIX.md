# Oracle GPT Review 能力矩阵

每项能力标注状态、证据、是否已固化。

| 能力 | 状态 | 证据 | 固化 |
|------|------|------|------|
| Oracle evidence pack 生成 | **正式** | `tools/oracle_s2_review_pack.py`，已打包 s2-gpt-review-evidence-pack.zip | ✅ |
| Chrome CDP 启动与连接 | **正式** | Chrome 独立 profile，端口 9222，Playwright connect_over_cdp | ✅ |
| 指定 GPT 会话 URL handoff | **正式** | `TARGET_CHATGPT_URL.txt`，不再搜索标题 | ✅ |
| GPT_REVIEW_PROMPT 自动粘贴 | **正式** | full review flow 中自动粘贴，多次验证通过 | ✅ |
| zip evidence pack 自动上传 | **正式** | `set_input_files` auto_success，多次验证通过 | ✅ |
| SEND 确认 gate | **正式** | 用户输入 SEND 才允许点击发送，非交互环境 EOFError 降级 | ✅ |
| GPT 新回复监控 | **正式** | assistant count 增加检测 + stop 按钮检测 + 内容稳定检测 | ✅ |
| GPT 回复抓取与保存 | **正式** | 区分用户 prompt 和 assistant 回复，内容评分制 | ✅ |
| GPT decision 解析 | **正式** | parse_decision 函数，多轮验证通过 | ✅ |
| Full review flow | **正式** | `oracle_gpt_full_review_flow.py`，多次端到端验证通过 | ✅ |
| 单轮 review loop | **正式** | `oracle_gpt_review_loop_once.py`，已跑通 | ✅ |
| 多轮 loop harness | **正式** | `oracle_gpt_review_loop.py`，dry-run + live 验证通过 | ✅ |
| stop_on_human_required | **正式** | harness dry-run 验证：检测到 human_required 正确停止 | ✅ |
| 中文 auto_non_human loop | **正式** | 1 轮中文 loop 跑通，GPT 正常回复并解析 | ✅ |
| 交叉字段校验（validate_result） | **正式** | 3 个回归测试，self_check_report.py 独立校验 | ✅ |
| 自动 multi-round reconciliation | **实验性** | 中文 loop 中已验证可处理无争议问题，但中文内容生成质量待优化 | ⚠️ |
| 自动 GPT 回复内容解析（中文） | **实验性** | 中文 GPT 回复解析基本准确，但中文语义的 decision 判断偶有边界情况 | ⚠️ |
| 完全无人值守 loop | **未验证** | 尚未测试零人工干预的全自动 loop | ❌ |
| pre-S2 baseline 生成 | **不可能自动** | 需要 S2 开始前的 git status 快照 | N/A |

## 固化状态统计

| 状态 | 数量 |
|------|------|
| 正式 | 15 |
| 实验性 | 2 |
| 未验证 | 1 |
| 不可能自动 | 1 |
