# `project_commit` Consumer 设计记录（已应用 · v14 remaining）

状态：**已应用（v3 定稿）**。代码草稿已删除；产品面以主树为准：

- `packages/experimental/project-controller/src/commit-consumer.ts` —— 工具与四道闸（本记录第 2-5 节）。
- `packages/experimental/project-controller/src/delivery-consumer.ts` —— 接线：`commitPathsByTask` Config、scope 构造校验、`jobs: () => ctx.get('jobs')`、`resolveOwnerHead`（workspaceRegistry × worktreeRegistry 行解析）。
- `packages/experimental/project-controller/tests/commit-consumer.spec.ts` —— 真 Loader 组合 22 例，含两条反例用例与两条 focused 拒绝路径。
- `scripts/gen-tool-catalog.ts` —— delivery 入口桩补 `commit` seam；`docs/tool-catalog.md` 已再生（+project_commit）。
- README.md / README.zh.md —— 挂载行、Config、commit 流程与工具清单已更新。

## 1. 目标与背景

worker shell 的 `git add`/`git commit` 被沙箱挡在 anchor 仓库的 `.git/worktrees/*/index.lock`（EACCES），而 `project_deliver` 要求干净已提交的 Worker 工作树。方案：worker 只写文件，经角色工具 `project_commit` 由 host 调用 worktree-registry 受控 commit Service（main @ f81a5cd9f6）；worker 侧无任何 shell git 权限扩张。

## 2. V1.2 四点修正（定稿语义）

1. **授权 = Config 显式 per-task `commitPathsByTask` 映射**（zod `z.dict(z.array(z.string()))`，optional；apply 时经导出的 `normalizeCommitPaths` 校验并构建 Map，坏条目报 `Invalid host commit path scope for task X`）。缺项在调用时拒绝（`requires a host-registered commit path scope for task X`）；模型路径 ⊆ scope（超集拒绝并列出越界路径）。**Config 映射即授权事实源**，取代 v1 的 diff 交叉核对；消费者侧无任何 dirty/status 扫描（plain `git status` 会执行检出控制的 clean filter，且 dirty 集不构成授权）。
2. **删除消费者重复的 dirty/status 扫描**：唯一保留的 git 调用是 owner 侧 `rev-parse --verify --end-of-options refs/heads/<branch>`（纯引用读，无 index/filter/fsmonitor）。Service 是 Git 唯一 owner（pinned gitdir、hooksPath 隔离、filter 拒绝、expected HEAD 复核、显式 pathspec）。
3. **HEAD 观察规范**：owner workspace 可信路径来自 registry 行（`resolveOwnerHead`，绝不 cwd 到 Worker `.git` 指针）；在 owner 仓库上读已登记分支引用；本地 trim + 40/64-hex OID 校验；单次观察原样携带进请求，Service 在 pinned gitdir 内复核 branch+expectedHead——观察只是预检。
4. **quiescence = JobRegistry 非终态写作业零存在**：每次调用解析 `ctx.get('jobs')`（**absent ≠ quiet**：缺失即拒绝 `requires the background job registry`）；`list(exec.agent)` 中存在 `running|stopping` → 拒绝（`requires a quiet worktree: N non-terminal background job(s)...`），绝不杀用户作业；HEAD 观察 await 之后、Service 调用之前**二次复核**。边界如实声明：serial(taskId) 只互斥 commit/deliver/review 族，job gate 是瞬时证据、不是 OS 锁；第二次复核后新出现的作业由 Service 自身验证与交付闸兜底。serial 仅保留为互斥层。

## 3. 多轮提交与未核实面

请求路径 ⊆ scope（非全等）→ 允许多轮提交。提交后 `clean=false` 是**成功结果**并显式报告 `pending changes remain and their ownership is unverified; resolve them through the host before project_deliver`（提交已成功，报错会因 expectedHead 前移毒化重试）；交付闸继续要求完全清洁。

## 4. 两条反例用例（审查清单预览，均已落测）

1. **Worker .git 重定向**：把 worker 检出的 `.git` 指针改写指向另一注册工作树 → Service 元数据校验拒绝 `does not belong`（owner 侧引用观察不受影响）；另一树 HEAD 不变、无暂存。
2. **stale HEAD**：在观察与 Service 调用之间注入 `--allow-empty` 干扰提交 → Service 拒绝 `expected HEAD`；无暂存残留。

两条 focused 拒绝路径（缺 jobs 服务、观察期间新增作业——经 `jobs.list` 计数包装在第 5 次 resolve 前插入真实作业）均有独立用例。

## 5. 覆盖面备注

- `/* v8 ignore */` 仅两处并带理由：非 ENOENT lstat 故障、`--verify` 成功却非完整 OID（fixture 内无自然触发）。
- 守卫翻转用例经 `worktreeRegistry.list` 计数（第 5 次=观察后终守卫的 resolve）改 branch 摘要触发 `Commit authority changed`。
- 状态闸用例经 `projectController.block(task-b)` 到达（planned 无 assignee 时 resolve 先拒，blocked 可达 `requires a developing task`）。
- 越界包含检查用 Windows junction / POSIX symlink 双平台触发。

## 6. 遗留风险（如实声明）

- scope 路径上的用户手工编辑与 worker 编辑按路径不可区分——Config scope 界定爆炸半径。
- Service 暂存与 clean 读之间完成的写入 → 走 clean=false 未核实面（不静默吞掉）。
- Service 暂存前完成的写入会进入提交（受 scope 限定）。
- 测试 devDependency `@deepseek-ai/dsh-jobs-local`（workspace:^）：真实 registry 面不 mock；vitest 经 tsconfig paths 解析。**pnpm-lock 的 project-controller importer 需总控同步**（见报告），同步前全仓 pnpm 脚本会因 lockfile 不满足而拒绝执行。

## 7. 合并期待办（报总控/审查者）

- pnpm-lock importer 同步（总控唯一写入权）+ 一致性检查。
- Agent Note（非平凡变更）同 PR 提供；recorded-session 快照场景与 roleToolPolicies worker 行（`project_commit`）是否需要由总控定夺（A2 候选场景 commitPaths 填充亦然）。
- catalog 已再生；`gen-tool-catalog.spec.ts` 期望列表随再生文档一致。
