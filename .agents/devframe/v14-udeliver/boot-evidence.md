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

## 链驱动集成发现（boot1-boot1d，2026-09-07）

四次真实 boot 的驱动面结论（对 shipped-profile 组合交付有普适价值）：

1. **shipped overlay 的原生宿主是 web profile**：headless 组合无 webserver 行（patch 跳过无妨）但 `tool-cordis` 依赖 bundle 层 `cordis-host-runner` 的 `dynamicCordisRunner`/`cordisInspect` 服务，headless 下 pending 超时 fail-loud（boot1 实录 stderr：`1 entry did not activate`）。
2. **web 组合在 bundle 层 disable 全部模型面工具**（web-app/cordis.patch.yml L330-439：tool-bash/pwsh/jobs/fs/str-replace-editor/subagent/workflow/ralph/skill/goal/todo/web 全 `disabled: true`），由 **agent preset 按会话重挂**（web-app L448-452 `agent-presets` 行 `default: standard`；standard=全工具）。
3. **裸 `agents.create` 绕过 preset 组装**：driver 先用 headless runner 同款 `agents.create+installModelSelection` 创建 agent，实测其工具面只有 memory/cordis（会话日志 tool/call 全集实证），模型被迫用 `cordis_define/cordis_run` 自建能力——三次 boot（boot1/1b/1c）同模式。改为 `sessionController.create({cwd, agentPreset:'standard'})`（Web 客户端同一 remote）后，boot1d 的 agent 记录 `agentPreset:"standard"`，pwsh/get_goal/todo_write 全部可用。
4. **/devframe-start 四连过**：boot1/1b/1c/1d 的 driver 证据 JSONL 均记录 `kind:"success"`，"required checks executed for real: 1, verification status: passed"（git diff --check 真实子进程）。
5. **模型行为如实记录**：glm-5.3-flash 在该组合下倾向先探索环境（cordis_inspect/memory_search）再行动；负面指令（"不要用 X 工具"）约束力弱，正面单动作指令部分有效。层级派工（总控→组长 subagent→Worker workflow）是否发生取决于模型配合，链证据如实标注实际路径。

## 结论

B1 运行态前置面收口：shipped profile（+部署 overlay）在真实 boot 中挂载 v14 四包成功，装配零重复，端口就绪。12 站真实链与 B4 按此基线执行。
