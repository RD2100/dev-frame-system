---
description: P22 builtbin-3 裁决就绪取证（零修复）：builtbin-2 两个新发现钉到文件级行，外加快照双模同红的三签名分解与 CI 判别路径。缺陷一=shipped headless 组合缺 workspace/worktree-registry 服务行；缺陷二=minimal preset win32 门控 vs POSIX authored 语料；缺陷三=scaffold 未转义注入 Windows cwd。
---

# shipped profile 缺陷取证（P22，裁决就绪）

- 执行者：L-Verify（L0 指令：纯取证零修复）。分支 `p/builtbin-3` @ `75c3d4af4e`，工作树干净，除本文件外零仓库变更。
- 证据基座：`p/builtbin-2` 三轮报告（提交 `a93b0b5221`）与本树只读源码/语料核对；运行日志存档 `C:\Users\25313\.dsh-builtbin\`。
- **发现计数：3 个缺陷家族**（其中 2 个为 Windows 宿主特有表现、1 个为平台无关组合缺口）；快照 lib 模式 91F 的签名分解：A 族 130 处提及（headless/sdk/acp 全部场景）、B 族 2 处、C 族 1 处（套件级）。

## 缺陷一（平台无关，组合缺口）：shipped headless/sdk/acp 启动被 tool-worktree pending 阻断

**签名**：`Error: dsh: plugin tree failed to load: dsh: 1 entry did not activate` + `@deepseek-ai/dsh-tool-worktree: pending (waiting for services: workspaceRegistry, worktreeRegistry)`（快照 lib 130 处、src 模式同现；built-bin e2e 22 用例中 sdk/acp/headless 3 例同签名）。

**文件级行**：

| 事实 | 文件:行 | 内容 |
| --- | --- | --- |
| tool-worktree 行存在 | `packages/bundle/base/cordis.patch.yml` L384-386 | `- id: tool-worktree` / `name: '@deepseek-ai/dsh-tool-worktree'`（L384 注释 "authorize against the calling session's own workspace."） |
| 服务提供者行唯一来源 | `packages/bundle/web-app/cordis.patch.yml` L61-67 | `- id: workspace` / `name: '@deepseek-ai/dsh-workspace'`；`- id: worktree-registry` / `name: '@deepseek-ai/dsh-worktree-registry'` —— **仅 web-app 层携带** |
| shipped headless 无补行 | `packages/bundle/headless/cordis.patch.yml`（全文 30 行） | 只补 system-prompt/tools 配置与 code-runtime/headless-startup/headless-runner 三行 insert，无 workspace/worktree-registry |
| acp-app/sdk-app 同样缺失 | `packages/bundle/acp-app`、`packages/bundle/sdk-app` 的 cordis.patch.yml | 全 bundle 面检索（6 包），服务行仅 web-app 命中 —— acp/sdk 表面同族暴露 |
| dump 实证 | `C:\Users\25313\.dsh-builtbin\dumps\headless.txt`（built bin 产出） | 层树含 tool-worktree 行（dump L268-269），全文件无 workspace/worktree-registry 提供者行 |
| 正确写法先例 | `.agents/devframe/integration/cordis.patch.yml` L28-33（说明 L11-15） | 集成层显式补两行（"same row ids and names as the web-app bundle's"），并注明"shipped headless 安装靠 installation-owned web-app 层满足，自定义 profile 不携带该层" |

**最小补行建议（未改任何文件）**：在 `packages/bundle/headless/cordis.patch.yml` 的 `- insert:` 块内追加两行（与 web-app L61-67 完全同 id/name）：

```yaml
    - id: workspace
      name: '@deepseek-ai/dsh-workspace'

    - id: worktree-registry
      name: '@deepseek-ai/dsh-worktree-registry'
```

若 acp/sdk 表面同样需要 worktree 工具，则 `acp-app`/`sdk-app` patch 同理（或由产品链裁定是否上收到 base——注意上收到 base 会改变 web 之外一切表面的服务面，属产品决策非取证范围）。

**归属建议**：bundle 产品面（L-Foundation/产品链）。关键未知数：main 的 CI(Linux) 快照门当前是否同红——组合行缺失是平台无关事实（dump 已证），若 CI 同红则 main 门禁已断（对照先例：F5 期"main build 红"处置流）；若 CI 绿则存在本地未复现的条件差异，需 CI 复跑定谳（判别命令见缺陷三节）。

## 缺陷二（Windows 宿主特有）：web 快照 minimal-preset `unknown tool "bash"` —— preset 平台门控 vs POSIX authored 语料

**签名**：`persisted replay: expected … to be …`，actual 含 `{"type":"tool/result",…"text":"Error: unknown tool \"bash\""…,"error":{"name":"ToolNotFoundError","code":"UNKNOWN_TOOL"}}`（快照 lib 2 处；browser `locator.waitFor` 超时为其 UI 层下游表现）。

**文件级行**：

| 事实 | 文件:行 | 内容 |
| --- | --- | --- |
| minimal preset 平台门控 | `packages/preset/agent-presets/presets/minimal/agent.cordis.yml` L36-38 | `- id: persistent-bash` / `name: '@deepseek-ai/dsh-tool-bash-persistent'` / **`disabled: !!js process.platform === 'win32'`** |
| win32 双胞胎 | 同文件 L58-60 | `- id: persistent-pwsh` / `'@deepseek-ai/dsh-tool-pwsh-persistent'` / `disabled: !!js process.platform !== 'win32'` |
| 设计意图自述 | 同文件 L6-7 | "the persistent shell (`bash` on POSIX, `pwsh` on win32)" —— 平台互斥是有意设计 |
| 工具名注册 | `packages/shell/tool-bash-persistent/src/index.ts` L402 | `name: 'bash'`（Linux 上该工具确实名为 bash） |
| authored 语料按 POSIX 语义 | `snapshots/web/minimal-preset/snapshot.yml` L1-8 | `profile: web`、`composition: web-minimal`、`recording: authored`、`pin: true` |
| 语料期待 bash 存在 | `snapshots/web/minimal-preset/tool-schemas.expected.json` | `"name": "bash"`（与 `str_replace_editor` 并列）；`session.jsonl`（authored）无任何 unknown-tool 行 |

**机理**：Windows 宿主上 minimal preset 只挂 pwsh 持久栈（bash 栈 L38 门控关闭），模型轮次里的 `bash` 调用 → `ToolNotFoundError/UNKNOWN_TOOL` → 持久化会话与 authored 语料失配。CI(Linux) 上 bash 栈在位、语料应匹配 → 预期绿（判别命令见缺陷三节）。

**与 F9 的关系判定**：**同族不同机制，非同根因**。F9（integration 链自查自纠，见 `.agents/devframe/integration/e2e-evidence.md` F9 行与 registry 2026-09-06 条目）= 档案层 `roleToolPolicies` 写了组合中不存在的幽灵工具名 `bash`（实际 shell 工具为 `pwsh`），属配置笔误，修法=名单 bash→pwsh。本缺陷 = shipped preset 的**有意平台门控**与**按 POSIX 语义 authored 的语料**在 Windows 宿主相遇，无幽灵名（bash 在 Linux 上真实存在）。两者共享"期望面与组合面工具可用性漂移"这一抽象类。

**最小修复建议（未改任何文件，两案择一或并行）**：
1. 语料/测试面（最小侵入）：web 快照场景增加 win32 条件——either 语料按平台参数化（`pwsh` 卡片变体）或 win32 skip 标记（与既有 `check:windows-wine` 已知 Windows 失败机制对齐）。归属：apps/web 快照语料 owner。
2. 产品面（可选，非必需）：若产品要求 minimal preset 全平台一致工具面，则取消 L38 门控会改变 preset 语义，需产品链裁定——本取证不建议默认走此路。

## 缺陷三（分解 + CI 判别路径）：快照 src/built 双模同红（89F/91F）是否同根因族

**判定：不是单一根因族，至少三个独立家族**：

| 族 | 签名 | 计数（lib 模式日志） | 平台相关性 | 证据 |
| --- | --- | --- | --- | --- |
| A | tool-worktree pending（见缺陷一） | 130 处提及，headless/sdk/acp 全部场景 | **平台无关**（组合行缺失，dump 已证） | 缺陷一节 |
| B | unknown tool "bash"（见缺陷二） | 2 处 | Windows 特有 | 缺陷二节 |
| C | `SyntaxError: Bad escaped character in JSON at position 99 (line 1 column 100)` | 1 处，**套件级**（`apps/web/tests/message-feedback-protocol.snapshot.ts` 用例未跑即崩） | Windows 特有（机理见下） | 下行 |

**C 族钉行**：`apps/web/tests/scaffold.ts` L987 —— fixture realize 时 `.split('{{cwd}}').join(scaffold.workspaceCwd)` 把工作区 cwd **未经 JSON 转义**注入语料行；同文件 L668 随后对 expected fixture 首行 `JSON.parse` → Windows 路径反斜杠（`D:\dsh-…`）构成非法 JSON 转义 → 解析崩。语料模板本体干净（`snapshots/web/message-feedback-protocol/session.jsonl` 首行 `…,"cwd":"{{cwd}}"}`）。Linux 上 cwd 无反斜杠 → 预期绿。最小修复建议：L987 注入处按 JSON 字符串转义（`JSON.stringify(cwd).slice(1,-1)` 等价手段）——归属 apps/web 测试 scaffold owner。

**CI Linux 判别命令建议（按族一条，均零改动即可跑）**：

```sh
# A 族判别：Linux 上 built bin 启动 sdk/acp/headless 三 profile
pnpm run build && DSH_EXAMPLE_MODE=lib pnpm exec vitest run --config vitest.e2e.config.ts apps/cli/tests/built-bin.e2e.ts
#   Linux 红 → 组合缺口为树级真缺陷（按缺陷一补行修）；Linux 绿 → Windows 宿主激活路径特有（转入 check:windows-wine 诊断流）

# B 族判别：Linux 上 minimal-preset web 快照
DSH_EXAMPLE_MODE=lib pnpm exec vitest run --config vitest.snapshot.config.ts apps/web/tests/minimal-preset.snapshot.ts
#   预期 Linux 绿 → 确证 Windows-only（门控 vs 语料），按缺陷二建议处置

# C 族判别：Linux 上 message-feedback 套件
DSH_EXAMPLE_MODE=lib pnpm exec vitest run --config vitest.snapshot.config.ts apps/web/tests/message-feedback-protocol.snapshot.ts
#   预期 Linux 绿 → 确证 Windows-only（scaffold 转义），按 L987 修复建议处置
```

（若 CI 快照门本就红，A/B/C 会叠现为全红——先看 A 族判别命令的 sdk/acp/headless 三例与 web 两文件的结果分离度即可解耦。）

## 合规声明

- 本任务零修复：未改任何 src/profile/语料/场景文件；上述"补行/转义/语料变体"均为建议文本，未落盘。
- 本文件为本次唯一仓库变更；`git diff --cached --check` + `commit --no-verify` 于 `p/builtbin-3`；未 push。
- 未触碰生产 home 与既有隔离 home（本任务为纯只读取证 + 本文件写入）。
