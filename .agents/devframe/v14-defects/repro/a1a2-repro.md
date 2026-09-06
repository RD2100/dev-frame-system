# A1/A2 复现与修复报告：both-mode-turn / ptc-turn 快照红

状态：已修复（本树实测两场景 exit 0）。全部证据为本线组长在本树（D:\dsh-devframe-v14-defects-lead @ codex/v14-defects-lead）第一手运行所得。

## 复现

- 树状态：干净 @ 6b31951491，`pnpm install`（repro/install-receipt.txt，exit 0）+ `pnpm run build`（exit 0，含 lib/worker.cjs 构建产物）。
- `pnpm run test:snapshot -t both-mode-turn` → **exit 1**（repro/a1-both-mode-turn.vitest-output.txt）。
- `pnpm run test:snapshot -t ptc-turn` → **exit 1**（repro/a2-ptc-turn.vitest-output.txt）。
- 断言位置：`packages/test-support/session-snapshot/src/suite.ts:1527-1530`（actual 与 expected 双方各过 `normalizeSessionSnapshots` 后 `toEqual`；源栈映射显示为 snapshots/session/headless.snapshot.ts:828）。

## 差异全貌（两场景同构，均只有一行 tool/result 文本差异）

期望（录制侧，快照 fixtures `session.win32.jsonl:24`，both-mode-turn 与 ptc-turn 同）：

```text
Error: code run failed (exception): TypeError: tools.bash is not a function
    at eval (eval at runWorkerMain (D:\dsh-devframe-p-battery\packages\code-runtime\code-runtime-worker-thread\lib\worker.cjs:887:31), <anonymous>:4:28)
    at runWorkerMain (D:\dsh-devframe-p-battery\packages\code-runtime\code-runtime-worker-thread\lib\worker.cjs:887:172)
    at Object.<anonymous> (D:\dsh-devframe-p-battery\packages\code-runtime\code-runtime-worker-thread\lib\worker.cjs:905:1)
    at Module._compile (node:internal/modules/cjs/loader:1872:14)
    ...（CJS loader 内部帧 + worker_thread MessagePort）
```

实际（本树回放，source 模式）：

```text
Error: code run failed (exception): TypeError: tools.bash is not a function
    at eval (eval at runWorkerMain (file:///D:/dsh-devframe-v14-defects-lead/packages/code-runtime/code-runtime-worker-thread/src/bootstrap.ts:406:16), <anonymous>:4:28)
    at runWorkerMain (file:///D:/dsh-devframe-v14-defects-lead/packages/code-runtime/code-runtime-worker-thread/src/bootstrap.ts:412:25)
    at file:///D:/dsh-devframe-v14-defects-lead/packages/code-runtime/code-runtime-worker-thread/src/worker.ts:14:6
    at ModuleJob.run (node:internal/modules/esm/module_job:439:25)
    ...（ESM loader 内部帧）
```

## 归因（比"树根路径"更进一步）

1. 路径嵌入：录制树根 `D:\dsh-devframe-p-battery` vs 回放树根——机器特定值，与 cwd 同类。
2. **模块格式缝（关键）**：录制侧运行的是**构建产物 CJS worker**（`lib/worker.cjs`，经 runWorkerMain + cjs/loader 帧集合）；回放侧运行的是**源码 ESM worker**（`src/worker.ts` → `src/bootstrap.ts`，经 tsx/ESM 帧集合）。两侧的 node 内部帧集合完全不同（cjs/loader vs module_job/esm loader）。
   → 因此单纯"树根归一"不可能收敛：即使路径归一，帧文本仍按模块格式分叉。栈区域整体是录制环境属性（构建面 × 树根 × Node 内部行号），与 win32 平台缝同类。
3. 被测语义（保持 pinned，不受影响）：exception kind 与 message（`TypeError: tools.bash is not a function`）、错误封装（`CodeRunFailedError` / `CODE_RUN_FAILED`）、tool-call 关联（callId）、`<anonymous>:4:28` 脚本内位置、step 2 模型反应、`sourceEventSeqs`。
4. 错误文本产生面：`packages/core/tools/src/ptc.ts:638`（`throw new CodeRunFailedError(\`code run failed (${result.error.kind}): ${result.error.message}...\`)`）；栈随 worker 异常 message 进入 tool/result 文本并持久化进 session log。

## 修复（选方向 ①，理由如下）

在归一化面 `packages/test-support/session-snapshot/src/normalize.ts` 新增一条窄域规则：

- 常量 `CODE_RUN_FAILURE_STACK_RE` + token `{{workerErrorStack}}`（normalize.ts:56-58、scrubString 内 ~line 199-203）。
- 规则：文本以 `Error: code run failed (exception): <一行>` 开头且其后跟随至少一个 `    at ` 帧行时，把栈区域整体折叠为 `{{workerErrorStack}}`；后续 `Captured output:` 场景语义内容保留。
- 该规则位于共享字符串清洗路径，session log 与 stdout 两个面、actual 与 expected 两侧同时生效；幂等。

为何不选 ② refresh 配方：`DSH_SNAPSHOT=refresh -t <scenario>` 会把**本树** source 模式栈（`file:///D:/dsh-devframe-v14-defects-lead/...`）写回 fixture——机器特定性只是换了宿主，问题类不消除，跨树/跨机不收敛。归一化一次性移除整个环境属性类，base 夹具零修改。

为何不是"削弱真实断言"：断言强度不变——异常种类、消息、错误封装、callId、模型后续行为全部保留；被移除的仅是录制宿主属性（树根、构建面、Node 内部帧行号），与 FILE_POLICY_RE（normalize.ts 先例，宿主文件策略）同一归类逻辑。

## 修复后验证（真实退出码）

- `pnpm run test:snapshot -t both-mode-turn` → **exit 0**（1 passed | 115 skipped）
- `pnpm run test:snapshot -t ptc-turn` → **exit 0**（1 passed | 115 skipped）
- 聚焦单测 `vitest run packages/test-support/session-snapshot/tests/normalize.spec.ts` → exit 0，70/70（含新增 5 例：栈折叠、两侧栈同一归一面、Captured output 保留、非 code-run 错误不折叠、无栈不折叠）。
- base 夹具（snapshots/session/both-mode-turn、snapshots/session/ptc-turn）零修改；全量套件结果见结算回执。

## Worker 分派记录（本线）

- ecadc1fa / 673d61fe：request/header 实证 huoshan-1/glm-5.3-flash（总控已提取 seq 证据），但交付物为 C 线核验内容（C1/C3，落 C 线树），未产出 A1/A2 证据。
- a46cab71：两次挂死（零工具调用/响应中断），按预算终局废弃。
- 本报告全部证据由组长第一手运行产生，不依赖上述 Worker。
