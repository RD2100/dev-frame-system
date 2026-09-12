# Agent Note: shadow 路由契约独立成 Service Definition（`dsh-experimental-shadow-routing`）

Status: implemented

[English](2026-09-12-shadow-routing-seam.md) | 中文

## Problem

shadow 家族的词汇原来住在实现包里。`dsh-experimental-shadow-router` 打包了四个因不同原因而变化的关注点：路由词汇（品牌 id、绑定/投递记录、`SHADOW_*` 错误码、config 类型）、具体服务（持久绑定存储、两次写入的投递、重放台账）、模型可见工具白名单，以及存储域。家族每个成员——转发投递的桥与拥有宿主 Remote 的控制器——为了标注一个 `ShadowDeliveryRecord` 或 `ctx.shadowRouter` 的类型而导入 Provider 包，于是架构所称的 Consumer 在编译期依赖了 Service Provider。投递交接也没有缝：桥只能靠轮询路由器索引来发现一条 `received` 投递，重启后恢复收敛把 queued 行落到 `received` 的动作在下一次轮询前不可见，任何未来 Consumer 都会继承同样的节奏耦合。

## Decision

新建一个 Service Definition 包持有 shadow 路由缝；Provider 实现它；Consumer 不再需要 Provider：

- **`@deepseek-ai/dsh-experimental-shadow-routing`（Service Definition）**——抽象 `ShadowRouter` 类（具体服务的全部公开方法迁为抽象成员）、`ctx.shadowRouter` Context 扩增，以及全部词汇：带边界校验的 `ShadowRequestId`/`ShadowMessageId`/`AcceptanceHash` 品牌工厂、绑定/投递/请求记录类型及其状态机、请求/回执形态、`ShadowRouterError` 及其 `SHADOW_*` 码联合（整体迁入——品牌工厂要抛它，若把基类留在 Provider 下面会倒转依赖方向）。它同时声明 typed 事件 `shadow/delivery-received`，并拥有带包含的 `emitDeliveryReceived` 派发，对应 [workflow 缝](../../../../packages/workflow/workflow/README.zh.md)的观察型事件模式。没有工具、没有存储、也没有 config：`ShadowRouterConfig` 类型留在 Provider，因为 config 目录门禁要求插件自己的 config 类型住在自己的包里。
- **`dsh-experimental-shadow-router`（Service Provider）**——具体 `ShadowRouter` 继承缝类；保留存储域与 schema、provisioning 副作用、重放台账与四个项目工具。`markDeliveryReceived`——发送路径与 `recoverDeliveries` 收敛中每次 queued→received 转移都经过的唯一内部助手——在持久写入提交后对每次真实转移发出一次事件；冷恢复时磁盘上已是 `received` 的行是重载而非转移，不发出事件。Provider 再导出迁出的词汇，使组合层与 profile 测试保持单一导入根；家族各 src 的导入直接指向定义包。
- **Consumer**——shadow-bridge、shadow-controller 与客户端 Shadow 入口针对定义包编译：其 src 导入指向缝本身，Provider 只按角色被导入——测试里的 Loader 插件值与组合行。桥在同轮完成事件化：从 `shadow/delivery-received` 触发转发，以挂载时与 loader 结算后的对账轮询加安全网定时器兜住事件窗口错过的工作。

## Alternatives considered

**只拆契约（类型与 id，不带抽象类）。** 否决：ctx 键与方法契约是缝的承重部分——把类留在 Provider 会让 `ctx.shadowRouter` 继续由实现包标注类型，下一个 Provider 更替（或第二个 Provider）会再次把所有 Consumer 耦合回去。

**保留桥轮询，只加事件。** 否决：没有转发监听者的事件是一条死通道，而恢复收敛落到 `received` 的行在下一次轮询前仍然不可见；桥在同一轮改为以事件为主通道，由对账轮询与安全网定时器兜住事件窗口错过的工作。

**词汇留在 router，让 Consumer 从那里导入。** 否决：这正是本轮要修复的现状——错误码联合与品牌工厂应与它们所校验的词同住，词汇提供方不能依赖词汇消费方。

## Consequences

买到的：shadow 词汇有了唯一属主；桥/控制器/入口的 src 导入直接指向缝包；投递交接在转移点可观察（`shadow/delivery-received`），而不是在下一次轮询；抽象类把每个实现欠下的语义写成文档（操作链串行化、两次写入投递、提交后 emit、重载不 emit）。Provider 公开面保持不变——同样的默认导出、同样的具名导出、同样的 ctx 键——所以 Loader、模块映射与组合行都不需要修改。

付出的：多一个包；router 的 index 再导出定义包，同一些类型可从两个包命名（定义包是属主，再导出服务于组合层与 profile 测试）；`ShadowRouter` 现在同时命名抽象缝与实现它的具体子类（子类保留 Provider 的名字与默认导出，Loader 与模块映射不变）；且发出的事件必须保持只观察——修改路由器状态的监听者会破坏包含助手写明的提交后无副作用契约。
