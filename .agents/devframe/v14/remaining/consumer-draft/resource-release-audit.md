# B6 资源释放证据审计（有界独立 · 只读 + 既有聚焦检查 + consumer-draft 实验）

对象 = `workflow-worker-thread.spec.ts` + `source-worker.compat.spec.ts` + `tool-workflow.spec.ts` + 引擎源 `src/host.ts`。结论绑定 HEAD 源码；产物仅本目录。

## 一、既有真实证据面（日志之外）

**真实（非 mock）且已测**：

1. **worker-death 组（workflow-worker-thread.spec.ts :1164-1433）— 真实线程死亡→宿主侧清点**。六个用例以 `worker.terminate()`（Node 真实终止）或 worker 内真实 uncaught exception 杀线程；断言面 = 引擎 exit 观察器产出的错误结果文本 `'exit code 1'`（该文本只能来自真实 Worker `exit` 事件负载）+ host 侧 registry reap（StubProvider `disposed`/`disposeCalls` 计数）。代表例 :1199（startup 未就绪时真杀线程→'workflow worker gone' abort+迟到 ready 的拒绝处置）、:1262（exit 先于 settle→error+reap，含 dispose-reject 容器）、:1318（worker 内 uncaught→reap stray child）。
2. **grace 终止路径（:1006-1036）**：cancel→grace→引擎**自己** terminate；断言先于 `handle.dispose()`（:1030-1032 注释明示"host-owned worker exit, not consumer courtesy"）——exit 驱动的 reap 在 ~1s 有界窗内完成 = 真实死亡事件的间接计时证明。
3. **dispose() 静默保证（:1038-1071）**："dispose() resolving IS the quiescence claim"——返回时子处置已完成而非在途（:1064-1068），且 grace 有界（:1063 <1200ms）。
4. **实现契约（src/host.ts）**：`dispose()` 无条件 **`await this.worker.terminate()`**（:243，"the thread never outlives its run"）——正常路径线程终止被**等待**；grace 路径 `void this.worker.terminate()`（:199，随后续 dispose 再 await 兜底）；grace timer unref（:202）；死亡屏障 onMessage（:267-272）。

**mock/仅计数（不得当 OS 释放）**：

- `tool-workflow.spec.ts` :29-55/:135-152 的 `engine.disposed` 计数 = **fake 引擎**宿主插件级 disposal 传播，仅证明"插件 fiber 卸载会 dispose 引擎服务"，不触及 worker/线程/OS。
- 各 stub provider 的 `disposed/disposeCalls` 计数 = host 侧子注册表清点，非线程证据（本审计仅将其用作"host 已清点"的面）。

**间接（真实 worker 但无退出断言）**：`source-worker.compat.spec.ts` — 源模式真 worker 跑通+dispose 链，未断言任何退出面。

## 二、新实验证据（consumer-draft，本审计新增）

`resource-audit-worker-exit.ts`（exit 0；日志 `resource-audit-exit-evidence.log`）：正常完成路径（`return 6*7`）在 `dispose()` 解析后**直接观察到真实 Worker `exit` 事件**（exit code 1，Node worker_threads 终止语义），时间线 result→dispose→exit 毫秒级同窗。**这是现有测试从未断言的面**（现有用例只在 death/grace 路径间接触达 exit）。
`resource-audit-vitest-reaps.log`：聚焦 'reaps' 四用例全绿（4 passed/50 skipped，3.74s），含两例真实 terminate→exit→reap。

## 三、缺口（精确到实现/断言）

1. **正常路径 exit 断言缺失**：无任何测试在"result completed→dispose"后断言 Worker `exit` 事件/terminate 完成。补法一行面：测试内 `worker.once('exit')` + dispose 后有界断言（实验已证今日成立，属防回归钉）。归属：`packages/workflow/workflow-worker-thread/tests/workflow-worker-thread.spec.ts`（待总控裁定后实施）。
2. **OS 层线程可观察性无断言**：`process.getActiveResourcesInfo()` 在本 Node（24.19）对 worker 线程**无 'Worker' 标签**（实验 before=0/after=0），不能作断言面；in-process 最强可观察 = `exit` 事件 + `terminate()` promise（dispose 已 await）。更强 OS 证明需 procfs/外部观察，现无任何测试涉及。
3. **grace 路径 terminate 未 await（host.ts:199 `void`）**：靠 :1006 的 1s 有界 reap 间接证 exit 已发；可直接断言 terminate 完成时序（同归属待裁）。
4. **exit 语义未钉**：'exit code 1' 文本被断言，但退出码语义（1 vs 0）与 exit/terminate 事件次序仅在合成 emit 屏障测试（:1165）覆盖，真实线程次序无钉。

## 四、OS 释放的证明边界（如实列档）

in-process 的线程释放证明上界 = `exit` 事件 + `await terminate()`（两者已在正常路径实现中被等待、实验中被观察）；**进程外资源（OS 调度面、句柄表）超出本仓测试可断言范围**，需外部观察器，当前为零覆盖——不将 mock dispose 计数、不含 'Worker' 标签的资源快照当作 OS 释放。
