# B6 background-workflow 四步验收方案（真实候选 · 供总控直接执行 · v2 收紧版）

状态：**待执行**。对象 = 当前 main（workflow 栈已内置于 base bundle：`packages/bundle/base/cordis.patch.yml` :261 tool-jobs / :375 workflow-worker-thread / :380 tool-workflow）。无共享 build、无 3080 触碰、协议不读不打印任何凭据。

## ① 启动（隔离 home + headless profile，无端口面）

```powershell
$home_ = 'D:\b6-acceptance-home'            # 全新空目录，本次验收专用
New-Item -ItemType Directory -Force $home_ | Out-Null
# 空家不继承路由：把已授权 home 的 settings 复制/改写入 $home_，其 provider 条目
# 以 apiKeyEnv 引用环境变量名（如 apiKeyEnv: DEEPSEEK_API_KEY——只含名字，不含
# 密钥值；若现条目含内联密钥则先改为 apiKeyEnv 引用再复制），并在你侧导出该环境
# 变量。协议与核查脚本全程不读取、不打印凭据值。
# 显式 provider：父回合与 workflow 子代理走同一显式授权路由条目（huoshan）；
# 路由面不以配置宣称为准，以日志为准（见③核查脚本打印 header.config）。
Copy-Item '<你已授权home>\settings.yaml' "$home_\settings.yaml"
$env:DSH_HOME = $home_
$env:pnpm_config_verify_deps_before_run = 'error'   # 不隐式 install
pnpm dsh --profile headless "<TASK>"                  # 见②；首次运行按随附模板初始化 profile
```

`pnpm dsh` 源启动（tsx/esm）无需 build；tool-workflow 已在 base bundle `cordis.patch.yml` :380。

路由就绪的证明不在配置宣称，而在日志：核查脚本会从最新 `request/header` 的 `header.config` 打印实际使用的 `provider/model`——只有它与你的 huoshan 授权条目一致才算路由面通过。

## ② 任务文本（顶层 workflow 输入；子任务设计为真实有界较长，避免与父回合竞争）

```
Background workflow acceptance. Perform exactly these steps in order:
1) Call the workflow tool with run_in_background set to true, meta
   {"name":"b6-acceptance","description":"Background acceptance workflow"},
   and this exact script:
   const line = await agent('Call the glob tool for pattern "docs/*.md", then read the first file you found, then reply with exactly: acceptance-child-line')
   return { child: line }
2) While that job runs, call job_list once and report the job's id and status.
3) Then call job_output for that job with wait set to true, and report the
   child line verbatim from the result.
4) Then start a second background workflow the same way with meta name
   "b6-acceptance-kill" and this exact script:
   const line = await agent('You are the b6-kill-child-marker. Call the glob tool for pattern "packages/**/*.json", then read the first file you found, then reply with exactly: kill-me-line')
   return { child: line }
   Confirm with job_list that it still shows running, then cancel it with
   job_kill, then call job_output with wait set to true to confirm it reports
   killed.
Report what each step returned.
```

两个子任务各含两次真实工具往返（glob+read，真实 provider 回合），有界且明显长于父回合的 job_list 读取；若子任务实际提前完成导致 job_list 已非 running，**验收按实报失败重跑，不放宽断言**。

## ③ 证据核销（真实 session 日志，机器可查）

```powershell
# 显式 parent session 身份必填——禁止"最新文件"选择（真实并行下子日志常更新）。
node --import tsx/esm .agents/devframe/v14/remaining/consumer-draft/b6-acceptance-log-check.ts $home_ <parentSessionId>
```

只读解析隔离 home 下 `session.jsonl` / `session.jsonl.zstd`（zstd 走仓库 `scanZstdFrames`+`createZstdFrameDecoder` 逐完整帧解码后 `scanLog`，已用真实 main parent zstd 日志烟测通过），断言（各步给出 `seq`/`time` 证据，失败退出码 1）：

- **a)** 最新 `request/header`：`header.tools[]` 含 `workflow`（`parameters.properties.run_in_background.type==='boolean'`，顶层）与 `job_output`/`job_list`/`job_kill`；**并打印 `header.config.provider/model`** 作为实际路由证据。
- **b)** `tool/call` workflow（`run_in_background===true`）按 `toolCallId` 配对 result，文本含 `started background workflow job <id>`。
- **c) 硬证据（不允许仅"中间事件存在"）**：同 jobId 的 **job_list 配对 result 文本含 `<jobId> [workflow] running`**——父回合的中间读取亲证作业处于 running；且 start result 与终态 job_output result 之间事件 time 单调、终态文本含 `[status: completed]` 与 `acceptance-child-line`。
- **d) 真实运行后取消**：kill 作业存在**先于 job_kill 的** job_list 配对 result 含 `<killJobId> [workflow] running`（取消时确在运行）；job_kill result 含 `cancellation-requested`；其后 job_output 文本 `[status: killed]`。**cleanup 双面**：完成子代理的 session 日志含其完成行（正向对照）；被取消子代理的 session 日志（含 `b6-kill-child-marker` 标记）存在且有活动、但**不含** `kill-me-line` 完成行（真实中途取消，未跑完即清理）。

## 成功标准与失败分诊

- 四步全 PASS = 验收通过；`[c]/[d]` 若因子任务真实提前完成而未见 running，按实报失败重跑（诚实失败，不放宽）。
- 分诊：日志为空 → 核对 `$home_\profiles\headless\sessions`；路由不符 → 核对复制进的 settings 与 huoshan 条目；步骤 4 被模型省略 → 原样重跑。

## 边界

- 启动独立候选在授权内；共享 build/profile 仍总控单写；`pnpm` 一律带 `pnpm_config_verify_deps_before_run=error`，不隐式 install。
- 同目录 `b6-background-workflow-acceptance.ts` 仅为 in-process 组件辅助检查（头部已标注非 B6 证据）。
