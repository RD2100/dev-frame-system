# Agent Note：apply 面默认挂载真实宿主停止适配器

Status: implemented

[English](2026-09-08-command-goal-binding-host-stop-adapters.md) | 中文

## 问题

停止链组合把三个宿主面——项目树、已捕获后代进程、writer 释放——留作构造器注入点且没有任何真实接线：`apply` 只传必需检查存储，因此每个标准 profile 部署的链都运行在 fail-closed（`inventoryUnverified`、释放未接线）下，无论 fiber 携带什么。这些面只对手工构建适配器的测试是真实的，这正是停止链 note 遗留给宿主接线切片的缺口。停止链同样没有 resume 侧的准入：owner 被排空并围栏后没有任何东西重新打开它，被释放的 writer 也没有任何东西重新获取。

## 决策

apply 面通过 `resolveHostStopAdapters` 从 fiber 解析 stop 存储。fiber 携带 agent 注册表时树面随之挂载；释放面还需要配置的 worktree 根与 workspace、worktree 注册表；注册表通过可选的 `ctx.get(name)` 读取，绝不走属性代理，因为插件没有把它们声明为注入，而拓扑敏感的属性读取会在把它们挂载在别处的 fiber 上抛错。

树面是 dispatch 血缘：接收根加上每个会话 header `parentSession` 链——沿活跃 agent 注册表回溯、有环界——能到达该根的活跃 agent。根身份在调用时传入：链自行提供调用 agent，这也是释放面的 owner 门所需的作用域。血缘就是项目边界——带显式父绑定的独立 worktree worker 属于树内，离开活跃注册表的血缘不可证明而被排除——因此同一仓库中血缘之外的会话绝不被排空。

配置的 workspace id 选择 workspace，规范 worktree 路径选择其中的目标行，因此 linked worktree 无须等于 workspace 锚点。释放面执行 owner 门并 await 注册表的异步 `unbind`：worktree 必须是拥有所配置根的 workspace 的已注册行，未绑定的行视为已完成的释放（可重复进入），已绑定的行只有在其 holder 是某个活跃树 agent 的会话 id 时才释放——外来 writer 永不释放，抛错即保留 writer。由于释放在停止原语的有界窗口内 settle，悬挂或被拒绝的释放都以 `needs_attention` 呈现且 writer 保持持有；持久的注册表行就是释放真相，重复停止重新进入释放并对照它收敛。

进程面消费宿主 subagent runtime 与[终端宿主所有权](2026-09-08-terminal-host-ownership.zh.md)所述的终端所有权目录。每个活跃血缘 owner 最多产生一个 subagent 与一个 terminal 排空条目；目录覆盖全部隔离终端实例，并在没有实例时仍阻止未来 spawn。`prepareResumeResources` 保留目录批量预检，重新验证原活跃 owner 树，并在提交前准备 subagent owner。树、目录或 owner 排空 generation 发生变化时，准入保持关闭。

释放面有其 resume 对应面：`createHostWriterAcquire` 在同样的 workspace 与行门下重新获取单写绑定，并自带接收根必须活跃的门；注册表的 `bind` 接受未绑定的行或同一 holder，同时拒绝挤走外来 writer。经授权的 resume 在重开资源之前先重取 writer，因此外来持有的 worktree 使 resume 失败而不偷锁，持久注册表行保持为真相。宿主携带项目控制器时，资源提交还会在原生 Goal 续行激活前打开其已停止的请求准入；准备阶段拒绝未完成停止，提交阶段复核捕获的生命周期。

冷启动后的 stop 将匹配的投影绑定恢复到空进程存储，不恢复 native Goal 的运行；其他 Goal 的投影不能满足当前绑定要求。

## 考虑过的替代

**用带日志的拒绝同步桥接异步 unbind。** 把经检查的释放交给注册表、事后用日志记录迟到的拒绝，会在释放尚未被证明时就把停止结果报出去。对照真实注册表的受控反例展示了损害：结果落在 `stopped` 时 `unbind` promise 仍悬挂，迟到的拒绝只有一条警告——这是组合契约禁止的假成功。在有界窗口内 await 释放才是诚实形态：只有绑定被证明清空后才报 `stopped`。

**用 worktree cwd 而非会话血缘派生树。** cwd 等值过滤只对生活在所配置 worktree 里的会话构成项目边界。它把自身 cwd 是独立 worktree 的显式父绑定 worker 排除在外——同一反例证明了这个排除——保留它会让链的树背离宿主真实的 dispatch 树。经活跃注册表的血缘才是链能验证的归属事实，而接收根参数使它不会扩大成"同仓所有会话"。

**把注册表声明为插件注入。** 这会让插件在没有 worktree 栈的 fiber 上拒绝加载，并迫使只用停止词汇的部署挂载它们从不调用的服务。可选读取让这些面保持缺席——链保持 fail-closed——而不是让加载失败。

## 后果

标准 profile 的 `stopChain` 部署经有界窗口排空真实拥有的资源，经授权的 resume 重取 writer 并重开准入而不扩大任一围栏。缺少注册表的部署与之前的 fail-closed 行为逐字节一致。永不 settle 的释放仍有界返回：悬挂超时具名 `writer:release`，writer 保持持有，重复停止对照持久行重新进入释放。
