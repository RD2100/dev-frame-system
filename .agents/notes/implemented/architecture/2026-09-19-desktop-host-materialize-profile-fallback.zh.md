# Agent Note：desktop-host 走本仓已物化的 profile fallback 启动，而非上游的运行期 PluginPackages hook

Status: implemented

[English](2026-09-19-desktop-host-materialize-profile-fallback.md) | 中文

## 问题

`apps/desktop-host/src/index.ts` 是从上游逐字照抄的，但本仓尚未移植上游的 `profile-resolution` 模块。文件依赖的两个导入名在 `@deepseek-ai/dsh-app-boot` 中并不存在：

- `createProfileResolutionGeneration`（文件顶部导入）
- `PluginPackages`（在 `boot` prepare 回调里挂载的 Cordis 服务插件）

第三个硬前提同样缺失：`src/index.ts` 通过 `loadOverlayPatches` 解析 `../config/desktop.cordis.patch.yml`，该函数在文件缺失时直接 throw，但整个 `apps/desktop-host/config/` 目录当时根本不存在。

逐字移植上游 resolver 在运行期被硬阻断：`resolver.ts` 顶部 `require('node-addon-require-builtin')`。该原生 addon 虽是 `apps/cli` 的合法依赖，但不在 `app-boot` 的解析作用域内（根 `node_modules` 顶层无此包，`app-boot` 声明依赖里也没有），且仓库 `allowBuilds` 列表明确禁止其原生编译。类型侧可解析（vendored `loader` 已导出 loader 类型），所以逐字移植能过 typecheck，但首次 boot 就会 `MODULE_NOT_FOUND`。

## 决策

Option B——不动 `packages/boot/app-boot`，把 desktop-host 改写成本仓已有的物化装载路径：

- 删掉两个未移植导入（`createProfileResolutionGeneration`、`PluginPackages`）及其全部用法点（`createProfileResolutionGeneration({...})` 调用与 `hostCtx.plugin(PluginPackages, { generation })`）。
- 在 `boot(...)` 之前调用已导出的 `healProfilesModuleFallback({ installAnchor, profile })`。它把共享依赖闭合物化到 `$DSH_HOME/profiles/node_modules`，把 bundle-only 链接物化到 profile 的 `node_modules`（即 Electron 的 `projectDir`），使 Loader 能按 `ctx.baseUrl` 解析裸 bundle 插件名。调用顺序与原 resolution hook 一致：都在 `boot` 之前。
- 从上游逐字恢复 `apps/desktop-host/config/desktop.cordis.patch.yml`。所有 `insert` 行用的都是 bare workspace 包名（`@deepseek-ai/dsh-host-directory-picker-native`、`@deepseek-ai/dsh-client-ui-directory-picker-native`），两者都已在 `apps/desktop-host/package.json` dependencies 里，无需按本仓路径改写。

boot prepare 回调在删掉唯一的 `await`（`hostCtx.plugin(...)`）后，去掉 `async` 修饰；`boot` 的 `prepare` 参数本就接受 `(ctx) => Promise<void> | void`。

## 备选方案

**逐字移植上游 `profile-resolution`（Option A）。** 三条理由否决：(1) 运行期硬阻断——`node-addon-require-builtin` 不在 `app-boot` 解析作用域且仓库禁止其编译，移植只会把 P0 从"导入失配"换成"原生模块不可解析"；(2) 边界风险——上游已把 `healProfilesModuleFallback` 分叉为返回 generation 表而非物化到磁盘，对齐它会冲击当前全绿的 `profile.spec.ts` / `app-boot.spec.ts` 测试面；(3) 无下游消费者——全仓 grep 显示 `PluginPackages` / `ctx.pluginPackages.packageOf` 只有 desktop-host 文件这一个调用方。

## 后果

收益：desktop-host 走本仓已有的 symlink 物化路径启动，与 CLI profile launcher 一直在用的同一条路径一致。`$DSH_HOME/profiles/node_modules` 下的 symlink 是 launcher 既有副作用，不是新引入的磁盘模式。

延后（记录在此，本次不做）：上游选运行期 hook 是为了在打包可执行文件里避免磁盘写。本仓 desktop-host 是 Electron `spawn` 的普通 Node 子进程（`isPackagedExecutable()` 为 false），所以物化在今天是正确的。未来若真正打包发布使 `~/.dsh` 只读、bundle-only 插件解析失败，再把 `node-addon-require-builtin` 作为 `native/` 下第二个原生 addon 引入并逐字移植 4 个 resolver 文件。

## overlay yml 的本地偏离

恢复的 `desktop.cordis.patch.yml` 删去了上游 preemptive disable 的两行：

- `id: open-in-app / disabled: true`
- `id: ui-open-in-app / disabled: true`

本仓 base 组合不含这两个 entry（这两个包本仓不发）。对目标 id 在 base 里缺席的 disabled 行，`composeEntries` 会警告 "entry not found"，污染 overlay 的干净组合。这两行作为对逐字上游副本的刻意本地偏离被删去，遵循 P0.2 既定原则（内部引用按本仓实际改写）。其余六条 disabled 行（`web-startup`、`webserver`、`web-runtime`、`client-hmr`、`directory-picker`、`connection`）的目标 entry 在本地 base 组合中存在。

## Handler 对齐（后续已完成）

逐字照抄的 `index.ts` 曾带着两处本仓客户端包已演进后的接口分叉，由 `tsc --noEmit` 暴露，与 P0 的导入失配无关。两处现已对齐到本仓真实 API：

- `assetHandler` / `remoteStreamHandler` 返回的 `requestBodyMode: () => 'buffered'`——已删除。本仓 `ConnectionFetchHandler`（packages/client/connection 的 rpc.ts:198）只声明 `fetch(request)`，其消费方（rpc-host.ts:123-129）从不读取 `requestBodyMode`。
- `assetHandler` 里的 `ctx.clientModules.fetchBundle(request)`——已删除。本仓 `ClientModuleRegistry`（packages/client/modules:585-588）在构造函数里自己把 `/plugins` 注册为 webServer prefix route（`ctx.webServer.register({ kind: 'prefix', path: '/plugins', handler: this.serveBundle })`）；上游的 `fetchBundle(request)` 是旧架构的手动 byte-pipe 转发，已被该 webServer 路由取代。asset handler 现在只负责 dist 静态文件；代码注释记录了这个委托。
