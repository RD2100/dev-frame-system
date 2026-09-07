# Agent Note：apply 面默认挂载真实宿主停止适配器

Status: implemented

[English](2026-09-08-command-goal-binding-host-stop-adapters.md) | 中文

## 问题

停止链组合把三个宿主面——项目树、已捕获后代进程、writer 释放——留作构造器注入点且没有任何真实接线：`apply` 只传必需检查存储，因此每个标准 profile 部署的链都运行在 fail-closed（`inventoryUnverified`、释放未接线）下，无论 fiber 携带什么。这些面只对手工构建适配器的测试是真实的，这正是停止链 note 遗留给宿主接线切片的缺口。

## 决策

apply 面现在通过 `resolveHostStopAdapters` 从 fiber 解析 stop 存储。已捕获进程 inventory 总是挂载，并可通过 `hostStopInventoryOf(ctx)` 访问，因此接管后代进程所有权的分发面无需深入组合即可获得捕获点。当 fiber 携带 agent、workspace 与 worktree 注册表且配置命名了 worktree 根时，树面与释放面随之挂载；注册表通过可选的 `ctx.get(name)` 读取，绝不走属性代理，因为插件没有把它们声明为注入，而拓扑敏感的属性读取会在把它们挂载在别处的 fiber 上抛错。

树面是 cwd 身份：每个会话 header cwd 规范化等于所配置 worktree 的活跃 agent，通过 `fs.realpath` 与 Windows 大小写分派比较。worktree 身份就是项目边界——其他 worktree 的 agent 永不被排空——链在其上再加自己的活跃身份 owner 过滤。

释放面同步执行完整的 owner 门：worktree 必须是拥有所配置根的 workspace 的已注册行，未绑定的行视为已完成的释放（可重复进入），已绑定的行只有在其 holder 是某个活跃树 agent 的会话 id 时才释放——外来 writer 永不释放，抛错即保留 writer。注册表的 `unbind` 是异步的，而停止原语的释放面按契约是同步的，因此经 owner 门检查的释放交给注册表执行，被拒绝的 unbind 通过日志大声上报：持久的注册表行就是释放真相，writer 保持绑定，重复停止重新进入释放并对照该行收敛。同步契约保护的是 owner 门；异步余量搭的是既有中断流程收敛路径。

## 考虑过的替代

**把注册表声明为插件注入。** 这会让插件在没有 worktree 栈的 fiber 上拒绝加载，并迫使只用停止词汇的部署挂载它们从不调用的服务。可选读取让这些面保持缺席——链保持 fail-closed——而不是让加载失败。

**让释放 await 注册表。** 停止原语的释放面按契约是同步的（"抛错必须保留 writer"）；改变它意味着重塑可靠性原语，而本切片不拥有它。带日志的异步余量在不扩宽 seam 的前提下保持持久真相诚实且可恢复。

**从会话血缘而非 cwd 派生树。** 血缘回溯需要树面并不持有的根身份（链自行补充调用 agent），而没有 worktree 身份的血缘会排空恰好从项目会话 fork 出来的外来会话。cwd 边界是宿主无需二者即可验证的事实。

## 后果

标准 profile 的 `stopChain` 部署无需额外宿主代码即获得真实的树、真实的 inventory 与真实的 writer 释放，而缺少注册表的部署与之前的 fail-closed 行为逐字节一致。已捕获进程 inventory 起始为空——目前没有任何产品分发面捕获后代子进程句柄——因此在捕获源落地之前进程 drain 仍无可排空之物；本次接线是 seam，不是喂源。异步失败的释放真相通过警告日志与重复停止呈现，而不通过 stopped 记录。
