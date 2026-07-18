<p align="center">
  <img src="docs/assets/devframe-system-banner.svg" alt="devframe-system：受治理的编码产品" width="100%" />
</p>

<h3 align="center">一个面向重度软件工程工作的受治理编码 CLI。`devframe code` 是主产品，其余控制平面能力服务于它。</h3>

<p align="center">
  <a href="README.md">English</a> | 简体中文
</p>

<p align="center">
  <a href="#它是什么">它是什么</a> |
  <a href="#从这里开始">从这里开始</a> |
  <a href="#主产品路径">主产品路径</a> |
  <a href="#二线与高级能力">二线与高级能力</a>
</p>

```text
devframe code "<goal>"   # 主产品：准备一次受治理的编码运行
devframe code workers    # 检查本地 worker 是否可用
devframe code status     # 查看已准备运行
devframe code execute    # 执行已准备运行
devframe dashboard serve # 可选：打开控制平面视图

# 二线 / 高阶能力
devframe client
devframe go <project> <goal>
rdgoal <project> <goal>
```

**请先把 DevFrame 理解为一个受治理的编码产品。`devframe code` 是日常主循环；dashboard 只是可选的只读诊断视图，rdgoal、RD-Code 客户端、MCP/ACP、paper workflow 都是围绕这条主线的支撑层或高级层。**

> **当前状态：** 本仓库在当前开发上下文中已经通过本地 release gate，
> 但这不等于对外正式发布完成。确切边界见
> [release-readiness.md](docs/status/release-readiness.md)。

## 它是什么

DevFrame 现在最应该被理解成：

> 一个让工程师把“准备任务、检查边界、执行、恢复、审查”做得更稳的编码 CLI。

它不是先让你学会一整套控制平面，再开始写代码。
它也不是让你先决定 MCP、ACP、Web AI、T3 bridge 这些高级能力怎么接入。

默认路径应该很短：

1. 进入仓库
2. 运行 `devframe code`
3. 准备一次有边界的编码任务
4. 检查 worker 命令
5. 决定是否执行
6. 之后用 `status` / `execute` 继续

Web AI 可以作为外部大脑提供方向和审查，
但日常主入口仍然应该是本地编码工具本身。

## 从这里开始

如果你只想先走主产品路径，请先这样用：

```powershell
git clone https://github.com/RD2100/dev-frame-system.git
cd dev-frame-system
python -m pip install -e ".\packages\control-plane[dev]" -e ".\packages\ai-workflow-hub[dev]"
.\scripts\verify-release.ps1

devframe code
devframe code workers
devframe code status
```

先把这条主循环跑通，再去学习二线能力。

## 主产品路径

`devframe code` 是主产品入口。

它的职责是：

- 接收一个编码目标
- 生成一次有边界的运行
- 明确显示会调用什么 worker
- 把真正执行这一步保留为显式动作
- 让你稍后通过 `status` / `execute` 继续，而不是每次重新开始

典型用法：

```powershell
devframe code "Build the MVP"
devframe code workers
devframe code "Fix the branch" --changed --agents auto --preview
devframe code status --runtime-dir "$env:TEMP\devframe-code"
devframe code execute --runtime-dir "$env:TEMP\devframe-code"
```

如果你只记住一件事，就记住这条链路。

## 二线与高级能力

下面这些能力很重要，但不该先学：

- `devframe dashboard serve`
  控制平面视图，用于检查 run、action、session、gate。
- `rdgoal`
  更深的编排与治理层。
- `devframe go`
  并发 coding-agent 分片入口，适合更复杂任务。
- `devframe client`
  RD-Code / T3 相关的客户端与 bridge 能力。
- `devframe web-ai ...`
  Web AI、MCP、review、task intake 等高级能力。

正确顺序是：

1. 先把 `devframe code` 用顺
2. 再引入 dashboard 做观察
3. 需要时再启用 `go`、`rdgoal`、`client`、`web-ai`

如果你已经进入控制平面层，常用的是这些入口：

```powershell
devframe visual-state --runtime-dir <dir>
devframe dashboard serve --runtime-dir <dir>
devframe actions --runtime-dir <dir>
```

公开只读 surface 仍然包括：

- `/actions.json`
- `/actions.md`
- `--action-id`
- `--allow-remote`

## 快速启动

检查公开发布面：

```powershell
python -m pip install -e ".\packages\control-plane[dev]" -e ".\packages\ai-workflow-hub[dev]"
.\scripts\verify-public-snapshot.ps1
.\scripts\verify-release.ps1
```

初始化另一个项目：

```powershell
.\templates\runtime-bootstrap\bootstrap.ps1 `
  -ProjectName "my-project" `
  -ProjectRoot "D:\my-project"
```

绑定浏览器 AI 会话（仅当你真的需要外部大脑路径时）：

```text
/bindChrome https://chatgpt.com/...
```

高级编排入口：

```powershell
rdgoal "D:\my-project" "Build the MVP" --digest
devframe go "D:\my-project" "Build the MVP" --agents 3 --target src
```

## 仓库结构

```text
dev-frame-system/
|-- README.md
|-- README.zh-CN.md
|-- AGENTS.md
|-- docs/
|-- packages/
|-- rules/
|-- schemas/
|-- scripts/
`-- templates/
```

## 适合谁

如果你已经在高频使用 AI 编码工具，但反复遇到这些问题，这个项目才适合你：

- agent 很快开始写代码，但目标边界不清楚
- 不同工具各有上下文，没有统一的运行与审查视图
- “完成”更多是一句回答，不是一套证据
- 任务中断之后很难继续
- 你想保留控制权，而不是把执行权完全交出去

## 许可证

项目使用 [Apache License 2.0](LICENSE)。
