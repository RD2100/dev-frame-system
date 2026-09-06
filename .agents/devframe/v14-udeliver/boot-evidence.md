# B1 boot 证据（收口文件）

基线：本树 f104786ca3（=2380aae9a3 + main 合并，含总控修复 acb2a2956b：shipped overlay 删重复 cordis-host-runner insert）。宿主无 bash；所有命令经 pwsh 真实执行。

## 探针 1：dump-config 装配探针（2026-09-07）

命令（workdir=D:\dsh-devframe-v14-udeliver-lead，隔离 DSH_HOME=临时 probe 目录）：

```
node --import file:///D:/dsh-devframe-v14-udeliver-lead/node_modules/tsx/dist/esm/index.mjs apps/cli/src/bin.ts --profile web --patch apps/cli/config/examples/cordis/cordis.yml --dump-config
```

- 退出码：**0**
- id 行总数：**152**（`^\s*- id: ` 精确计数）
- 重复 id：**0**（Group-Object 全量查重）
- `cordis-host-runner` id 行：**1**（=web-app bundle 层唯一插入；shipped overlay 仅注释提及，无第二行）
- v14 四包行全部在列：`@deepseek-ai/dsh-experimental-session-identity` / `-shadow-router` / `-project-memory` / `-command-goal-binding`
- 原始输出：`D:\dsh-udeliver-iso\probe-*\dump.txt`（隔离目录）

## 探针 2：真实 boot 探针（2026-09-07）

命令（workdir=D:\dsh-devframe-v14-udeliver-lead，隔离 DSH_HOME=bootprobe 临时目录，--patch shipped + --patch 隔离探针 overlay[端口 3491]，--no-open）：

```
node --import file:///D:/dsh-devframe-v14-udeliver-lead/node_modules/tsx/dist/esm/index.mjs apps/cli/src/bin.ts --profile web --patch apps/cli/config/examples/cordis/cordis.yml --patch D:\dsh-udeliver-iso\probe-overlay.yml --no-open
```

- 端口 3491：**LISTENING=True（~4s 内就绪）**（Test-NetConnection 实测）
- 监听进程身份核实：PID 23180，命令行头 `"…node.exe" --import file:///D:/dsh-devframe-v14-udeliver-lead/node_modules/tsx/…`（=本探针进程，非他物占用）
- 重定向 stdout/stderr 0 字节（URL 提示行未进重定向管道——如实记录，token URL 证据面归总控探针）
- 探针进程在证据收齐后由组长 job_kill 干净收尾（记录于此，不算崩溃）
- boot 日志目录：`D:\dsh-udeliver-iso\bootprobe-20260907-075120\`（隔离）

## 附带实证（boot1c，2026-09-07 早前，修复合入前本树同内容修复）

- 端口 3490 LISTENING after ~4s；`--patch shipped --patch 部署 overlay(webserver/shadow-router.authorizedRoots/project-memory.vaultRoot+writeEnabled)` 全链激活成功
- **`!!js` 激活期插值实证**：command-goal-binding 激活期对 `checks[].cwd` 做 `isAbsolute` 校验（config.ts:113-114），插值失败即 fail-loud 拒载；boot 成功=插值到达数组内元素成立
- boot1/1b 失败根因（duplicate loader entry id: cordis-host-runner）=design.md L25-26 预告语义，总控已修（acb2a2956b）并合 main

## 结论

B1 运行态前置面收口：shipped profile（+部署 overlay）在真实 boot 中挂载 v14 四包成功，装配零重复，端口就绪。12 站真实链与 B4 按此基线执行。
