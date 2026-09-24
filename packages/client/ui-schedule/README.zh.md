---
description: "Web Schedule 任务中心与头部目录说明，包含活动提醒的浏览器控制。"
kind: "package-reference"
---

# @deepseek-ai/dsh-client-ui-schedule

[English](README.md) | 中文

## 概述

本包在 Web 会话头部渲染 Schedule 目录，并在设置中提供任务中心。任务中心读取全部 Session projection，通过生成的 Schedule Remote 暂停、恢复、立即运行或删除任务；头部目录仍是紧凑的只读呈现。浏览器派生的时间标签不会写入持久状态。随附 Web bundle 默认禁用该插件，只有显式 Schedule overlay 才会同时启用 Host Schedule 服务与此客户端 row。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [进一步探索](#further-exploration)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

在需要显示提醒的 Web Session 启动前启用 Schedule overlay：

```sh
dsh web --patch apps/cli/config/examples/schedule/cordis.yml
```

随附 Web graph 已通过 disabled 的 `ui-schedule` row 解析 `@deepseek-ai/dsh-client-ui-schedule`；overlay 会把该 row 与 `@deepseek-ai/dsh-schedule` 一起启用。只有 Session 已成功打开且 projection 至少包含一条活动记录时，触发器才会出现。打开目录后，逾期行在前，未来行再按目标时间排序；完全并列时保留 projection 的创建顺序。

### 阅读和关闭目录

每一行显示可完整换行的 prompt、独立的「等待中」或「已逾期」状态、本地化的「单次」或重复间隔可整除的最大完整单位、浏览器本地目标时间，以及按浏览器时钟派生的相对时间。间隔绝不舍入，三项元数据会按行换行，不会裁剪合法的大数值。通过 portal 挂到 body 的弹层目标宽度为 336px；空间足够时与触发按钮左边缘对齐，触发器靠近视口右侧时向左避让并保留 16px 视口边距，最大宽度为视口宽度减 32px。弹层会在需要时纵向滚动，且不显示 Schedule id、原始 UTC 值、详情或操作控件。

只有原生触发按钮进入 Tab 顺序。Enter 与 Space 使用按钮的正常激活行为；焦点仍在触发器或目录内时，Escape 会关闭弹层并把焦点交还触发器；在外部按下指针也会关闭。若 live 更新移除最后一条记录，组件会关闭并卸载，但不会把焦点移到另一个会话头部动作。Session 打开失败时，即使存在暂定的缓存 projection，也会隐藏触发器。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

浏览器插件以顺序 10 向 `conversation.session.header.actions` 贡献 `schedule-catalog`，并向设置贡献 `schedule` 分区。任务中心发送按 Session 寻址的 Remote 调用，并通过正常的 Session 更新路径重新读取 projection；操作失败只显示在当前页面。头部组件仍读取 `openState` 与 `useProjection('schedule')`，只读弹层不会改变持久记录。

### 源码地图

| 文件 | 职责 |
|---|---|
| [`src/client/index.ts`](src/client/index.ts) | 浏览器入口：注册 locale 并贡献 Session 头部 slot |
| [`src/client/ScheduleCatalogAction.tsx`](src/client/ScheduleCatalogAction.tsx) | 可见性、排序、格式化、弹层与键盘行为 |
| [`src/client/locales.ts`](src/client/locales.ts) | 中英文目录文案 |
| [`src/index.ts`](src/index.ts) | 空的 Host apply，使 Loader 可以寻址该可选浏览器功能 |
| — | 不发布运行时不变量伴生入口；这个只读客户端目录不拥有可变的跨插件状态。 |

[持久 Web Schedule Agent Note](../../../.agents/notes/implemented/feature/2026-08-05-durable-web-schedule.zh.md)拥有活动 projection 与 opt-in 呈现边界；本包拥有目录的时间与无障碍行为。

</details>

-----

<a id="further-exploration"></a>
## 进一步探索

当目录本身不够用时阅读以下页面。它们从浏览器呈现逐步进入持久 Schedule 状态与共享 projection 传输。

- [Schedule 包](../../schedule/schedule/README.zh.md)——创建、列出、取消并交付这里显示的提醒。
- [Schedule 子系统](../../../docs/subsystems/schedule.zh.md)——持久记录、转换与交付语义。
- [会话投影子系统](../../../docs/subsystems/session-projection.zh.md)——本包读取的完整值传输。
- [客户端包映射](../README.zh.md)——相邻的浏览器 UI 包。

-----

<a id="model-experience"></a>
## 模型体验

无，因为本包只为人类渲染已经完成的客户端 projection，从不改变 prompt、消息、schema、流或工具结果。

#### KV Cache 影响

无；本包从不组装或发送 provider 请求。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>


这些限制界定当前 Schedule 目录。它们是当前包约束，不是提醒服务对比或任务积压。

- **仅含活动记录**——终结性的 delete 与 dispatch 转换会移除对应行；普通 transcript 仍是唯一的提醒交付历史。
- **浏览器派生时间**——本地时间与相对时间标签使用查看方浏览器当前的 locale、时区与时钟。它们是呈现值，不是持久 Schedule 事实。
- **头部目录只读**——创建仍由 Schedule 工具负责；暂停、恢复、立即运行和删除在设置任务中心提供。
- **要求 Session 打开成功**——打开失败时，即使存在暂定缓存值也会隐藏，因为严格 Session 回放仍是权威。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

无。

</details>
