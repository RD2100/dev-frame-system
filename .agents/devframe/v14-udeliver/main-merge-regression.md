# main 合并回归验证记录（codex/v14-udeliver-lead × main）

- 运行时间：2026-09-08 03:03–03:09 (+09:00)
- 工作树：`D:\dsh-devframe-v14-udeliver-lead`，branch `codex/v14-udeliver-lead`
- HEAD：`3db114fcde`（"merge: main into codex/v14-udeliver-lead (main-merge regression baseline)"）
  - 第一父 = `8bfe2d28ad`（AT1-10 stop/abandon 切片，本任务基线，`git merge-base --is-ancestor` 确认为 HEAD 祖先）
  - 第二父 = `1980fb629d`（main tip）
- 树净：`git status --porcelain` 输出为空
- 环境：Node v24.19.0（codex-primary-runtime），vitest v4.1.8
- 统一命令形态：`node node_modules/vitest/vitest.mjs <tests目录或spec路径>`（`$env:CI='true'` 保证 run-once）
- 纪律遵守：零 src 写入、零 build/pnpm/依赖安装、零 git 写操作（仅只读 status/show/diff/merge-base）、零模型探针

## 阶梯结果

| # | 套件 | 文件数 | 通过 | 失败 | 退出码 |
|---|------|--------|------|------|--------|
| 1 | tool-workflow（invariant / background-composition / tool-workflow） | 3 | 59 tests | 0 | 0 |
| 2 | tool-jobs（tool-jobs.spec.ts） | 1 | 42 tests | 0 | 0 |
| 3a | agent-reliability 全套件 | 8 | 38 tests | 0 | 0 |
| 3b | devframe reliability/stop/goal-binding（reliability/stop、reliability/stop-persistence-failure、reliability/stop-writer-exclusion、goal-binding、goal-binding-file-store） | 5 | 80 tests | 0 | 0 |
| 4 | command-goal-binding 全套件 | 6 | 56 tests | 0 | 0 |
| 5 | agent-dispatch 全套件 | 4 | 0 tests（4 suite 导入期失败） | 4 | 1 |

绿面合计：23 个测试文件、275 个测试全过、exit 0。红面：仅阶梯 5，见登记 #1。

## 缺陷登记（仅登记，未修任何源文件）

### 登记 #1：agent-dispatch 全套件导入期红 — `@deepseek-ai/dsh-experimental-project-controller/request-budget-consumer` 包解析失败

- 现象：4/4 spec（agent-dispatch、dispatch-consumer、durable-ack、loader-composition）0 test 执行，suite 级 ERR_MODULE_NOT_FOUND，exit 1。
- 位置：`packages/experimental/agent-dispatch/src/consumer.ts:22`
  `import { apply as requestBudgetApply } from '@deepseek-ai/dsh-experimental-project-controller/request-budget-consumer'`
  （经 `packages/experimental/agent-dispatch/src/index.ts:30` 进入；durable-ack / dispatch-consumer / loader-composition 均经同一链路失败。）
- 失败错误原文摘录：
  `Error: Cannot find package '@deepseek-ai/dsh-experimental-project-controller/request-budget-consumer' imported from D:/dsh-devframe-v14-udeliver-lead/packages/experimental/agent-dispatch/src/consumer.ts`
- 解析链归因（只读证据）：
  1. `tsconfig.base.json:239-242` 仅为 root、`./consumer`、`./task-consumer`、`./delivery-consumer` 四个 specifier 配了 src paths 映射，**没有** `@deepseek-ai/dsh-experimental-project-controller/request-budget-consumer` 条目 → vite-tsconfig-paths 不命中，落回 package exports。
  2. `packages/experimental/project-controller/package.json` exports 将 `'./request-budget-consumer'` 指向 `./lib/request-budget-consumer.js`；本树 `lib/` 根目录仅有 `index.js`、`types/`、`tsconfig.tsbuildinfo`，**缺 `lib/request-budget-consumer.js`**（`lib/types/request-budget-consumer.js` 存在但 exports 不指向它）→ ERR_MODULE_NOT_FOUND。
  3. 全仓库唯一 importer 即 `consumer.ts:22`（grep 全 packages 无第二处）。
- 预存在判断（只读对照基线 `8bfe2d28ad`）：
  - 该 import 行在基线与 HEAD **逐字相同**（`git show` 两树比对一致）；
  - `git diff 8bfe2d28ad HEAD -- tsconfig.base.json` 为空，`git diff 8bfe2d28ad HEAD -- packages/experimental/project-controller` 为空（merge 未触碰映射与 exports）；
  - lib 产物属未纳管构建产物，当前缺失；merge 是纯 git 操作不可能改变它。
  - 结论：源面与接线面在两树完全等同，同条件下基线同样无法解析 → **非本 merge commit 引入**。未重放基线运行（checkout 属禁用的 git 写操作），此判断基于上述只读等同证据，而非基线重跑。
  - 备注：基线声明"334 过"与当前绿面 275 的差值 59 与 agent-dispatch 静态用例数（顶层 `it(` 计 22，helper 循环/each 变体未计入）无法精确对账；若基线 334 确含 agent-dispatch，则说明两次运行之间 lib 产物状态发生过变化（环境面，git 不可见）。两种读法均不改变"merge 未引入"的结论。
- 怀疑面：project-controller 构建产物缺失（零 build 纪律内不可修复）+ `tsconfig.base.json` 缺该子路径 src 映射（真实接线缺口，与其三个兄弟子路径不对称）。
- owner 归属建议：project-controller / agent-dispatch owner。候选修法（均超出本 worker 授权，未执行）：
  1. `tsconfig.base.json` 增补 `"@deepseek-ai/dsh-experimental-project-controller/request-budget-consumer": ["./packages/experimental/project-controller/src/request-budget-consumer.ts"]`，与其兄弟子路径对称，测试面回到"paths 指向 src"约定；
  2. 或按常规流程 `pnpm run build` 重建 lib 使 exports 落点存在。

### 登记 #2（已知登记项，确认复现）：devframe-profile loader-composition.spec.ts 红

- `packages/experimental/devframe-profile/tests/loader-composition.spec.ts`：1 suite 失败、0 test、exit 1；错误与登记 #1 逐字一致（同一 `consumer.ts:22`，经 devframe-profile 组合链导入 agent-dispatch）。
- 按既定约定登记为 not-run/known-defect（预存在红），不计为 merge 回归，不掩盖。

### 登记 #3（已知登记项，确认现状）：devframe source-fingerprint POSIX 用例平台跳过

- `packages/experimental/devframe/tests/source-fingerprint.spec.ts`：41 passed | 1 skipped (42)，exit 0；1 skip 为 POSIX 平台用例（本机 Windows）。

## 补充证据

- `packages/experimental/devframe/tests/loader-composition.spec.ts` 单跑：3 passed，exit 0 —— devframe 自身 loader 组合不引用 agent-dispatch consumer，不受登记 #1 影响。
- 除上表阶梯与两条已知登记项外，未发现新的行为性失败。

## 结论

- merge commit `3db114fcde` 在受影响阶梯上**未引入新的行为性回归**：5 阶梯中 4 阶梯全绿（23 文件 / 275 测试 / exit 0）。
- 唯一红面（agent-dispatch 4 spec + devframe-profile 1 spec，共 5 个 suite）为**导入期包解析失败**，与既有 known-defect 同族、同根因、同一 `file:line`（`agent-dispatch/src/consumer.ts:22`）；只读证据表明源面在基线与 HEAD 等同，红为预存在/环境类，非 merge 引入。
- 过程中发现一处真实接线缺口（`tsconfig.base.json` 缺 `request-budget-consumer` 子路径 src 映射，见登记 #1），已登记，未修源。
