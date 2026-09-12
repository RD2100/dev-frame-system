# Shadow 最小真闭环 — Round 1 任务注册表

总控：本会话（Claude desktop，D:\dsh-devframe）。目标：让 Shadow 从"机制骨架"追平设计预期（docs/detailDesign-part2.md）的最小真闭环——投递真正驱动 controller 工作、执行链进入组合、Shadow 工具面收敛到设计 allowlist。

## 环境硬约束（2026-09-11 核实）

- 本机当前**无 node / pnpm / git**（注册表 PATH + 全盘探测证实；F:\env 只有安装包）。**所有实现 agent 禁止运行 pnpm/node/git/vitest，禁止声称任何测试已运行，禁止提交。**
- 交付形态：工作树改动，静态自审。验证（真实 Loader 组合测试、typecheck、lint）待工具链恢复后由总控执行。
- 无 DEEPSEEK_API_KEY → 验证一律 keyless（mock model / 无密钥组合测试）。

## 任务与所有权（严格分区，防冲突）

| 任务 | Owner agent | 所有权范围 | 交付物 |
| --- | --- | --- | --- |
| T1 交付转发桥 | bridge-impl | packages/experimental/shadow-bridge/**（新包）+ 对应 Agent Note | 新包 @deepseek-ai/dsh-experimental-shadow-bridge：把 shadow-router 中 `received` 且绑定有授权 open run 的 work 投递，转发为绑定 controller 会话的 durable followup（模型可见⟺已记录）；`shadow_bridge` 存储域记录已转发 messageId 保证跨重启恰好一次；v1 仅 live controller（不冷恢复）；不自动 completeDelivery（完成是 controller 侧事实，留给 goal 回执接线）；keyless real-Loader 组合测试 |
| T2 组合装配示例 | compose-impl | apps/cli/config/examples/shadow-loop/**（新目录） | 示例 patch：在 devframe-profile 之上配置 shadow-router（REPLACE 占位符风格，沿用 apps/cli/config/examples/shadow/ 惯例）+ 挂载 shadow-bridge、agent-evidence、project-controller 四个 consumer 子路径及其必填 config；附安装说明 README（若兄弟示例有此惯例） |
| T3 Shadow allowlist 收敛 | allowlist-impl | packages/experimental/shadow-controller/** | shadow-agent factory setup 内对该 scope 执行 tools.restrict：模型面仅剩四个对话工具 + 已注册的 memory 工具；router 的 project_* 在该 scope 自然不可见（双工具面收敛）；README 双语更新 Known Limitations；Agent Note 记录 host 侧 restrict 决策与备选 |

## 共享契约（T1/T2 依赖，总控裁定）

- 包名 `@deepseek-ai/dsh-experimental-shadow-bridge`；行 id `shadow-bridge`；function plugin，`name: 'shadow-bridge'`，具名导出 name/inject/Config/apply，无 default export。
- Config：`intervalMs`（必填正整数，轮询投递节奏）、`followupMaxChars`（必填正整数，转发文本上限）。后续字段由 T1 实现按仓库惯例增补并在 README 声明。

## 验收（总控执行——2026-09-11 已完成）

1. ✅ T2：结构/语义/占位符验收通过；controllerSessionId 拓扑注释已按设计更正（独立 controller 根，非 Shadow 会话）；独立占位符已拆分。
2. ✅ T1：代码审读通过（门禁含 goalId/acceptanceHash 匹配，设计 §Delivery 全文实现）；6 个测试失败根因为 harness 假件接缝 + 组合测试种子缺 goal 字段（均在测试侧，实现无改），修复后 27/27；`tsc -b` 绿；README/Note 三元组 sidecar 配对通过。
3. ✅ T3：三重收敛机制（presentAs native + restrict 继承面 + guard 执行守卫）审读通过；schema 残余可见性如实入档（结构性限制：自有层豁免，路由器侧收敛列为后续任务）；处置测试根因为 bench 根 fiber restart 语义未达 agent 本体，测试已搬到宿主行 fiber 精确所有权边界，28/28；zh 链接语区已修。
4. ✅ 总控侧登记：tsconfig.base.json 手写别名（生成器约定 `dsh-<叶子目录>`，experimental 组名不匹配）、tsconfig.host.json reference、apps/cli dependencies 三包（首误入 devDependencies，已移正）。
5. ✅ 最终验证轮（09-11 09:17）：pnpm install 绿；verify-cordis-config 153 文件通过；verify-translation-pairing 1204 对一致；shadow-controller + shadow-bridge 55/55；`tsc -b` 两包绿；test:docs 见下。
6. ✅ 文档基线债务（09-06..09-11 未提交工作遗留）：4 个 README 的 Model Experience 结构、agent-evidence 锚点、subagent.md type-equiv 粘贴漂移、doc-standard 2 例（frontmatter kind + zh Dev Note 标题）、devframe-profile 坏链——清理 agent 修 18 个文档文件后 test:docs 15 叶门禁全绿（总控独立复跑 exit 0）。
7. 残留说明：`.agents/devframe/archive-candidate-b6/`（settings.yaml + candidate.patch.yml，文件时间戳 2026-09-08，本轮期间出现在 git 状态，非本轮 agent 创建）——待用户处置。
8. 遗留（后续轮）：路由器侧单工具面收敛（消除 schema 残余可见性）；投递完成结算接 goal 回执；controller 冷恢复转发；keyless 组合级端到端快照场景（test:snapshot 是 CI 信号）；完整 doc-sync（website 构建）未跑。

## 基线（2026-09-11 更正）

**更正**：会话启动快照显示 clean 不准确。实际工作树自 2026-09-06 起承载未提交工作（09-10/09-11 Shadow 对话面改动、devframe-profile/session-controller/client-ui-shadow-entry 等），另有数百个 `src/**/*.d.ts.map`（旧 tsc 误运行残留）与根目录 `_tmp_*` 垃圾文件。总控已在验收前固化基线快照：`%TEMP%\dsh-baseline-tracked.diff`（273KB）+ `%TEMP%\dsh-baseline-status.txt`（433 条），验收 diff 一律相对该快照；既有 stash×2（codex/v14-llmargs、devframe recovery）不动。

本轮预期改动仅限任务所有权范围 + 本注册表文件 + .agents/notes/ 下对应 Note 三元组。工具链（git 2.55.0 @ D:\Git、node 24.19.0 @ D:\nodejs zip、pnpm 11.7.0 @ F:\.local-toolchain\bin）已恢复；C 盘 Node MSI 卸载两次 1603（MSI 缓存损坏），残留在"应用与功能"待用户手动清理。验证方案（需用户批准的工具链安装 / gh 授权推送）在实现完成后单独呈报。
