# AT3-07 Worker 记录（总控令：双轨——B 线组长亲收 AT2-05 + 派 Worker 做 AT3-07）

**移交声明（防双写）**：派发前我未动过 project-controller 域（零写入），AT3-07 全权由 Worker 在独立 worktree 执行。

## Worker 要素

| 项 | 值 |
| --- | --- |
| 路由 | 显式 pinned `{provider:'huoshan-2', model:'glm-5.3-flash'}`（总控令；workflow agent 独立 LLM 目标） |
| worktree | `D:\dsh-udeliver-at37`（我建，branch `codex/v14-udeliver-at37`，起点=我的 tip ec27a5c6ce） |
| 任务书要点 | 目标=AT3-07 任务级联动半边（controller 旅程 × memory_unavailable 警告）；域=`packages/experimental/project-controller/tests/` 新 journey spec；三断言：A1 编码任务遇 memory 不可用带可观察警告完成 / A2 失败保存无成功 receipt / A3 memory-only 仍失败；只读参考=project-memory failure.spec + agent-rehydration.spec；**警告契约缺失则先报缺口（文件+行为），不编造测试、不改产品代码**；每命令真实退出码；`git diff --cached --check`=0 后 `--no-verify` 提交；不 push/PR；主树 D:\dsh-devframe 只读；429 有限退避禁密集重试 |

## Worker 结果（VERDICT: gap）

- **缺口报告**：`.agents/devframe/v14-udeliver/at37-gap-report.md`（Worker 树内提交 **ca832388d3**）；未落地任何 spec，未改任何产品代码。
- 核心发现（Worker 逐文件核实）：
  1. `project-controller/src/controller.ts` 任务机（createTask…complete/block/fail/resume）**零 memory 感知**：`complete(taskId)` 无警告参数、无完成事件（src 无 ctx.emit/event-map）、无工具面；
  2. `spec.ts` taskRecordSchema 与 `project-contracts` 共享 TaskRecord 均**无 warnings/memory 字段**；
  3. project-controller **未依赖** project-memory（连 dev 依赖都没有）——test-only journey spec 无法挂载 memory 插件（需 manifest 变更，超出本片只测范围）；
  4. A2 的包级诚实**已在 project-memory 侧成立**（失败 append 不落 receipt，failure.spec 证实），但 controller 旅程从不调用 memory，本包无法断言联动；
  5. 最小契约提案：TaskRecord 增可选 `warnings?: readonly TaskWarning[]`（封闭联合对齐 MEMORY_UNAVAILABLE）+ `complete(taskId, outcome?)` 扩展 + createTask 增 `deliverable` 区分（memory 交付遇不可用走既有 fail() 拒绝完成）。
- Worker 真实退出码：pnpm install 0；邻居回归 `project-controller/tests` 4 files/18 tests passed exit 0；diff --check 0；commit ca832388d3 exit 0；post-commit porcelain clean。
- 无 429 发生（Worker 全程未报告限流）。

## 裁定请求

AT3-07 的警告契约缺口=**产品实现缺口**（非测试缺口）：需总控裁定是否开产品片（TaskRecord warnings 字段 + complete 扩展 + 依赖接线，涉及 project-contracts 共享类型与 taskRecordSchema 演进）。测试片在契约落地后可即补（Worker 已给最小契约提案与断言映射）。
