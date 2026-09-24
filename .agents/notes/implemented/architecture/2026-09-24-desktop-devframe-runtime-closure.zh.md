# Agent Note: Desktop 生产运行时携带 DevFrame 闭包

Status: implemented

[English](2026-09-24-desktop-devframe-runtime-closure.md) | 中文

## 问题

通用 dsh 发布族排除 `packages/experimental`，但 Desktop 产品需要交付 DevFrame 专家、记忆、Shadow、团队和 Schedule 页面。开发环境中的 workspace 链接会让这些行出现，打包后的 Desktop 却没有 profile bundle、专家包数据或已安装的包路径。

## 决策

Desktop 打包在通用 dsh 发布族之后增加产品专用的 experimental 闭包。闭包从 DevFrame profile、Shadow 浏览器入口和 Desktop Host 声明的 experimental 依赖开始，递归跟踪本地 dependencies、optionalDependencies 和 peerDependencies。package-set 描述强制包含 DevFrame profile，生成的运行时 manifest 激活 `dsh-base`、`dsh-web-app` 和 `dsh-experimental-devframe-profile`。

Desktop Host overlay 提供 Shadow bridge 和浏览器入口，挂载 project-controller 的任务/集成/交付 face 与 agent-evidence，并把 Expert Team 的源码目录改为已安装的 `expert-pack-paper` 与 `expert-pack-dev` 包目录。experimental 名称不再进入发布 CLI 与 Host 的 runtime dependency surface；Desktop 生成的运行时 manifest 提供本地闭包。通用 dsh 发布族保持不变，继续为非 Desktop 消费者排除 experimental 包。

## 备选方案

**让 Desktop tarball 排除 experimental 包。** 放弃，因为打包后的 profile 无法解析其行和专家数据，文档所述 Desktop 能力会缺失。

**把全部 experimental 包加入通用 dsh 发布族。** 放弃，因为这会改变所有消费者的正式发布边界；Desktop 需要产品专用闭包。

**继续在 Host overlay 使用源码目录。** 放弃，因为准备后的运行时只有已安装包目录，不包含仓库的 `packages/experimental` 树。

## 后果

Desktop preparation 会打包 DevFrame 的传递闭包，缺少本地包时立即失败。生产 profile 现在激活 DevFrame 服务、UI 行和 project workflow face，Expert Team 从已安装的包路径读取数据。项目 face 要等部署提供真实 workspace 和 Shadow binding 才会运行。Desktop 包体积会增大，仍需完整执行 package preparation；通用 dsh 包消费者不会得到 experimental 闭包。

## 测试

Desktop package-set、profile 和 package-target 测试通过；Desktop 与 Desktop Host TypeScript 构建通过；Cordis 配置检查通过。通用 dsh release verifier 报告 247 个成员均为 `0.1.6-alpha.1`，vendor verifier 接受独立命名的 mobile-pairing 包，DevFrame preflight 也成功打包两个专家数据包。release 子进程助手会解析 Windows `pnpm.cmd` shim，使嵌套 pack 命令与 Unix 使用同一门禁。完整 Windows package preparation 仍需在打包运行时上完成一次 Electron 运行。
