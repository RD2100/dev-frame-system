# Shadow Todo 看板 v2 — 阶段 B 代码验收意见

- 验收对象：`feat/desktop-quality-fixes` 分支未提交的 10 个文件改动 + 2 个未跟踪文件
- 验收依据：计划 §2B（HITL RPC / 注册时序 / Goal 生命周期）+ §4 验收 2/3；评审 r1（P0-2 必须复用全部前置断言）、r2（P1-2 beforePersist / P1-3 靠下游 authority 门）、r3（通过）
- 验收方式：两名评审员并行，一路对照源码逐条亲验，一路读测试源码 + 复跑套件 + git diff 范围核对
- 验收日期：2026-09-20
- **结论：通过。** 6 项源码保真度全部符合、无断言删除；三套测试 + tsc 实测全绿；回归范围干净。3 条 P2 收尾项（git add / 清理临时文件）不阻断；2 条 P1 为阶段 C/D 的集成前置，不在本阶段打回。

---

## 一、源码保真度（6/6 符合）

| # | 验收点 | 判定 | 证据 |
|---|---|---|---|
| 1 | `start-authority.ts` 完整复刻 task-consumer.ts:88-102 全部断言 | 符合 | resolveTaskStartAuthority :105-131 逐条对照旧断言：恰一 worker、lead role/parent/pluginId、worker/lead agent 在线且 cwd 对齐、两个 lockedBy、三个独立 worktree（:127-128 `Set().size===3`）。无一条删除/弱化。taskStartUnchanged :154-170 复现 signature 重比对；StoppedState 以 `isStopped` 回调注入替代旧 :61 闭包。 |
| 2 | task-consumer 改造后行为一致 | 符合 | plan 分支 :60-67 用 resolveControllerAuthority + beforePersist；start 分支 :70-80 用 resolveTaskStartAuthority + taskStartUnchanged 作 :73/:78 写边界复检。逐行同构旧版 :113-118，tails 串行与 stop effect 保留。 |
| 3 | delivery-consumer 动态注册面 + 拒点未弱化 | 符合 | TaskDeliveryRegistration :33-43（digest 必填、commitPaths 可选）；ProjectDeliveryRegistry :54-69；live map :127；拒点迁移至 :256-257（`checksByTask.get` undefined → throw 'Task has no host-approved checkset'）；register 写 :558 与 deliver 读 :256 同 key。commitPaths 省略 → commit-consumer.ts:303-306 抛错 fail-closed，不静默放行。 |
| 4 | approveTask 链顺序 / realpath 先行 / beforePersist / 无伪 caller 校验 | 符合 | shadow-controller/index.ts:193-230：requireRouter :194 → findBinding ready :195-196 → resolveTaskStartAuthority :198 → planned 门 :199 → registry 在场 :200-201 → **realpathNormalize :202 先于** store.save :207-208 → registerTask（commitPaths 可选）:213-216 → **assign :219 与 startDevelopment :222 均带 `{ beforePersist: unchanged }`** → followup :224 → boardNotify :228。方法体无 request 自报 caller 字段，身份来源仅 binding.controllerSessionId → 下游 authority 门，与 r3 结论一致。无 try/catch 吞错，boardNotify best-effort 外全部 fail-loud 上抛。 |
| 5 | rejectTask 链 | 符合 | :241-255：planned 门 :246-247 → block 三元组（blockedReason/nextAction/wakeCondition）:248-252 → boardNotify :253。 |
| 6 | types.ts commitPaths 可选 + index.ts 真导出 | 符合 | ShadowApproveTaskInput.commitPaths?: readonly string[]（types.ts:88）；project-controller/index.ts:16-17 真导出三个函数 + 两个类型，shadow-controller/index.ts:51 真 import 消费。 |

## 二、测试实测（非口头转述）

| 套件 | 实际命令 | exit code | 结果 |
|---|---|---|---|
| shadow-controller | `vitest run .../shadow-controller.host.spec.ts` | 0 | **17/17 passed** |
| commit-consumer | `vitest run .../commit-consumer.spec.ts` | 0 | **26/26 passed**（86s，process-bound） |
| project-controller 全量 | `vitest run packages/experimental/project-controller/tests` | 0 | **16 文件 / 164 测试全过**（210s；含 request-budget、at2b-04/05/06、at4-05 全部既有套件） |
| shadow-controller `tsc -b` | `cd shadow-controller; tsc -b` | 0 | 无报错 |

> 验收员中途在 start-authority.ts:168 抓到一次 PARSE_ERROR（未闭合字符串），但该文件在两次读取之间被外部编辑修正；修正后复跑全部全绿，tsc exit 0。**当前磁盘状态无语法错误**。提醒：该文件仍未 `git add`，建议尽快提交以锁定此正确状态。

## 三、两条必备路径覆盖

- **路径乙「未 approve 直接 deliver 被拒」——真覆盖 ✅**：commit-consumer.spec.ts:607（+ :651 复证）。真实 Loader composition（真 ProjectController / 真 delivery-consumer / 真 git / 真 worktree-registry），seedChecks:false、不注册，断言 deliver 报错文本正是 delivery-consumer.ts:256-257 的 throw。
- **路径甲「approve → 注册 → start → deliver 成功」——跨文件组合覆盖（按验收标准允许的方式）**：
  - 上半段 shadow-controller.host.spec.ts:284：真 controller.approveTask，断言 registerTask 调用形态（digest 任意字符串、assign/startDevelopment 均带 beforePersist:fn）、postMessage 文案。projectController 与 registerTask 此处为 mock。
  - 下半段 commit-consumer.spec.ts:615：真 FileRequiredChecksConfigStore.save + 真 registerTask + 真 commit + 真 deliver → reviewing。
  - 组合接缝：approveTask 调 store.save 后直接用返回 digest 注册（无第二处自算 digest），故 digest 一致性由 store 自身保证；cwd 逃逸拒绝由 :633 用例锁定。

## 四、回归范围

- `git status --short`：改动 10 文件与验收对象完全吻合，无夹带。
- `git diff --stat`：+451/−57。request-budget-consumer、at2b-04/05/06、at4-05 及对应测试源码**均不在改动列表**（只在全量回归中被跑过，全绿）。
- `pnpm-lock.yaml`：仅 +9 行，全部落在 shadow-controller importer 块，新增 devframe / project-contracts / project-contracts 三个 workspace link，正是计划要求。

---

## P1 — 阶段 C/D 集成前置（不在本阶段打回，记录在案）

1. **commitPaths 与 deliver 闭环的部署配置**：桌面默认 approveTask 不传 commitPaths（types.ts:88 可选、index.ts:209-212 注释明示），则 worker 产出后 project_commit 在 commit-consumer.ts:303-306 恒拒，而 deliver 要求 worktree 干净（delivery-consumer.ts:215 `git status --porcelain === ''`）。即 fail-closed 设计下，**首轮全链路闭环要跑通，部署方在 approve 时必须 pin commitPaths**。这不是代码缺陷，是阶段 C 部署配置必须显式决定的一件事。
2. **路径甲的 digest 接缝可再收紧**：当前 approveTask 算出的 check 配置（checkId 'git-diff-check' / executable 'git' / args ['diff','--check'] / cwd=realpath）未在任何一条用例里与"真 store.save → 真 deliver"串成一链。建议阶段 C 加一条集成用例，或在 shadow-controller.host.spec.ts:284 把 `{digest}` 与 store 真实 digest 等值断言。非阻断。

## P2 — 收尾项（提交前顺手做）

1. `packages/experimental/project-controller/src/start-authority.ts` 是抽取 authority 的新源文件（task-consumer.ts:10、index.ts:16、shadow-controller index.ts:51 均 import），**仍未 `git add`**，提交前补上。
2. 清理 stray 临时文件：`docs/working/tmp-pc-full.txt`（及验收过程产生的 `tmp-pc-run.txt`）不进 PR。
3. **已知偏离确认（记录，不判打回）**：GoalBinding.taskIds 仍为静态 `['devframe-goal']`（development-project.ts:151），无 update_goal 动态追加；任意非 'devframe-goal' 的 taskId 在 start-authority.ts:87 必抛错。首轮闭环用静态 taskId 走通，多轮任务机制按计划记为开放项，不进本阶段验收。

---

## 终审
阶段 B 代码与 r3 通过的计划保真，测试实测全绿，无回归。可进入阶段 C（看板 UI + readBoard 投影）。上述 P1-1 必须在阶段 C 部署配置中明确，否则全链路 e2e 在 commit 步停住。
