---
description: 能力中心插件独立安装与 DSH 升级兼容性工作的交接记录。
---

# 能力中心插件兼容性交接——2026-09-26

[English](capability-center-plugin-compatibility-handoff-2026-09-26.md) | 中文

## 目的

本文记录能力中心插件包尚待完成的工作。用户明确了边界：交付可独立安装、并能随着 DSH 更新继续使用的插件；不修复或扩展 DSH Desktop/Host 应用主体或核心模块加载器。本文是后续 Agent 接手这项工作的入口。

## 当前状态

四标签能力中心由独立插件提供内容：[client-ui-expert-team](../../packages/experimental/client-ui-expert-team/README.zh.md)拥有“专家”页外壳，[ui-settings-plugin-inventory](../../packages/client/ui-settings-plugin-inventory/README.zh.md)贡献“技能”和“连接器”，[client-ui-project-memory](../../packages/experimental/client-ui-project-memory/README.zh.md)贡献“记忆库”。数据和操作仍由各自插件负责。

Host 侧的 [expert-team 包](../../packages/experimental/expert-team/README.zh.md)接受已安装的数据包名称，并从自身安装依赖闭包中解析，因此使用包名时不再依赖调用方的当前目录。

当前工作树包含这些插件包、配套双语文档、能力中心 Agent Note、锁文件和实验包工作区约束的未提交修改。此次修改不涉及 Desktop、Host 应用、客户端核心加载器或 Desktop 分发文件。编辑前先检查当前差异；不要重置或清理共享工作树。

## 证据与限制

| 检查 | 结果 |
|---|---|
| `pnpm exec tsc -b tsconfig.client.json --pretty false` | 当前客户端源码树类型检查通过。 |
| inventory、client-ui-expert-team、client-ui-project-memory bundle | 三个客户端插件的 bundle 命令均成功。Host expert-team 包没有 `bundle` 脚本。 |
| 本地包归档 | `pnpm pack` 为三个客户端插件、Host expert-team 和两个已提供的专家数据包生成了归档。这只证明本地打包成功。 |
| expert-team 包引用探测 | 在仓库环境中解析 `@deepseek-ai/dsh-experimental-expert-pack-paper` 返回了对应的工作区包目录；尚未在仓库外的干净使用方验证。 |
| 指定双语配对检查和 `git diff --check` | 七组文档配对通过；差异检查只报告 `LibraryCard.tsx` 的 CRLF 转 LF 提示。 |
| `scripts/check-workspace-constraints.ts` | 被既有 Desktop/Host 发布元数据，以及 expert-pack-dev、expert-pack-paper、project-controller 的 `files` 策略错误阻断。这些错误不代表插件归档无法生成。 |

打包元数据中的 peer 范围目前由 `workspace:^` 转换为 `^0.1.6-alpha.1`。本地打包不能证明插件能兼容 DSH 后续升级；本轮也没有发布到 registry 或在干净 profile 中安装运行。较早的 Agent Note 记录过 66 个 UI 定向测试通过，但该证据早于当前工作树，不能作为本轮验收；本次收尾没有运行测试。

## 留给下一位 Agent 的工作

1. 基于公开 Remote 与 slot API 明确兼容契约，并记录插件支持的 DSH 版本。用户希望插件在 DSH 更新后继续可用；没有证据时，不要承诺跨越公开 API 破坏性变更仍兼容。
2. 在没有仓库工作区链接的干净使用方 profile 中安装本地插件归档，验证依赖解析、四个标签页和 Host Remote 调用；不要修改 DSH 应用或加载器代码。
3. 如果可用，在当前 DSH 版本及一个较新 DSH 版本上检查同一插件集合。记录确切包版本与行为；兼容性调整限定在插件包和发布依赖元数据内。
4. 审核工作区约束改动。当前规则允许任何设置了 `publishConfig.access: public` 的 experimental 包取消 private；在保留插件独立发布能力的同时，缩小或说明该规则范围。
5. 下一位 Agent 审核当前差异后，再运行所改插件行为的定向测试和打包检查。不要用 Desktop 重建或 Host 补丁代替插件使用方验证。

较早的 [Desktop 产品交付交接](desktop-product-delivery.zh.md)记录了更广的 Desktop 集成工作；其中修改应用依赖的内容不属于本次后续工作的范围。[能力中心 Agent Note](../../.agents/notes/implemented/feature/2026-09-25-capability-center.zh.md)记录了功能的所有权决定。

## 交接要求

只接手插件兼容性工作。保留共享工作树中的现有修改，不编辑 `apps/desktop`、`apps/desktop-host` 和 `packages/client/modules`，也不发布包或创建发行版。验收结果应包含干净使用方安装和所选 DSH 版本的兼容性证据。
