# Agent Note: Desktop 能力管理与 Schedule 控件

Status: implemented

[English](2026-09-24-desktop-skill-mcp-schedule-management.md) | 中文

## 问题

Desktop 设置页只展示能力与调度状态，没有完整的用户变更路径。Skill 无法安装或启停，MCP 条目从浏览器看是内存状态，Schedule 任务中心也停留在只读视图。

## 决定

Host 的 plugin-inventory Remote 负责用户 Skill 文件与 MCP 配置。Skill 以校验后的 `SKILL.md` 写入 `$DSH_HOME/skills`，启用状态使用官方 invocation frontmatter 字段表示。MCP 条目从 `$DSH_HOME/storages/mcp-servers.json` 恢复，通过串行的原子替换写回，并在投影中隐藏 `env` 与 `headers`。设置页能力标签页调用这些 Remote 完成安装、启用、停用、卸载，以及添加、编辑、测试、移除；部署拥有的 profile 和预设组合仍保持只读。

Schedule 的变更归 Schedule Host Remote。设置任务中心按 Session 调用暂停、恢复、立即运行和删除，并在每次结果后重新读取 Host 投影；头部目录继续只读展示。

## 备选方案

**保留浏览器本地能力状态。** 否决：它会与 Loader 状态分叉，并在重连或重启后消失。

**把 MCP 凭据返回浏览器再测试。** 否决：脱敏投影无法安全重建私有传输值；现在由 Host 用自己的私有配置测试已有条目。

**让头部目录拥有 Schedule 变更。** 否决：设置任务中心有足够空间承载操作状态和错误，头部保持紧凑的只读视图。

## 结果

用户 Skill 与 MCP 变更可跨 Host 重启保留，并通过同一份 Loader 投影显示。MCP 配置文件属于 DSH home 内的本地持久状态，Remote 响应不会返回密钥。冷重启 Electron 验收仍需在真实打包运行时执行；Host、Client、Schedule 与 Typert 的定向检查覆盖已交付的接缝。

## 测试

定向 Vitest 覆盖 Host Skill 生命周期、设置页 Skill/MCP 控件与错误脱敏、浏览器插件注册和 Schedule 任务操作。Host、Schedule、API Remote 与 UI Schedule TypeScript 构建通过，Typert 产物可重新生成。设置包构建仍会报告本次变更范围外既有的 `ui-approval` 与 `ui-chat` SessionStore 声明错误。
