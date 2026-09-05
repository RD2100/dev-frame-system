---
description: "面向 Web 客户端的组合冒烟：在 jsdom 测试台的真槽位、渲染器、会话与语言栈上挂载一个功能插件，然后断言装配后的表面。"
kind: "package-library"
---

# @deepseek-ai/dsh-composition-smoke

[English](README.md) | 中文

## 概述

`dsh-composition-smoke` 围绕一个功能插件装配生产客户端栈。`mountComposition()` 创建[客户端测试运行时](../client-runtime/README.zh.md)测试台——真实的 Cordis `Context`、渲染器持有的 `SlotRegistry`、UI 渲染器，以及架在类型化 Controller 替身之上的 `ui-session` 适配器——允许测试用例提供插件所需的其余服务，并把插件挂载到一条活纤程上。冒烟套件随后断言装配后的表面：槽位账目注册、语言注册表，以及渲染出的 DOM。它不属于产品插件图（无 `dsh.client`）；消费方仅在 devDependencies 中依赖它。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [延伸阅读](#further-exploration)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

本包是对测试台的一次性装配封装：挂载一个功能插件，驱动组合后的表面，并沿一条轴完成清理——不复制任何生产逻辑的第二份实现。

### 挂载一个组合

`mountComposition(plugin, options)` 一次调用完成测试台装配与插件挂载。`provide` 回调在装配与挂载之间运行，因此挂载前的服务预检能看到每一个注入服务：在 `runtime.ctx` 上提供插件所需的其余服务，通过 `TestRemote` 脚本化 Remote 命名空间，固定语言，或释放功能要替换的测试台默认项（在提供自己的根工作区钩子的插件之前调用 `releaseWorkspaceSource()`）。返回的运行时就是[客户端测试运行时](../client-runtime/README.zh.md)测试台——通过它声明槽位、渲染并清理：

```text
const runtime = await mountComposition({ inject, apply }, {
  provide: (bench) => {
    bench.releaseWorkspaceSource()
    // provide('locale', ...), new TestRemote(bench.ctx, { ... })
  },
})
await runtime.declare({ 'feature-slot': {} })
const view = runtime.renderSlot('feature-slot', owner)
await runtime.dispose()
```

### 会出什么问题

- **声明的服务未被提供** —— 挂载预检会带缺失名称大声失败；在 `options.provide` 中提供它们。
- **根钩子提供者盖在测试台默认项之上** —— 先在 `provide` 中调用 `releaseWorkspaceSource()`；测试台在装配时、任何插件纤程启动之前安装它的工作区钩子。

-----
<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现内部 —— 点击展开</summary>

本节解释装配器的设计；可观察行为已在[使用本包](#use-this-package)中完整覆盖。

### 设计

本包不复制任何生产或测试台逻辑：它把组合所需的调用顺序——测试台装配、用例私有的服务供给、挂载的大声失败服务预检、再到活纤程——收拢在一个函数之后，其返回值就是已有文档的测试台。

### 源码映射

| 文件 | 职责 |
|---|---|
| [`src/index.ts`](src/index.ts) | `mountComposition` 装配与 `provide` 定制点 |
| — | 不发布运行时不变式伴生入口；本测试支持包不拥有生产事件流或可变数据，装配后的表面由消费它的冒烟套件检验。 |

### 生命周期

`mountComposition` 等待测试台装配完成，运行 `provide` 回调，再通过测试台的 act 包装等待插件纤程。清理仍归测试台：`runtime.dispose()` 卸载视图、处置功能纤程、释放注册并清除持久化状态，且幂等。

</details>

-----
<a id="further-exploration"></a>
## 延伸阅读

- [client-runtime](../client-runtime/README.zh.md) —— 本包装配的测试台及其暴露的替身。
- [测试策略](../../../docs/testing.zh.md) —— 装配冒烟所补充的覆盖层级。
- [test-support 组地图](../README.zh.md) —— 同组测试设施与支持包。

-----
<a id="model-experience"></a>
## 模型体验

无，本包是浏览器侧测试基础设施；这里没有任何内容到达模型请求。

#### KV Cache 效应

无；本包既不组装也不发送任何提供方请求。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>

- **仅限 Vitest 与 jsdom** —— 组合运行在与客户端测试运行时相同的进程内测试台上；线路承载、真实 Host 应答与浏览器级行为仍留在浏览器快照通道。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者工作上下文 —— 点击展开</summary>

无。

</details>
