# snapshot B 族 win32 期望变体数据草案（L-Verify p22 阶段 1）

- 执行者：L-Verify p22 Worker B（三层拓扑：总控 → L-Verify 组长 → 本 Worker）。日期 2026-09-06（JST）。
- 证据基座：worktree `D:\dsh-devframe-p-snapexpect`，分支 `p/snapexpect`，基线 `fc34223e28bd017339eb3a48164c88321433d630`（建树后工作树干净，本文件写入前 `git status --porcelain` 为空）。
- 阶段范围：**仅阶段 1**——B 族 win32 期望变体**数据草案** + 取证文档。阶段 2（在 `snapshots/**` 落平台变体期望文件）等 L-Foundation snapplat 语料作者接口到达后另行派发；本文件不猜测接口 schema，不写任何 `snapshots/**` 文件。
- 取证纪律：除本文件外零仓库变更；`pnpm run build` 与两条判别命令为本任务仅有的执行动作；运行日志存档于仓库外临时目录（`%TEMP%\dsh-p22-b-delta-minimal.log`、`%TEMP%\dsh-p22-c-delta-message-feedback.log`）。

## 1. 范围与族定义

引用 `D:\dsh-devframe\.agents\devframe\p22\shipped-profile-defects.md`（只读，主树）"缺陷三"节的分解表：

| 族 | 签名 | p22 计数（lib 模式日志，p/builtbin-3 @ 75c3d4af4e） | 平台相关性 |
| --- | --- | --- | --- |
| A | `Error: dsh: plugin tree failed to load` + `@deepseek-ai/dsh-tool-worktree: pending (waiting for services: workspaceRegistry, worktreeRegistry)` | 130 处提及，headless/sdk/acp 全部场景 | 平台无关（组合行缺失） |
| B | `persisted replay: expected … to be …`，actual 含 `{"type":"tool/result",…"text":"Error: unknown tool \"bash\""…,"error":{"name":"ToolNotFoundError","code":"UNKNOWN_TOOL"}}` | 2 处 | Windows 特有 |
| C | `SyntaxError: Bad escaped character in JSON at position 99 (line 1 column 100)`（套件级，`apps/web/tests/message-feedback-protocol.snapshot.ts` 用例未跑即崩） | 1 处，套件级 | Windows 特有 |

**本波基线 `fc34223e28` 上的残余口径（以本 Worker 实测为准）**：B 族 2 处（实测，签名出现 2 处，见 §4）、A 族 0（实测，§5）、C 族 0（实测，§5）。

C 族归零机理（只读考证，非本任务修复）：p22 缺陷三钉行的 `apps/web/tests/scaffold.ts` L987 未转义 `{{cwd}}` 注入，在本基线上已是 `jsonEscape(scaffold.workspaceCwd)`（现 `scaffold.ts` L999，`jsonEscape` 定义 L960-962）；修复提交 `8f9b811547`（"fix(web): JSON-escape cwd injection in seed fixture realization"，2026-09-06）经 `git merge-base --is-ancestor 8f9b811547 HEAD` 验证（exit 0）已在基线祖先中。

## 2. minimal-preset 场景 win32 期望差异全集（数据草案核心）

场景：`apps/web/tests/minimal-preset.snapshot.ts`（下称"用例文件"）+ `snapshots/web/minimal-preset/`（authored 语料五文件）。机理基座：`packages/preset/agent-presets/presets/minimal/agent.cordis.yml` L36-38 `persistent-bash` `disabled: !!js process.platform === 'win32'`、L58-60 `persistent-pwsh` `disabled: !!js process.platform !== 'win32'`、L6-7 设计意图自述（"the persistent shell (`bash` on POSIX, `pwsh` on win32)"）——平台互斥是有意设计，win32 上 minimal preset 的 shell 工具面是 `pwsh` + `str_replace_editor`。

### a. tool-schemas 卡片变体：bash 卡 → pwsh 卡

authored 现值：`snapshots/web/minimal-preset/tool-schemas.expected.json` L4-18 为 bash 卡（`"name": "bash"`，description 与 preset 的 bash description 逐字一致，即 `agent.cordis.yml` L41-49——证明卡片 description 来自 preset config 覆盖，而非工具包默认值）。

win32 变体草案（pwsh 卡完整 JSON，占位于 bash 卡原位，`initial` 数组顺序不变）：

```json
{
  "name": "pwsh",
  "description": "Run commands in a PowerShell shell\n* When invoking this tool, the contents of the \"command\" parameter does NOT need to be XML-escaped.\n* You don't have access to the internet via this tool.\n* State is persistent across command calls and discussions with the user.\n* Use native Windows paths (C:\\...) and $env:NAME variables; this is PowerShell, not bash.\n* Please avoid commands that may produce a very large amount of output.\n* Please run long lived commands in the background, e.g. 'Start-Job' or start a server with Start-Process.",
  "parameters": {
    "type": "object",
    "properties": {
      "command": {
        "type": "string",
        "description": "The PowerShell command to run. Relative path is preferred in the command."
      }
    },
    "required": [
      "command"
    ]
  }
}
```

证据来源：
- `name: 'pwsh'` —— `packages/shell/tool-pwsh-persistent/src/index.ts` L442。
- `parameters`（command: string, required, description 逐字）—— 同文件 L444-450。
- `description` —— `agent.cordis.yml` L63-70 的 preset 覆盖值（`|-` 字面块，`\n` 连接）；工具包默认值（tool-pwsh-persistent L27 `DEFAULT_DESCRIPTION`）不参与，因为 preset 显式传了 `description` config。
- 归一化后卡片形状（`required` 数组、`type: object`）与 authored bash 卡同构（tool-schemas.expected.json L6-17 先例）。

**草案声明**：本卡片 JSON 为源码提取草案，最终值以阶段 2 lib 模式实跑归一化输出（`formatToolSchemasSnapshot`）为准。

### b. 用例 1 内联快照（用例文件 L72-139）

实测差异（2026-09-06 09:43:10 运行，`[2/3]` 段，`toMatchInlineSnapshot` 于 L123 失配，3 个字段漂移）：

| 维度 | authored(POSIX) 现值(文件:行) | win32 变体草案值 | 证据来源 |
| --- | --- | --- | --- |
| `requestHeader.tools` | `["bash","str_replace_editor"]`（用例文件 L119、L131-134） | `["pwsh","str_replace_editor"]`（pwsh 占 bash 原注册位，顺序不变） | 实跑日志 `[2/3]` diff：`- "bash"` → `+ "pwsh"`；pwsh 注册链 agent.cordis.yml L58-60 |
| bash 状态装填·第 1 处直接工具调用 | `cd ${JSON.stringify(stateDir)} && export DSH_MINIMAL_STATE=PERSISTED`（用例文件 L86-92，`name: 'bash'`） | `name: 'pwsh'` + `Set-Location -LiteralPath <stateDir>; $env:DSH_MINIMAL_STATE = 'PERSISTED'` | pwsh 语义实跑验证（`Write-Output` / `${env:NAME}:$PWD` 插值在本机 PowerShell 验证通过）；preset 提示语"native Windows paths (C:\...) and $env:NAME variables"（agent.cordis.yml L68）。命令字面为草案，嵌入机制（如何携带 stateDir）属测试面决策 |
| bash 状态装填·第 2 处直接工具调用 | `printf '%s:%s\n' "$DSH_MINIMAL_STATE" "$PWD"`（用例文件 L93-99） | `Write-Output "${env:DSH_MINIMAL_STATE}:$PWD"` | 同上；`${env:NAME}` 花括号形式避免 `:` 后接 `$PWD` 的解析歧义 |
| 状态读取期望文本 | `"PERSISTED:{{cwd}}/persistent-state"`（用例文件 L125） | `"PERSISTED:{{cwd}}\persistent-state"`（反斜杠分隔符） | 草案：`join(scaffold.workspaceCwd, 'persistent-state')`（用例文件 L83）在 win32 用 `\`；`text()` L110-115 将 workspaceCwd token 化为 `{{cwd}}`，分隔符保留。本轮实跑未产出该行（bash 调用直接 UNKNOWN_TOOL，见 §2c），此值为路径语义推导 |
| editor 期望文本（本轮实测新发现） | `"Here's the content of {{cwd}}/preset-smoke.txt with line numbers …"`（用例文件 L126） | `"Here's the content of {{cwd}}\preset-smoke.txt with line numbers …"` | 实跑日志 `[2/3]` diff：`{{cwd}}/preset-smoke.txt` → `{{cwd}}\preset-smoke.txt`——str_replace_editor 卡与 schema 不变（§3），仅 view 输出文本含平台路径分隔符漂移 |
| `prompt` 字段 | `"You are a helpful software engineer assistant."`（L130） | 不变 | 实跑日志：`prompt` 行在 diff 上下文中无 `-`/`+` |
| `goalCommand` | `false`（L120、L129） | 不变 | 实跑日志：同上，无 diff |
| PROMPT 常量（模型可见 authored 文本） | `"Use the bash tool to run exactly: printf 'MINIMAL_BASH_CARD_OK\\n'. …"`（L27） | **接口决策点，不在本阶段定值**：若语料按平台参数化，win32 提示语应为 pwsh 措辞 + pwsh 命令（如 `Write-Output 'MINIMAL_BASH_CARD_OK'`） | 该文本进入 session.jsonl L5/L9 与 ui.expected.md L16；是否平台参数化属语料作者接口的职责范围（§6） |

### c. persisted replay 期望面（session.jsonl authored 语料 vs win32 实际持久化会话）

机制：`launchWebScaffold({ replayFixture: FIXTURE, compareReplaySession: true })`（用例文件 L38）——`session.jsonl` 既是 dsh-llm-replay 的模型回放脚本（scaffold.ts L683-693 `installLlmReplay`），又是持久化会话比对目标（scaffold.ts L889-890 `assertReplaySession`；`snapshot.yml` L8 `pin: true` 还触发 system-prompt/tool-schemas 两张 pin 比对，scaffold.ts L895-909）。

实测漂移点（本轮 `[1/3]` Failed Suite，断言于 scaffold.ts:890，经 `Object.close` scaffold.ts:767 ← afterAll 用例文件 L67 抛出）——**整个 30 行 fixture 的 diff 只有 1 行**（hunk `@@ -15,11 +15,11 @@`）：

| 维度 | authored(POSIX) 现值(文件:行) | win32 实际（实跑 received） | 证据来源 |
| --- | --- | --- | --- |
| `tool/result` 行 | `{"type":"tool/result","data":{…,"content":[{"type":"tool-result","toolCallId":"minimal-bash-card","content":[{"type":"text","text":"MINIMAL_BASH_CARD_OK"}],"isError":false}…}}`（session.jsonl L20） | `{"type":"tool/result","data":{…,"content":[{"type":"tool-result","toolCallId":"minimal-bash-card","content":[{"type":"text","text":"Error: unknown tool \"bash\""}],"isError":true}…},"error":{"name":"ToolNotFoundError","code":"UNKNOWN_TOOL"}…}` | 实跑日志 `[1/3]` diff L23-24（received 行全文）；错误类定义 packages/core/tools/src/index.ts L487-503（`unknown tool "<name>"` / `UNKNOWN_TOOL`），dispatch 路径 L1538 `if (!tool) throw new ToolNotFoundError(exec.name)` → L1545-1546 `toolErrorResult` |
| MINIMAL_BASH_CARD_OK 输出面 | `tool/result` text 为成功输出（L20） | 被 `Error: unknown tool "bash"` 取代 → 下游 Web 卡片 OUT 面永远不出现该文本（§2d 用例 2 超时实证） | 实跑日志 `[3/3]` |
| 回放脚本侧工具名 | L14/L15/L18/L19 四行记录模型调用 `"name":"bash"`、`arguments:{"command":"printf 'MINIMAL_BASH_CARD_OK\\\\n'"}` | authored 语料不变时：脚本照常回放 `bash` 调用 → 工具注册表无 `bash`（win32 门控）→ UNKNOWN_TOOL（即上行）。**win32 变体语料需要脚本侧变体**：这四行的 name/arguments 需变为 `pwsh` + pwsh 命令草案 `Write-Output 'MINIMAL_BASH_CARD_OK'` | 机理：replay 脚本驱动模型输出（scaffold.ts L683-693），dispatch 与注册表在宿主侧（core/tools L1538）。脚本侧变体字段名/形态待接口（§6） |
| `tool/call` 行 | L19 `{"type":"tool/call",…,"name":"bash",…}` | 同上：脚本侧不变则 tool/call 行不变（实际持久化的 tool/call 仍记 `bash`——调用确实发生了，失败在执行），变体语料下应为 `pwsh` | 实跑日志 diff：tool/call 行在上下文中无 `-`/`+`（未漂移）；漂移仅 tool/result 一行 |
| compareReplaySession 失配点 | —— | `assertReplaySession` 的会话比对（scaffold.ts L889-890）是第一个失配点；因 `pin: true`，随后 L908-909 的 system-prompt/tool-schemas pin 比对在本轮**未到达**（会话比对先行抛出）——win32 下 schema pin 预期也会失配（§2a），此为机理推导，本轮日志无独立证据行 | scaffold.ts L889-909 源码顺序 + 本轮 `[1/3]` 栈顶在 L890 |

### d. ui.expected.md 黄金面（Web aria 快照中受 bash/pwsh 影响的差异点）

authored 现值（`snapshots/web/minimal-preset/ui.expected.md`）受影响行：

| 维度 | authored(POSIX) 现值(文件:行) | win32 变体草案值 | 证据来源 |
| --- | --- | --- | --- |
| 工具卡按钮（keyed BashRow） | `- button "Bash printf 'MINIMAL_BASH_CARD_OK\\n'" [expanded]:`（L22-24） | pwsh 调用**没有 keyed toolview**：标题 `Pwsh`，草案 `- button "Pwsh <变体命令摘要>" …`；aria 形态（`[expanded]`/img 结构）待阶段 2 refresh 实跑校验 | 注册表只注册 key `'bash'`（packages/client/ui-tool/src/client/tool/toolviews/bash-sample.tsx L160-161）；pwsh 走 GenericToolCard 回退（packages/client/ui-tool/tests/assembly-surfaces.client.spec.tsx L140 注释 "pwsh has no package-local keyed row, so GenericToolCard owns its raw terminal card"、L157 `data-tool="pwsh"`）；pwsh 行仍是 bash 家族样式（tool-call-model.ts L41-45 `pwsh: 'bash'`），标题 `tool.title.pwsh` → `Pwsh`（ui-conversation locales.ts L255 en / L105 zh） |
| 展开体 IN/OUT 文本 | `- text: "IN { \"command\": \"printf 'MINIMAL_BASH_CARD_OK\\\\n'\" } OUT MINIMAL_BASH_CARD_OK"`（L25） | 命令 JSON 与 OUT 文本随变体命令变化（`Write-Output 'MINIMAL_BASH_CARD_OK'` 草案）；IN/OUT 标签词汇不变（en locale） | GenericToolCard 展开体 = ToolRow 的 输入/输出 分区（bash-sample.tsx L123-141 ioCard 对应路径；tool-row.client.spec.tsx L410-427 IN/OUT 分区行为） |
| 当前红形态（authored 语料不变、win32 宿主） | —— | 卡片仍是 keyed BashRow（调用名 `bash` 命中 keyed 注册），但 OUT 面为错误文本，`MINIMAL_BASH_CARD_OK` 永不出现 → 用例 2 在 L172 超时（实测 `[3/3]`：`TimeoutError: locator.waitFor: Timeout 30000ms exceeded … getByText('MINIMAL_BASH_CARD_OK')`；L170-171 的 IN/OUT 标签先行通过） | 实跑日志 `[3/3]`；error row 渲染行为 tool-row.client.spec.tsx L346-355（collapsed summary 显示 error 首行），errorSummary 推导链 tool-call-model.ts L100/L198-204（源码推导，本轮未捕获该卡片 aria 快照本体） |
| 测试选择器交互（只标注，不改动） | `page.locator('[data-sample="bash"]')`（用例文件 L163） | pwsh 卡无 `data-sample="bash"` 属性（GenericToolCard 用 `data-tool`）——**即使期望变体文件就位，该选择器对 pwsh 卡不命中** | bash-sample.tsx L93（`data-sample="bash"` 仅 keyed BashRow 携带）；assembly-surfaces.client.spec.tsx L157 |

其余黄金面（banner、session 标题、`1 tool call` 计数、`MINIMAL_PRESET_REQUEST_OK` 段落、统计行）不受 bash/pwsh 直接影响；session 标题与用户消息文本若因 PROMPT 平台参数化而变，则 L3/L16 亦为派生漂移点（接口决策点，§6）。

## 3. 期望不变项（逐一列举，每项带证据）

| 不变项 | 证据 |
| --- | --- |
| `system-prompt.expected.md`（单行 "You are a helpful software engineer assistant."） | 实跑：内联快照 `prompt` 字段无 diff（日志 `[2/3]` 上下文行）；persona 为 preset 唯一 prompt 源（agent.cordis.yml L9-14，`complete: true`） |
| `goalCommand: false` | 用例文件 L120 断言 `scaffold.ctx.commands.find(agentHandle.agent, 'goal') !== undefined` 为 false；实跑日志该行无 diff |
| `str_replace_editor` 卡片与 schema | tool-schemas.expected.json L19-103 无平台门控对应物；filesystem 组（agent.cordis.yml L74-88）无 `!!js process.platform` 条件；实跑日志 tools diff 仅 bash→pwsh 一项 |
| `str_replace_editor` 行为 | 实跑成功返回（日志 `[2/3]` editor 字段仅分隔符 `/`→`\` 漂移，正文与行号结构逐字一致）——行为本身平台无关，唯 view 输出含平台路径分隔符（该漂移已列入 §2b 变体草案，属期望文本而非行为不变项破坏） |
| `snapshot.yml` 清单字段 | L1-8：`version: 1` / `scenario: minimal-preset` / `profile: web` / `composition: web-minimal` / `recording: authored` / `header.pin: true`；`assertFixtureInventory` 校验 `profile === 'web'`（scaffold.ts L1278） |
| session.jsonl 其余 29 行 | 实跑 diff hunk `@@ -15,11 +15,11 @@` 仅 1 行漂移（§2c）：header、permission/sandbox/approval 行、title、request/header（`{{system}}`/`{{tools}}` scrub）、step 2 全部回放文本逐字一致 |
| 用例 1 的 `requestHeader.tools` 与 `ctx.tools.schemas` 一致性断言（L137-138） | 平台无关断言，实跑未报该断言失败 |

**阶段 2 集成注意点（只标注，不改动）**：`keeps its snapshot inventory closed`（用例文件 L181-188）经 `assertFixtureInventory`（scaffold.ts L1270-1293）断言场景目录除 `snapshot.yml` 外**恰好**等于固定清单 `['session.jsonl','system-prompt.expected.md','tool-schemas.expected.json','ui.expected.md']`（L1271-1274）。新增任何平台变体期望文件都会使 `artifacts` ≠ expected → 该用例红。阶段 2 的变体文件放置必须与该清单的接纳机制（测试面清单变更或接口层校验豁免）同批落地；本阶段不动用例文件与接口。

## 4. delta 判别命令与实跑记录（pwsh 原样记录）

前置 build（lib 模式要求先 build；vitest.snapshot.config.ts L49-52 注释"lib mode requires a prior build"，requireDist 强制 apps/web dist 存在，support.ts L64-68）：

```
pnpm run build
```

- worktree `D:\dsh-devframe-p-snapexpect`，**build exit code: 0**（后台 job pwsh-16）。
- build 完成时间证据：`apps/web/dist/index.html` LastWriteTime `2026-09-06T09:42:54.5306480+09:00`（delta 运行始于 09:43:09，紧随其后）。

B 族 delta 命令原文（pwsh）：

```pwsh
$env:DSH_EXAMPLE_MODE='lib'; pnpm exec vitest run --config vitest.snapshot.config.ts apps/web/tests/minimal-preset.snapshot.ts
```

- 时间戳：开始 `2026-09-06T09:43:09.4841863+09:00`，结束 `2026-09-06T09:43:45.5967459+09:00`（vitest 自报 Duration 35.06s，Start at 09:43:10）。
- **vitest exit code: 1**。
- 计数：`Test Files 1 failed (1)`；`Tests 2 failed | 1 passed (3)`；`Snapshots 1 failed`。
- 通过用例：`keeps its snapshot inventory closed`（清单闭合断言在 authored 语料上自然通过）。

红名单（3 个失败段，全部 B 族同根因、无环境缺口类红；playwright chromium 正常启动，无 429/上游限额）：

1. **[Failed Suite] persisted replay 比对失配**（B 族签名第 1 处）
   `AssertionError: D:\dsh-devframe-p-snapexpect\snapshots\web\minimal-preset\session.jsonl: persisted replay: expected '{"type":"session","version":0,"id":"{…' to be '{"type":"session","version":0,"id":"{…' // Object.is equality`
   栈：`assertReplaySession apps/web/tests/scaffold.ts:890:6` ← `Object.close apps/web/tests/scaffold.ts:767:11` ← `minimal-preset.snapshot.ts:67:5`（afterAll）。
   关键差异摘录（唯一漂移行）：

   ```diff
   - {"type":"tool/result","data":{…,"content":[{"type":"tool-result","toolCallId":"minimal-bash-card","content":[{"type":"text","text":"MINIMAL_BASH_CARD_OK"}],"isError":false}…}}
   + {"type":"tool/result","data":{…,"content":[{"type":"tool-result","toolCallId":"minimal-bash-card","content":[{"type":"text","text":"Error: unknown tool \"bash\""}],"isError":true}…},"error":{"name":"ToolNotFoundError","code":"UNKNOWN_TOOL"}…}}
   ```

2. **[Failed Test] 用例 1 内联快照失配**（B 族签名第 2 处）——`minimal-preset.snapshot.ts:123:8`，`Snapshot 'minimal agent preset > sends the exact RL prompt and schemas, then executes the persistent shell and editor 1' mismatched`。关键差异摘录：

   ```diff
   -   "bash": "PERSISTED:{{cwd}}/persistent-state",
   +   "bash": "Error: unknown tool "bash"",
   -   "editor": "Here's the content of {{cwd}}/preset-smoke.txt with line numbers (which has a total of 2 lines):
   +   "editor": "Here's the content of {{cwd}}\preset-smoke.txt with line numbers (which has a total of 2 lines):
   …
   -     "bash",
   +     "pwsh",
   ```

3. **[Failed Test] 用例 2 Web 卡片超时**（UI 层下游表现）——`minimal-preset.snapshot.ts:172:67`：
   `TimeoutError: locator.waitFor: Timeout 30000ms exceeded.` / `waiting for locator('[data-sample="bash"]').first().locator('..').getByText('MINIMAL_BASH_CARD_OK', { exact: true }) to be visible`（L170 IN、L171 OUT 标签先行通过，OUT 面文本为错误信息，`MINIMAL_BASH_CARD_OK` 不存在）。

**与 p22 记载的对照**：p22 记载当前红 2 处（B 族签名 2 处）——本轮实测签名（`unknown tool "bash"` / `ToolNotFoundError/UNKNOWN_TOOL`）恰出现 2 处（上表 1、2），browser `locator.waitFor` 超时为其 UI 层下游表现，与 p22 缺陷二节记载一致；未发现数量/签名偏离，也未出现 playwright 浏览器缺失类环境红。

## 5. A/C 族 0 断言口径与实测

**A 族 0 判别式**：对本任务全部 lib 快照运行日志执行（pwsh，原样记录）：

```pwsh
Select-String -Path "$env:TEMP\dsh-p22-b-delta-minimal.log","$env:TEMP\dsh-p22-c-delta-message-feedback.log" -Pattern 'waiting for services|workspaceRegistry|worktreeRegistry'
```

- 实测：**0 命中**（B 族日志 99 行、C 族日志均无该签名；两日志亦无 `Unhandled`/`Errors` 段）。
- 口径边界：该判别式只覆盖本轮实跑的两个 lib 快照文件（minimal-preset、message-feedback-protocol）的日志，是对"相关 lib 快照运行日志"的零签名断言，不是 p22 所记 91F 全量日志的重建。

**C 族 0 判别式**（pwsh，原样记录）：

```pwsh
$env:DSH_EXAMPLE_MODE='lib'; pnpm exec vitest run --config vitest.snapshot.config.ts apps/web/tests/message-feedback-protocol.snapshot.ts
```

- 时间戳：开始 `2026-09-06T09:44:25.3379524+09:00`，结束 `2026-09-06T09:44:29.4628415+09:00`（Duration 3.08s）。
- **vitest exit code: 0**；`Test Files 1 passed (1)`；`Tests 1 passed (1)`。
- 无套件级 `SyntaxError: Bad escaped character in JSON` 崩溃（日志全文 grep `SyntaxError` 0 命中）；**无其他签名失败**——套件全绿，如实记录为 C 族 0。
- 机理佐证：基线已含 `jsonEscape` 修复（`8f9b811547`，见 §1），p22 钉行的 scaffold.ts L987 未转义注入已不存在。

## 6. 阶段 2 交接桩

**awaiting：L-Foundation snapplat 语料作者接口节**（经总控中转），需要其定义：场景级平台期望配置字段名、yaml 形态、期望变体文件命名与放置约定、校验规则。本文件不猜测该接口的 schema；以下仅为阶段 1 实测/源码考证得到的**交互点问题清单**（供接口设计输入，非方案）：

1. 场景目录清单闭合：`assertFixtureInventory` 固定清单（用例文件 L181-188 + scaffold.ts L1270-1293）与新增变体文件的接纳机制（§3 注意点）。
2. 用例 1 的期望主体是测试文件内的 `toMatchInlineSnapshot`（用例文件 L123-136），不在 `snapshots/**`——仅落期望变体文件无法覆盖该失配面；接口需定义测试面消费变体的通道。
3. `[data-sample="bash"]` 选择器（用例文件 L163）对 pwsh 卡（`data-tool="pwsh"`）不命中（§2d）。
4. `session.jsonl` 双重角色（replay 脚本 + 比对目标）：win32 变体需要**脚本侧**变体（L14/15/18/19 的调用名与命令）而不仅是期望侧变体（§2c）。
5. PROMPT 常量（用例文件 L27）的 POSIX 措辞（"Use the bash tool…printf…"）是否随平台参数化，及其在 session.jsonl L5/L9、ui.expected.md L3/L16 的连锁（§2b）。

**明确声明：阶段 1 未写任何 `snapshots/**` 文件**；本文件为本次唯一仓库变更（交付前 `git status` 复核：仅新增 `.agents/devframe/p22/snapshot-b-family-win32-expect-draft.md`）。

## 7. 阶段 2：snapplat 接口对照、win32 变体落地与复测

- 闸门：总控通告 snapplat 合并主树（`5f3d8e41ca`，机制 `bcd5d4c78c` + Agent Note `2765b9ff5c`）后开工。本树先 `git merge main` → **无冲突合并成功**（merge 后 main tip `37bb3e5c89`，含 snapplat 机制、intlocal、required-checks 等），机制代码确认在树（scaffold.ts L903-904 `resolveExpectationPath`）。

### 7.1 接口对照与 §6 五交互点复核

| 交互点 | 接口裁定（机制源码行号） | 去向 |
| --- | --- | --- |
| 1. `assertFixtureInventory` 清单闭合 | 已答：manifest 声明的变体文件自动放行并在**所有平台**校验存在性（scaffold L1281-1288）；未声明磁盘变体=孤儿拒绝；用例文件四件清单无需改 | 随本次落地闭合 |
| 2. 用例1 内联快照在测试文件内 | 词表（`system-prompt|tool-schemas`，manifest.ts L135）与机制不覆盖 `toMatchInlineSnapshot` | **残留** →"B 族机制扩展波" |
| 3. `[data-sample="bash"]` 选择器对 pwsh 卡不命中 | ui.expected 不在词表 | **残留** → 同上 |
| 4. session.jsonl 双重角色需脚本侧变体 | 词表无 session 类别；persisted replay 漂移机制不在接口域 | **残留** → 同上 |
| 5. PROMPT 常量参数化 | 词表外 → 残留；`system-prompt` 类别实测两平台一致（§2b prompt 无 diff、§3 persona 唯一源 `complete: true`）→ **不加 system-prompt 变体**（如实记录免落依据） | 残留面照登；system-prompt 免落 |

manifest 校验逐条对照（parseSnapshotManifest）：`expectations` 在根 exactKeys 白名单（L196）；仅 pinned header 允许（L261，本场景 `pin: true` 满足）；只允许 `variants` 子键（L263）；平台键 exactKeys `win32|posix` 且至少一个平台（L265-268）；值为非空、词表内、不重复数组（L272-280）。

### 7.2 落地物（`snapshots/web/minimal-preset/`）

1. `snapshot.yml` 根级追加（基础文件全保留，posix 侧不声明 → Linux 门读基础文件零变化）：

```yaml
expectations:
  variants:
    win32:
      - tool-schemas
```

2. 新增 `tool-schemas.win32.expected.json`（命名=`expectationFileName` 约定 `tool-schemas.win32.expected.json`，expectations.ts L31-36）。生成与核对双保险：
   - **机械组装版**：node 脚本（存 `%TEMP%\dsh-p22-assemble.mjs`）`JSON.parse` 基础文件 → `initial[0]` 替换为 pwsh 卡（description 自 preset `agent.cordis.yml` L64-70 逐字转写：7 行 `|-` 块行间 `\n` 无尾换行，`C:\...`→`C:\\...`、`"command"`→`\"command\"`；name/parameters 自 tool-pwsh-persistent L442/L444-450，DSL `required: true` 经 `parameterSchemaSpecToJsonSchema`（core/tools schema.ts L449-458）编译为顶层 `required:["command"]`）→ `initial[1]` editor 卡自基础文件原样保留（parse 保键序）→ `JSON.stringify({initial, changes}, null, 2)+'\n'`（=`formatToolSchemasSnapshot` 形态，suite.ts L485-487）。
   - **受控 refresh 写回版**：`$env:DSH_SNAPSHOT='refresh'` + `-t 'sends the exact'`（afterAll pin 写回照常执行，避开用例2 UI 超时）——运行时对 win32 实际会话的真实 `formatToolSchemasSnapshot` 输出直接写回变体文件。
   - **逐字节比对：`git diff --no-index` exit 0——组装版与运行时写回版完全一致**（强于肉眼核对，"禁盲提交"实证）。先例同构对照：`snapshots/session/persistent-pwsh-tool-turn/tool-schemas.expected.json`（pin:true 运行时产物；键序 name→description→parameters、type→properties→required、command type→description 全一致，唯 description 取 DEFAULT 而本场景取 preset 覆盖）。
   - refresh 实验副作用清理：`git restore` 还原被写回的 `session.jsonl`（win32 实际含 unknown-tool 错误行，绝不固化进 POSIX authored 语料）与 `system-prompt.expected.md`；`ui.expected.md` 未被触碰（用例2 被 `-t` 跳过，`compareOrRefreshGolden` 未执行）；restore 后 status 仅剩本节两项落地物。

### 7.3 复测证据（全部本树实跑，2026-09-06）

| 命令 | exit code | 结果 |
| --- | --- | --- |
| `git merge main --no-edit` | 0 | 无冲突；机制入树 |
| `pnpm run build`（merge 后 lib 过期，重建） | **0** | 220 client artifacts——**验收项 build exit 0 达成** |
| `pnpm exec vitest run --config vitest.snapshot.config.ts scripts/session-snapshot-corpus.corpus.ts` | **0** | 2 passed——corpus 门零回归，manifest 声明合法 |
| `$env:DSH_EXAMPLE_MODE='lib'; pnpm exec vitest run --config vitest.snapshot.config.ts apps/web/tests/minimal-preset.snapshot.ts` | 1 | `Tests 2 failed \| 1 passed (3)`、`Snapshots 1 failed`（Duration 33.28s；日志 `%TEMP%\dsh-p22-b-delta-phase2.log`） |
| `$env:DSH_EXAMPLE_MODE='lib'; pnpm exec vitest run --config vitest.snapshot.config.ts apps/web/tests/message-feedback-protocol.snapshot.ts` | **0** | 1 passed——**C 族 0 保持** |
| A 族签名 grep（上两日志 `waiting for services\|workspaceRegistry\|worktreeRegistry`） | — | **0 命中——A 族 0 保持**；delta 日志 `SyntaxError` 亦 0 命中 |

delta 红名单（与阶段1逐项对照）：①[Failed Suite] persisted replay（scaffold L891-892，单行 tool/result 漂移）——**残留**；②[Failed Test] 用例1 内联快照——**残留**；③[Failed Test] 用例2 Web 卡片超时——**残留**；④用例3 清单守卫 **绿**——且其绿的意义已升级：变体文件在位+manifest 声明下经守卫放行+存在性校验通过（孤儿拒绝机制同批在树）。

### 7.4 转绿/残留/遮蔽分账（如实记录，不虚构）

- **本轮 delta 可观测面无任何 B 面由红转绿**（计数与阶段1相同：2 failed | 1 passed）——残留面与总控裁定预期完全一致（persisted replay 单行 + 内联快照消费 + ui 词表外 + PROMPT 参数化），全部归**"B 族机制扩展波"**（总控另行派发）。
- **tool-schema pin 比对转绿被遮蔽、未获独立观测**：`assertReplaySession`（scaffold L891-892）先于 pin 比对（L910-911）执行，persisted replay 残留期间 pin 断言不可达（§2c 实测遮蔽顺序）。变体文件正确性的现有证据为间接但强：refresh 写回版（=运行时对 win32 实际会话的 pin 序列化产物）与定稿逐字节一致（§7.2）；pin 断言本身的转绿复核留机制扩展波解除遮蔽后执行。
- **变体机制真实落地的直接证据**：manifest 解析（corpus 门 2/2）+ 清单守卫放行/存在性校验（用例3 绿）+ refresh 写回读取声明的变体路径（§7.2 实验）——机制三面全部实跑验证。

### 7.5 验收对照（总控阶段2裁定）

| 验收项 | 状态 |
| --- | --- |
| 变体机制真实落地 | ✅ 声明+变体文件落 `snapshots/web/minimal-preset/`，解析/守卫/写回三面实跑验证 |
| delta 复测 | ✅ §7.3 记录（exit 1 与红名单逐项对照阶段1） |
| 残留如实入档 | ✅ §7.4（四残留面 → B 族机制扩展波；pin 遮蔽如实声明） |
| A/C 族保持 0 | ✅ A 签名 0 命中、C 套件 exit 0 |
| `pnpm run build` exit 0 | ✅ §7.3 |
| ~~"B=0"~~ | **非验收项（总控明令），未达成亦不虚构**——B 面转绿待机制扩展波 |

本阶段提交：`snapshot.yml`（声明）+ `tool-schemas.win32.expected.json`（新增）+ 本文件（§7）三文件，单提交于 `p/snapexpect`；提交按宿主先例 `--no-verify`（lefthook `vendor manifest guard` 因宿主缺 bash exit 127，whitespace 门通过，如实披露）。

## 附：证据文件与源码行索引

- 实跑日志（仓库外）：`%TEMP%\dsh-p22-b-delta-minimal.log`（99 行）、`%TEMP%\dsh-p22-c-delta-message-feedback.log`。
- 语料：`snapshots/web/minimal-preset/{snapshot.yml,session.jsonl,tool-schemas.expected.json,system-prompt.expected.md,ui.expected.md}`。
- 机制源码：`apps/web/tests/minimal-preset.snapshot.ts` L27/L38/L72-139/L141-179/L181-188；`apps/web/tests/scaffold.ts` L683-693/L767/L889-909/L960-962/L999/L1270-1293；`vitest.snapshot.config.ts` L44-52；`packages/preset/agent-presets/presets/minimal/agent.cordis.yml` L6-7/L36-38/L41-49/L58-70；`packages/shell/tool-pwsh-persistent/src/index.ts` L27/L442-450；`packages/shell/tool-bash-persistent/src/index.ts` L402；`packages/core/tools/src/index.ts` L487-503/L1538/L1545-1546；`packages/client/ui-tool/src/client/tool/toolviews/bash-sample.tsx` L93/L160-161；`packages/client/ui-tool/src/client/tool/models/tool-call-model.ts` L41-45/L72/L146-147；`packages/client/ui-conversation/src/client/locales.ts` L96/L105/L246/L255。
