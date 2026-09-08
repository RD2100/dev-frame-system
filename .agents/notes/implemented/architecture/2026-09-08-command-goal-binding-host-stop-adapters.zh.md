# Agent Note：apply 面默认挂载真实宿主停止适配器

Status: implemented

[English](2026-09-08-command-goal-binding-host-stop-adapters.md) | 中文

## 问题

停止链组合把三个宿主面——项目树、已捕获后代进程、writer 释放——留作构造器注入点且没有任何真实接线：`apply` 只传必需检查存储，因此每个标准 profile 部署的链都运行在 fail-closed（`inventoryUnverified`、释放未接线）下，无论 fiber 携带什么。这些面只对手工构建适配器的测试是真实的，这正是停止链 note 遗留给宿主接线切片的缺口。

## 决策

apply 面通过 `resolveHostStopAdapters` 从 fiber 解析 stop 存储。当 fiber 携带 agent、workspace 与 worktree 注册表且配置命名了 worktree 根时，树面与释放面随之挂载；注册表通过可选的 `ctx.get(name)` 读取，绝不走属性代理，因为插件没有把它们声明为注入，而拓扑敏感的属性读取会在把它们挂载在别处的 fiber 上抛错。

树面是 dispatch 血缘：接收根加上每个会话 header `parentSession` 链——沿活跃 agent 注册表回溯、有环界——能到达该根的活跃 agent。根身份在调用时传入：链自行提供调用 agent，这也是释放面的 owner 门所需的作用域。血缘就是项目边界——带显式父绑定的独立 worktree worker 属于树内，离开活跃注册表的血缘不可证明而被排除——因此同一仓库中血缘之外的会话绝不被排空。

释放面执行 owner 门并 await 注册表的异步 `unbind`：worktree 必须是拥有所配置根的 workspace 的已注册行，未绑定的行视为已完成的释放（可重复进入），已绑定的行只有在其 holder 是某个活跃树 agent 的会话 id 时才释放——外来 writer 永不释放，抛错即保留 writer。由于释放在停止原语的有界窗口内 settle，悬挂或被拒绝的释放都以 `needs_attention` 呈现且 writer 保持持有；持久的注册表行就是释放真相，重复停止重新进入释放并对照它收敛。

不挂载任何进程 inventory。捕获 seam 没有喂源：没有任何分发面记录后代进程，挂载的 inventory 只能永远为空，而空列表会被读成可证明的静止——恰恰是链必须拒绝的。在真实捕获喂源接管后代进程之前，链对缺失的面 fail-closed，与缺 jobs 注册表的拒绝同向。

## 考虑过的替代

**用带日志的拒绝同步桥接异步 unbind。** 把经检查的释放交给注册表、事后用日志记录迟到的拒绝，会在释放尚未被证明时就把停止结果报出去。对照真实注册表的受控反例展示了损害：结果落在 `stopped` 时 `unbind` promise 仍悬挂，迟到的拒绝只有一条警告——这是组合契约禁止的假成功。在有界窗口内 await 释放才是诚实形态：只有绑定被证明清空后才报 `stopped`。

**用 worktree cwd 而非会话血缘派生树。** cwd 等值过滤只对生活在所配置 worktree 里的会话构成项目边界。它把自身 cwd 是独立 worktree 的显式父绑定 worker 排除在外——同一反例证明了这个排除——保留它会让链的树背离宿主真实的 dispatch 树。经活跃注册表的血缘才是链能验证的归属事实，而接收根参数使它不会扩大成"同仓所有会话"。

**把注册表声明为插件注入。** 这会让插件在没有 worktree 栈的 fiber 上拒绝加载，并迫使只用停止词汇的部署挂载它们从不调用的服务。可选读取让这些面保持缺席——链保持 fail-closed——而不是让加载失败。

## 后果

标准 profile 的 `stopChain` 部署无需额外宿主代码即获得真实的树与真实的 writer 释放，而缺少注册表的部署与之前的 fail-closed 行为逐字节一致。在捕获喂源落地并挂载 inventory 面之前，进程 drain 无可排空之物；这种缺席是大声的，不是安静的。永不 settle 的释放仍有界返回：悬挂超时具名 `writer:release`，writer 保持持有，重复停止重新进入。
