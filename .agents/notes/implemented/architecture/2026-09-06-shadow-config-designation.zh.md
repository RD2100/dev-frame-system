# Agent Note：Shadow 的生产调用点是组合行的 config

Status: implemented

[English](2026-09-06-shadow-config-designation.md) | 中文

## 问题

`markShadow(agent)` 一直存在，却没有生产调用点：只有测试与集成探针会调用它，真正想要四个项目工具的组合必须在任何注册行之外手写宿主命令式代码，而且组合中没有任何地方声明哪个会话是 Shadow。除非调用者记得手动调用该方法，白名单始终保持惰性，这使得发布出来的 fail-closed 表现与一次意外漏标记的部署无法区分。

## 决策

生产调用点就是组合行的 config。`ShadowRouterConfig.shadowSessionId` 声明 Shadow 会话 id，路由器在最早可解析的时点自行执行真正的 `markShadow` 调用——激活时该 id 的代理已存活则立即标记（通过代理注册表做一次 init 扫描），否则在其 `agent/created` 事件时标记。会话创建仍由宿主负责：路由器绝不创建被指定的代理，从未成为存活的 id 不会安装任何东西，因此未配置或从未创建的挂载保持 fail-closed 的 `SHADOW_CALLER_FORBIDDEN` 行为。标记是幂等的，清理仍由既有的 `agent/disposed` 效果承担：被指定的代理释放后即取消标记，同 id 重建后再次标记；冷重启时指定在内存中重建，而绑定行保持持久。

## 被否决的备选方案

**扩展 project-contracts 的角色联合，加入 `shadow` 角色。** 否决：project-contracts 是 Shadow 包缝隙之外的封闭跨包类型词汇表；扩大它会把白名单的指定与另一个包的契约耦合，并让每个角色消费者都背上只有 Shadow 路由器才消费的事实。

**把调用点推迟到未来的 P23/S4 toolface 切片包。** 否决：指定缝隙属于 Shadow 白名单本身——拥有四个工具及其 fail-closed 守卫的组件——而且后续切片仍然要经过同一个服务来标记，推迟只会让生产缺口继续敞开。

**保持仅探针接线。** 否决：测试与探针手动调用 `markShadow` 证明了机制，但不是生产调用点；没有声明式的表面积，每个真实组合都会带上一个未标记的 Shadow，以及看起来像有意为之的 fail-closed 拒绝。

## 后果

组合用一个 config 字段指定 Shadow，标记随声明的 id 跨创建、重启与释放/重建保持一致；字段缺省或 id 从未出现时，fail-closed 默认不变。代价：声明的 id 是受信任的组合数据，拼写错误只会以 fail-closed 拒绝浮出——有意与默认表现一致，因此核对配置 id 成为组合评审的一部分——此外路由器在其他依赖之外新增硬注入基础树的代理注册表。
