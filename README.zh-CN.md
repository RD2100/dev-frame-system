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
/rdinit                 # 初始化外部大脑操作层
/bindChrome <url>       # 绑定 GPT Web、DeepSeek、豆包或其他网页 AI 会话
```

**核心问题不是“再做一套治理框架”。真正的问题是：如何用尽量低的成本和最简单的流程，提高代码质量，并让研发方向不漂移？**

dev-frame-system 的答案是：把网页 AI 会话变成软件研发的**外部大脑**。网页 AI 负责保存产品方向、工程取舍、任务边界、证据、审查结论和经验记忆；IDE、CLI、浏览器、脚本、测试框架以及不同厂商的 coding agent 都是可替换的执行器。

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
- **证据审查**：用 ExecutionReport、证据索引、审查门禁和负面夹具防止“假完成”。
- **可复用引导**：用 PowerShell bootstrap 把同一套操作层部署到其他项目。
- **外部大脑绑定**：用 `/bindChrome` 把稳定的网页 AI 会话绑定到当前项目。
- **总控编排**：用 `rdgoal` 协调多个项目本地 workflow，记录 controller 决策、rollback snapshot、dispatch packet 和最终报告。

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

绑定网页 AI 会话：

```text
/bindChrome https://chatgpt.com/...
```

安装 control-plane CLI，并用 `rdgoal` 路由一个项目：

```powershell
cd .\packages\control-plane
pip install -e .
devframe doctor
cd ..\..
.\scripts\verify-release.ps1
devframe rdgoal "D:\my-project" "Build the MVP" --digest
```

如果要跑完整的 dispatch -> worker -> digest 闭环：

```powershell
devframe rdgoal "D:\my-project" "Build the MVP" --runtime-dir D:\tmp\devframe-runtime
devframe rdgoal worker "<packet-dir>" --runtime-dir D:\tmp\devframe-runtime
devframe rdgoal digest --runtime-dir D:\tmp\devframe-runtime
```

`rdgoal worker` 只有在报告状态为 `passed` 或 `completed` 时返回退出码 `0`。`blocked`、`failed` 或未知状态都会返回非零，避免自动化把未执行或失败误判为成功。

## 工作流程

1. 在网页 AI 中明确目标、风险、范围和验收标准。
2. 把任务转成有边界的 TaskSpec。
3. 分发给 Codex、Claude Code、CLI 脚本或浏览器自动化执行。
4. 收集 ExecutionReport 和验证输出。
5. 只有证据通过审查门禁，才接受这次工作。
6. 把可复用经验沉淀回项目记忆。

## 两个技能入口

| 技能 | 用途 | 结果 |
|---|---|---|
| `/rdinit` | 给仓库初始化 dev-frame-system 操作层 | `AGENTS.md`、规则、schemas、工具策略、能力清单和运行时文档 |
| `/bindChrome <url>` | 把网页 AI 会话绑定到当前项目 | 一个稳定的外部大脑会话，连接本地项目上下文 |

提供商可以替换，契约不能替换。GPT Web 是默认参考路径，因为它容易获得，也适合长上下文协调。如果另一个网页 AI 不能稳定保存项目上下文、协调任务并审查证据，就更适合作为二级审查器，而不是主外部大脑。

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
- “完成”只是 agent 说完成，而不是证据证明完成；
- 重复踩坑沉没在聊天记录里；
- 想要更强的代码审查压力，但不想再引入一个重平台。

## 许可证

本项目使用 [Apache License 2.0](LICENSE)。
