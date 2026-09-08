# V1.4 → V1.5 总控交接文档

作者：V1.4 唯一总控（session-c1668d60，DSH Harness / deepseek-v4.1-flash-expires-on-0910）
交接时刻 main tip：**c096bdf698**（V1.4 最后一次本人合并为 `751ca8db56`，其后由 Codex 根任务 V1.2 继续整合）
本文档只描述**实测状态**；凡与现场不符，以现场 git / 进程 / 文件为准，本文不构成权威。

---

## 0. 一句话交接

产品面已完成 **17 笔本人合并 + Codex 后续整合**，覆盖 worktree 提交、停止链、结算唤醒、并行非 ff 集成、完成门契约、资源释放测试、SDK 回放与冷恢复；**未完成的是候选真实全链的集成回执侧、必需 keyless 快照债务、ea42 host 面提交、project_evidence 工具源落地**。V1.4 的开发写入与 main 合并权已在三作者停写确认后移交 Codex 根任务 V1.2；V1.5 接手时须先与 V1.2 对表，再决定是否并行或完全接管。

---

## 1. 事实状态

### 1.1 main 权威链（近期，自下而上）

| SHA | 内容 | 审查绑定 |
|---|---|---|
| `c096bdf698` | merge：双客户端 SDK durable resume 验证 | Codex 侧 |
| `37a037dd18` | test(sdk)：跨双客户端验证 durable goal resume | Codex 侧 |
| `f1aee7f923` | merge：停止与 durable resume 生命周期 | Codex 侧 |
| `eb1cb0e227` | fix(devframe)：仅在 durable 绑定与资源准入后 resume | Codex 侧 |
| `3179b215be` | merge：recovery 候选与已接受 dispatch/SDK 对齐 | Codex 侧 |
| `95bc403943` | merge：已验证的 SDK 结算 followup 场景 | Codex 侧 |
| `41d4e696fe` | test(agent-dispatch)：经 SDK 回放结算与 followup | Codex 侧 |
| `34c6ed3aaf` | merge：对持久压缩历史验证冷 followup | Codex 侧 |
| `833a99897d` | test(agent-dispatch)：从压缩会话恢复冷 followup | Codex 侧 |
| `751ca8db56` | merge：冷保留 child 恢复入口（**V1.4 末笔**） | c9 五面 PASS |
| `1ccd553a03` | merge：无指令 followup 拒绝 + Note 措辞 | c9 PASS |
| `ead1553107` | merge：R3 落地 + observe 钉头 + G1 widening | c9 PASS |
| `0a2a07ca34` | merge：stop-host 三缺口修复 | 009 五面 PASS |
| `511cef02c0` | merge：allowlist 补 project_evidence | 机械核 |
| `863f228fbb` | merge：完成门生产入口面 | 009 PASS（含补交重绑） |
| `3ad7c26265` | merge：Goal 完成契约（最终合并树证据） | 009 七面 PASS |
| `74b52be6b5` | merge：README 结构修 | 门态核 |
| `2c71d9d7bd` | merge：stop host 接线 | 009 六面 PASS |
| `3619b022c2` | merge：settlement dispose 修复 + devframe 机械修 | c9 PASS |
| `d8c8054a68` | merge：config-scope + 准入竞态 | 009 PASS |
| `b4b391ce74` | merge：非 ff 并行集成（schema v4） | 009 八面 PASS |
| `258941b2a3` | merge：worker-thread 退出测试 | 009 PASS |
| `fa8b96607a` | merge：settlement 唤醒切片 | c9 PASS |
| `88b8e71096` | merge：stop adapter 全量（前段） | 009 两轮 PASS |
| `f81a5cd9f6` / `8058a8822c`+`eea40debb5` | WorktreeRegistry.commit Service / project_commit Consumer | c9 审查在案 |

### 1.2 四工作区状态（实测）

| 树 | 归属（历史） | HEAD | 脏面 | 说明 |
|---|---|---|---|---|
| `D:/dsh-devframe-v14-llmargs-lead` | A2（h1） | `41d4e696fe` | 1 M + 207 untracked | 未跟踪多为诊断残留/场景件；SDK 场景由 Codex 冻结并验证 |
| `D:/dsh-devframe-v14-udeliver-lead` | B（h2） | `37a037dd18` | 0 M + 1 untracked | 工作树净；`c8a7591f8d`（G1 补笔）已由 Codex 入 main |
| `D:/dsh-devframe-v14-resrel-lead` | ea42（h2） | `eabe1655e3` | **21 M + 5 untracked** | Codex `owned_stop_feed` 冻结 21 文件 + ea42 host 面（acquireWriter/挂载/3 测试）+ note 三件套 + 临时 overlay tsconfig，**均未提交、原位保留** |
| `D:/dsh-devframe-codex-b1` | V1.2 根任务 | `6eaea29c1d` | 0 M + 1 untracked | 未跟踪=project_evidence 工具源（`fad8ed8a…`，c9 源码 PASS）；**尚未入 main** |

主树 `D:/dsh-devframe` 工作区另有长期脏面（`AGENTS.md`、两 skill 集、`docs/env.*`、handoff 文档、`consumer-draft/` 验证资产、`proposed` Note 三件）——**历史遗留，勿清理勿回滚**。

### 1.3 已合能力（分组）

- **提交/交付域**：WorktreeRegistry.commit Service（受控 host commit）、project_commit Consumer（commitPathsByTask 唯一授权事实源、owner HEAD 观察、clean=false 语义）。
- **停止链**：整树停止（root+真实后代 drain/flush）、quiescence 持久前置、双重入恢复、缺身份诚实拒绝；host 接线（cwd 身份→lineage 树面）；writer 释放 stopped⇔release 实际完成（timeout/operation_failed→needs_attention+writer 保留）；inventory 不可证明即具名拒绝。
- **结算/唤醒**：child-settlement watch（durable 门+typed source 四元组+WeakMap claim+宿主隔离+冷恢复重挂+flush 窗口复查）；通知一律 followup（消除 steer 搁浅死锁）；dispose 窗口修复（active 门+借用 logger+归属 catch+claim 释放）；无指令 followup fail-loud；冷保留 child 经 recovery 车道恢复（同 identity/worktree、恢复零投递）。
- **并行集成**：integration 域版本 v4（mode+appliedHead）、恢复两阶段（prepared 两父观察 / applied 精确相等）、octopus 拒、merge 配置三层隔离（配置束+全局/系统剥离+local driver/filter 前置拒）、并行 spec（同 Goal 双 taskId、一次写入证据、冷恢复保真）。
- **完成门**：Goal 完成须经最终合并树证据（每任务 applied 回执+whole-Goal 验证/审查+审查者独立）+指纹重锚不改写绑定+脱钩搭车拒；生产入口面（gate 介入 fail-closed/普通通道保真）。
- **资源释放**：worker-thread 真实 exit 事件测试（预注册监听+dispose 后立即断言、grace 唯一路径+时间戳钉准时）。
- **SDK/回放**（Codex 收口）：双客户端 durable resume、压缩历史冷 followup、结算 followup 场景 keyless 回放。

### 1.4 未合/未提交面（**Codex 收口清单**）

1. **ea42 树 21 M + 5 untracked**：owned 生命周期+host 面（`createHostWriterAcquire`、`resolveHostStopAdapters` 挂载、3 测试）+note 三件套+临时 overlay tsconfig。其 G1 红线已被 `c8a7591f8d`（已在 main）解除。
2. **project_evidence 工具源**（`codex-b1` 未跟踪，`fad8ed8a…`）：project-controller `delivery-consumer.ts` 只读证据面+findings array/object schema+decision enum——c9 逻辑面 PASS，未提交未激活。
3. **A2 树残留**：Note SDK 段脏态、快照场景件、`docs/tool-catalog.md`、`sdk.snapshot.ts`（Codex 冻结 blob）、诊断残留（清理决策归 Codex）。
4. **B 树 1 untracked**。
5. **required keyless 快照债务**：完成门/findings schema 等 model-visible 面按 `docs/testing.md` 需同批场景（部分已由 Codex SDK 场景覆盖，须逐面核对）。
6. **`docs/tool-catalog.md` 重生成**（滞后于 consumer/DISPATCH_DESCRIPTION 变更）。
7. **pairing 存量失配 2 处**：`docs/tool-catalog`、`llm/plugin-package-inventory-deepseek` README 对（`6eaea29c1d` 链引入）。

---

## 2. 运行与协作机制（V1.5 必须继承）

### 2.1 角色与所有权

- **总控**：跨线优先级、派工、负责人协调、唯一 main 合并（no-ff）、显式文件提交、WORKLIST 维护。
- **实现组长**（各自独占 checkout，一目录一写者）：A2=agent-dispatch 域；B=project-controller/cgb composition/manifests/Goal 面；ea42=停止/资源/ACP/terminal 域；d3b（早期）=B6 验收/资源审计/stop 首版。
- **独立审查者**（与实现者不同会话；可用同模型）：c9（h1）、00904cb5（h2）。审查只核改动与实际反例，绑定实读字节 SHA256。
- **Codex 根任务 V1.2**：当前 main 整合/共享 build/3080/候选/证据工具唯一负责人。

### 2.2 账号与模型路由

- 两火山账号显式分流：**huoshan-1**（h1：A2、c9）、**huoshan-2**（h2：B、ea42、00904cb5）。
- Worker 模型 **glm-5.3-flash**（用户显式选择）；GPT 订阅仅可选。
- 429/限流：沿既定退避减并发，保留单实质 Worker+有界冷却；不为刷负载重复既绿检查。

### 2.3 审查与合并流程

1. 实现方冻结切片 → 报 **commit + 文件 + 精确测试 + 未完边界**。
2. 审查者做**增量**审查（绑定 SHA256/实读字节），出 PASS/FAIL 或问题清单。
3. PASS → 总控 **no-ff 合并 + 全 hooks**；FAIL → 退回实现方，修复到位后仅重绑/复核对应用。
4. 合并后只做**受影响面**复验（如 `tsc -b <包>`、focused vitest）。
5. 新文件必须 `git add` 进切片；提交后核 **diff stat ↔ 交付描述**（B 曾因 `git add` 不存在路径被 `2>$null` 吞掉而漏交 2 个实体文件）。

### 2.4 证据与验证纪律

- 绑定以 **raw SHA256** 为主键（`Get-FileHash`）；git blob oid（SHA1）仅辅助；**mtime 不得替代内容一致证据**。
- 时间窗口**不是**产品保证（后台 child 可先于 jobId 回执启动）；核销按**事件身份 join**（childId+runId/seq ↔ agent-end 映射）。
- 同源版本已过测试**不重跑**；修 1 个失败只跑该例与真受影响邻例。
- 同一确定性结构错误在同一验收轮**重复两次即冻结失败并定位**。
- 模型轮证据冻结后**零模型重跑**；失败轮如实保留，不复用为成功证据。
- 四态分离：实现 / 验证 / 独立审查 / 激活——不得混称；未验证项诚实保留。

### 2.5 失败与恢复协议

- 网络中断：先核未确认工具结果与落盘 diff，再**显式恢复原任务**，不新建重复写者。
- 机器重启：**先核最后工具实际落盘**，禁盲重放中断操作；旧 PID/运行态不代表作业仍活。
- 环境 PATH 丢失（WMI detached 启动不继承）：prepend 四目录（见 3.1），不遍历磁盘找工具、不安装。

### 2.6 记录

- `WORKLIST.md`（本目录）为唯一剩余清单，按四态记变更；**不整表重写**。
- 本文档与 WORKLIST 均属 V1.4 遗留文档域；V1.5 可续写但勿删。

---

## 3. 环境处方（可直接复用）

### 3.1 git / PATH / 依赖

```
$deps = 'C:\Users\25313\.cache\codex-runtimes\codex-primary-runtime\dependencies'
prepend: $deps\native\git\cmd ; $deps\node\bin ; $deps\bin\fallback ; $deps\native\powershell
$env:pnpm_config_verify_deps_before_run = 'error'   # 防隐式 install
```

- pnpm 默认可能隐式安装——**始终设上面这个变量**；B 曾因 `pnpm exec` 意外完成未授权 install（已披露，勿重犯）。
- 模型/包管理调用优先直调 `node_modules` 内二进制（vitest/tsc/tsx）。

### 3.2 bash shim（提交走全 hooks，不用 --no-verify）

runtime 无 POSIX shell 时，用硬链接法（目标必须是 `sh.exe`——它本身就是 GNU bash）：

```powershell
$sh = "$deps\native\git\usr\bin\sh.exe"          # 先 Test-Path
$tmp = Join-Path $env:TEMP ("dsh-bash-shim-" + [guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $tmp | Out-Null
New-Item -ItemType HardLink -Path (Join-Path $tmp 'bash.exe') -Target $sh | Out-Null
$env:PATH = "$tmp;$deps\native\git\cmd;$deps\native\git\usr\bin;$deps\node\bin;$deps\bin\fallback;$env:PATH"
```

- 合并侧以该环境执行，可让 `vendor manifest guard`/lint/whitespace 真实运行；实现方 `--no-verify` 提交必须**披露**，合并侧补齐 hooks。
- `git diff --cached --check`（**不是** `--check=0`，后者 git 不识别）。

### 3.3 dsh headless 源启动处方

```
$env:TSX_TSCONFIG_PATH = 'D:/dsh-devframe/tsconfig.base.json'   # 缺 paths → cordis 解析旧 lib 面
node --import file:///D:/dsh-devframe/node_modules/.pnpm/tsx@4.22.4/node_modules/tsx/dist/esm/index.mjs \
     D:/dsh-devframe/apps/cli/src/bin.ts --profile headless [--patch <overlay>] $task
exit $launchExit        # 包装脚本必须透传 exit code，否则 exit 0 误导
```

- 候选 overlay 用 `--patch` 调用级挂载，**不改 base bundle**（共享 manifest 唯一写者串行）。
- `tool-workflow`/`tool-jobs` 在 base bundle 可用，免 build。
- workdir 不存在 → spawn 报 `ENOENT`（**不是** pwsh 损坏）：先从存在的 cwd 创建目录再以该 workdir 启动。

### 3.4 worktree 与 node_modules

- `git worktree add -b <branch> <path> <base>` + 根 `node_modules` junction（`mklink /J`，只读使用、gitignored）。
- 包级依赖在 isolated 模式下可能缺失 → 按需补**包级 junction** 指向主树（勿 install）。

### 3.5 构建与内存纪律

- 主机 32GB、可用常约 7GB：**避免并行重型测试**；共享构建只有总控/根任务。
- `tsc -b` 大闭包会在缺 `outDir` 约束的包 `src/` 内 emit 产物垃圾（曾产生 304 个文件）——用**窄 overlay 或 `-p`**，事后 `git status` 核对。
- 仓库既有现象：`vendor/loader` 被 `paths` 源直拉，任何 import 它的 tests 程序都会以宿主 strict 配置编译 loader src 报 5 错（两树同有，编排现象非缺陷）。

---

## 4. 硬约束与禁项

- **禁** push / PR / 发布 / 删除用户文件；凭据不输出不提交不复制（`apiKeyEnv` 只写名）。
- 3080 承载进程归 V1.2；**未明确交接前不改写权归属**；不重启 3080（激活需受控重启决策）。
- 候选：`live-fullchain-1788825148717` 本轮 10 分钟上限终态失败（95/96 请求、0 integration）——**不重启、不重置预算**；候选 home/预算/端口禁触。
- `candidate-b6` 原 session 证据有效，**错误 base cwd 搜索失败不触发模型整批重跑**。
- 不隐式 install、不动他人树、不 clean/回滚既有脏面、不串行化兄弟分支、不改验收目标做绿、不吞失败。
- 一个目录一个写者；主树唯一合入；共享 manifest/profile 唯一写入者串行。

---

## 5. 未竟清单（按线）

| 线 | 未竟项 | 归属 |
|---|---|---|
| 停止/资源 | ea42 host 面+note 提交；真实 owned-process feed（切片 S+C：shell 镜像对+subagent-acp，设计要点已定）；交付二真实 profile 活动子孙停止/冷恢复验收 | Codex/V1.5 |
| 完成门 | project_evidence 工具源落地+激活；候选真实链同 Goal 续跑（待集成回执侧） | Codex |
| 集成 | `task-a has no applied integration receipt` 侧推进（搁浅机制已由 `751ca8db56` 解除） | Codex |
| 快照/文档 | required keyless 快照逐面核对；`tool-catalog` 重生成；pairing 存量 2 处 | Codex/V1.5 |
| 观察项 | host-stop 单例 5s testTimeout（并行负载）、`stopResumeResources` public 收紧、`parentAlreadyNoticed` O(n) 扫描 | 低优先 |
| 记录 | WORKLIST 后续行更新 | V1.5 |

---

## 6. V1.5 接手核对清单

1. `git -C D:/dsh-devframe log -1` 与本文 1.1 对表；认领 Codex 在 `751ca8db56` 之后的新提交。
2. 读 `WORKLIST.md` + 本文档；读 c9/009 审查结论存档（对话记录/回执文件）。
3. 逐树 `git status`/`log -1` 核对 1.2 表；**勿 clean/rebase/覆盖**任何脏面。
4. 与 V1.2 根任务对表：整合队列（ea42 host 面、project_evidence 源、快照批、catalog）。
5. 账号健康检查：huoshan-1/2 限流状态，按健康度决定并发（起步每账号 ≤2 实质 Worker）。
6. 确认边界：3080、候选 home/预算、凭据 store、发布门禁均未变。
7. 新建 V1.5 会话与 goal；V1.4 goal 归 V1.4（保持暂停，勿恢复）。
8. 继承纪律：单写者、审查者与实现者分离、SHA256 绑定、bash shim 全 hooks、`verify_deps_before_run=error`。
9. 未竟清单逐项四态登记（源码/验证/独立审查/生产验收），只记变更。
10. 首轮只做核对与对表，不并发写入；有明确验收的独立任务才派。

---

## 7. 关键教训（防复发）

1. **bash shim 目标**是 `sh.exe`（GNU bash 5.2.37 msys），链接名才叫 `bash.exe`。
2. 包装启动脚本**必须 `exit $launchExit`**，否则 exit 0 掩盖真实失败。
3. `TSX_TSCONFIG_PATH` 缺失 → cordis 解析旧 lib 面（`FiberState` 缺失类症状）。
4. workdir 不存在 → spawn `ENOENT`；不是 pwsh 损坏。
5. **PowerShell 引号 ParserError 会静默不执行**（A2 末笔因此未改文件）——复杂替换写成脚本文件再执行。
6. `git add` 不存在路径 + `2>$null` → **静默漏文件**；提交后核 diff stat 与交付描述（B 教训）。
7. `--no-verify` 必须披露；合并侧用 bash shim 补 hooks。
8. 大闭包 `tsc -b` 会产生 emit 垃圾（304 文件事件）；窄 overlay/`-p`。
9. fake 引擎 disposal 计数 ≠ OS 资源释放；日志无后续事件 ≠ 已释放（process 级释放不在日志证明范围，如实列档）。
10. 时间窗口不是身份；按事件身份 join。
11. 未授权 install 一旦发生要**立即披露并停止**（B 的 `pnpm exec` 事件）。
12. 只报新交付/新根因/需 root 动作项；不重复“终态确认/待命”状态，避免状态轰炸。

---

## 8. 证据索引

- **工作清单**：`.agents/devframe/v14/remaining/WORKLIST.md`
- **B6 验收与资源审计**：`.agents/devframe/v14/remaining/consumer-draft/`（verifier×2、plan、资源释放审计与实验日志）
- **V1.2 根任务证据空间**：`D:/dsh-devframe-codex-b1-receipts/`（候选 runs/回执、`review-schema-failure.json`、`stop-release-gap.json`、`git-config-scope-proof.json`、`merge-admission-gap.json`、`merge-admission-order-comparison.json`、`recovery-runner-review-freeze.json`、运行器与证据工具）
- **候选**：`live-fullchain-1788825148717`（95/96 终态）、`live-fullchain-1788822569542`（prepared）
- **审查存档**：c9 十轮 / 00904cb5 七轮 PASS 结论（绑定各自 SHA，见对话记录）
- **Agent Note**：`.agents/notes/implemented/architecture/` 下 `2026-09-08-*` 系列（settlement-wake、controller-parallel-branch-merge、goal-completion-final-merge-contract、command-goal-binding-host-stop-adapters）

---

*本文档由 V1.4 总控在写权移交后一次性出具；后续状态以现场为准。*
