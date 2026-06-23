<p align="center">
  <img src="docs/assets/devframe-system-banner.svg" alt="dev-frame-system：把网页 AI 作为外部大脑" width="100%" />
</p>

<h3 align="center">把 GPT Web 或任何可用的网页 AI，变成你现有软件工具和 coding agent 的外部大脑。</h3>

<p align="center">
  <a href="README.md">English</a> | 简体中文
</p>

<p align="center">
  <a href="#为什么需要它">为什么需要它</a> |
  <a href="#它具体做什么">它具体做什么</a> |
  <a href="#快速开始">快速开始</a> |
  <a href="#仓库结构">仓库结构</a>
</p>

```text
devframe code "<goal>"  # 在当前仓库启动类似 Codex 的编程会话
/rdinit                 # 初始化外部大脑操作层
/bindChrome <url>       # 绑定 GPT Web、DeepSeek、豆包或其他网页 AI 会话
/go <project> <goal>    # 准备或运行并发 coding agent 分片
/rdgoal <project> <goal> # 把项目目标路由进总控闭环
/rdpaper <project> <goal> # 把论文任务路由进论文审查闭环
```

**核心问题不是"再做一套治理框架"。真正的问题是：如何用尽量低的成本和最简单的流程，提高代码质量，并让研发方向不漂移？**

dev-frame-system 的答案是：把网页 AI 会话变成软件研发的**外部大脑**。网页 AI 负责保存产品方向、工程取舍、任务边界、证据、审查结论和经验记忆；IDE、CLI、浏览器、脚本、测试框架以及不同厂商的 coding agent 都是可替换的执行器。

落到产品形态上，第一个主入口是 `devframe code`：一个面向 Codex、Claude Code、OpenCode 或其他 worker 命令的本地编程 CLI。它不替代模型，也不替代 IDE；它负责限定任务边界、准备 coding 会话、按需拆分并发 agent，并把状态写进可选的只读 Dashboard。

## 为什么需要它

AI coding 工具很擅长产出代码，但它们经常不擅长三件事：记住真正的产品方向，证明代码确实变好了，以及在工作跑偏前停下来。

dev-frame-system 在工具之上放了一层思考与协调层：

| 常见做法 | dev-frame-system 做法 |
|---|---|
| 直接让某个 agent 修问题 | 先让绑定的网页 AI 明确范围、风险和验收标准 |
| 相信 agent 的最终回复 | 要求证据、验证输出和可审查报告 |
| 每个工具各自保存上下文 | 把方向和决策放在同一个外部大脑里 |
| 再引入一个重平台 | 复用你已经在用的网页 AI 和工具 |
| 乱了之后再补质量 | 每个任务都经过规则、schema 和证据门禁 |

一句话：

> 网页 AI 负责思考和协调。工具负责执行。证据决定能不能接受。

## 它具体做什么

dev-frame-system 提供一套可迁移的 agent 研发操作层：

- **方向把控**：在写代码前，把目标、边界、风险和取舍放到同一个上下文里。
- **任务调度**：把模糊需求变成有边界的 TaskSpec，交给 Codex、Claude Code、CLI、浏览器自动化或其他 agent。
- **并发 coding agent 入口**：用 `/go` 或 `devframe go` 准备多个有边界的编码分片；确认要花 agent token 时，再通过 OpenCode 或其他 worker 并发执行。
- **证据审查**：用 ExecutionReport、证据索引、审查门禁和负面夹具防止"假完成"。
- **可复用引导**：用 PowerShell bootstrap 把同一套操作层部署到其他项目。
- **外部大脑绑定**：用 `/bindChrome` 把稳定的网页 AI 会话绑定到当前项目。
- **总控编排**：用 `rdgoal` 协调多个项目本地 workflow，记录 controller 决策、rollback snapshot、dispatch packet 和最终报告。
- **论文审查闭环**：用 `/rdpaper` 让网页 AI 负责论文评审判断，本地 agent 负责脱敏任务包、证据和报告。

## 快速开始

克隆仓库：

```powershell
git clone https://github.com/RD2100/dev-frame-system.git
cd dev-frame-system
```

检查公开快照：

```powershell
.\scripts\verify-public-snapshot.ps1
```

在发布本地版本或共享 control-plane 包之前，先运行发布验证入口：

```powershell
.\scripts\verify-release.ps1
```

把外部大脑操作层引导到另一个项目：

```powershell
.\templates\runtime-bootstrap\bootstrap.ps1 `
  -ProjectName "my-project" `
  -ProjectRoot "D:\my-project" `
  -DryRun

.\templates\runtime-bootstrap\bootstrap.ps1 `
  -ProjectName "my-project" `
  -ProjectRoot "D:\my-project"
```

引导完成后，从 agent 环境中绑定浏览器 AI 会话：

```text
/bindChrome https://chatgpt.com/...
```

可选：安装 control-plane CLI，并用 `rdgoal` 路由一个项目：

```powershell
cd .\packages\control-plane
pip install -e .
cd D:\my-project
devframe code "Build the MVP" --target src --runtime-dir "$env:TEMP\devframe-code" --dashboard
rdgoal "D:\my-project" "Build the MVP" --digest
devframe go "D:\my-project" "Build the MVP" --agents 3 --target src --runtime-dir "$env:TEMP\devframe-go"
```

`devframe code` 是更接近 Codex/OpenCode 形态的编程入口。它默认作用于当前仓库，准备一个有边界的 coding-agent 会话，打印精确 worker 命令，并把状态写入 Dashboard 可读取的 runtime。真实 git 工作区里推荐用 `--changed --agents auto`：只把 modified、staged 或 untracked 文件作为 target，并按文件数自动拆成有上限的并发分片；`--max-agents` 可以调整自动拆分上限。先用 `--preview` 可以只看分片计划，不创建 packet，也不消耗 worker token。准备真正消耗 worker token 时再加 `--execute`。加 `--dashboard` 会直接启动同一个 runtime 的本地只读可视化界面；在 Dashboard URL 后追加 `?lang=zh-CN` 可切换中文界面。

`/rdgoal` 是面向用户的 slash 入口。在 shell 中使用已安装的 `rdgoal` 命令。`devframe rdgoal` 作为兼容形式仍然可用于已经使用 umbrella CLI 的脚本。

`/go` 是面向编程工具形态的入口。在 shell 中，`devframe go` 默认只准备并发 coding agent dispatch packet，并打印精确 worker 命令，不会立刻消耗 agent token。加 `--execute` 后才会并发运行这些分片；不传 `--command` 时默认使用 `opencode run -m stepfun/step-3.7-flash --agent build`，也可以用 `--command <your-worker>` 接入其他执行器。传 `--changed --agents auto` 可以从 git 变更自动生成分片 target，并自动选择并发数，避免项目级大上下文。
Visual Control Plane 会读取同一个 runtime，并显示 go-run 以及每个 coding-agent 分片的目标、packet、状态和 worker 命令。

然后通过外部大脑闭环运行工作：

1. 在网页 AI 中明确目标、风险、范围和验收标准。
2. 把任务转成有边界的 TaskSpec。
3. 分发给 Codex、Claude Code、CLI 脚本或浏览器自动化执行。
4. 收集 ExecutionReport 和验证输出。
5. 只有证据通过审查门禁，才接受这次工作。
6. 把可复用经验沉淀回项目记忆。

## 四个技能入口

| 技能 | 用途 | 结果 |
|---|---|---|
| `/rdinit` | 给仓库初始化 dev-frame-system 操作层 | `AGENTS.md`、规则、schemas、工具策略、能力清单和运行时文档 |
| `/bindChrome <url>` | 把网页 AI 会话绑定到当前项目 | 一个稳定的外部大脑会话，连接本地项目上下文 |
| `/go <project> <goal>` | 准备或运行并发 coding agent 分片 | go-run 记录、每个 agent 的 rdgoal packet、worker 命令，以及 Dashboard 可见的 runs |
| `/rdgoal <project> <goal>` | 把项目目标交给总控编排 | 项目 contract、controller 决策、dispatch packet、worker 报告和 runtime digest |
| `/rdpaper <project> <goal>` | 把论文任务交给论文审查控制面 | 论文工作区、Web AI Adapter 配置、隐私闸门、审查报告和证据摘要 |

提供商说明：GPT Web 是默认参考路径，因为它容易获得，也适合长上下文协调。提供商可以替换，契约不能替换。浏览器托管提供商使用 `docs/agent-runtime/web-ai-adapter-contract.md` 和 `schemas/web_ai_adapter.schema.json`；Chrome 加 ChatGPT 是参考适配器，不是硬编码边界。如果另一个网页 AI 不能稳定保存项目上下文、协调任务并审查证据，更适合作为二级审查器，而不是主外部大脑。

未来产品形态可参见 [Visual Control Plane](docs/agent-runtime/visual-control-plane.md)：它定义了项目、Provider Binding、Agent、Run、Evidence、Review 和 Gate 如何组成一个治理优先的客户端模型。第一个只读状态导出入口是 `devframe visual-state --runtime-dir <dir>`；也可以用 `devframe visual-state --runtime-dir <dir> --format html --output visual-state.html` 生成本地 HTML 快照，用 `devframe dashboard serve --runtime-dir <dir>` 启动本地只读 Dashboard，或用 `devframe actions --runtime-dir <dir>` 直接查看下一步队列。Dashboard 默认只绑定 loopback；如需在非 loopback 网卡上监听，请显式传入 `--allow-remote`。加上 `--paper-project <dir>` 可以把论文迭代工作区、它的 `WEB_AI_ADAPTER.yaml` provider binding、manual fallback instructions，以及带 next action 的 provider safety gate 纳入同一个控制面视图。Dashboard 的 Agent Registry 会在同一张表里显示每个 agent 的 role、scope、provider、binding health 和 status；Run Details 卡片会显示 TaskSpec/evidence 路径、当前 controller decision 和下一条安全本地命令。Dashboard 和 actions CLI 都会把当前 gate/run/decision 指引汇总成带 action id 和可复制 `--action-id` resume filter 的只读 Action Queue；actions CLI 和 `/actions.json` dashboard endpoint 还可以按 status、priority、source type、source id 或 action id 过滤，方便脚本化 triage。需要人工接续或交给 Web AI 时，可以用 `devframe actions --format markdown --output ACTION_QUEUE.md` 或 dashboard 的 `/actions.md` endpoint 导出 Markdown handoff 包。

## 已集成模块

| 路径 | 来源 | 作用 |
|---|---|---|
| `packages/agent-acceptance/` | `agent-acceptance` | 验收契约、策略和 CI preflight 模板 |
| `packages/ai-workflow-hub/` | `dev-frame-opencode/ai-workflow-hub` | 工作流编排、任务队列、证据适配器和上下文层 |
| `packages/control-plane/` | `devframe-control-plane` | 运行时协调、pipeline spec、交接工具和状态机组件 |
| `packages/test-frame/` | `test-frame` | 验证适配器、结果规范化、测试编排和小程序 E2E 包 |

这些模块是精选快照。旧 Git 历史和内部过程材料没有导入。

## 仓库结构

```text
dev-frame-system/
|-- README.md
|-- README.zh-CN.md
|-- AGENTS.md
|-- docs/
|   |-- agent-runtime/
|   |-- assets/
|   `-- module-sources.md
|-- packages/
|   |-- agent-acceptance/
|   |-- ai-workflow-hub/
|   |-- control-plane/
|   `-- test-frame/
|-- rules/
|-- schemas/
|-- scripts/
`-- templates/
    `-- runtime-bootstrap/
```

## 谁适合使用

如果你已经在用 AI coding 工具，但经常遇到这些问题，就适合使用 dev-frame-system：

- agent 还没搞清方向就开始写代码；
- 每个工具都有自己的上下文，但没人记得全局目标；
- "完成"只是 agent 说完成，而不是证据证明完成；
- 重复踩坑沉没在聊天记录里；
- 想要更强的代码审查压力，但不想再引入一个重平台。

## 许可证

本项目使用 [Apache License 2.0](LICENSE)。
