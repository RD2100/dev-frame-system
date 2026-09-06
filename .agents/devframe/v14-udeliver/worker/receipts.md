# B 线 Worker 回执（实体落盘版）

车道修正依据：总控 2026-09-06 指令——B 线 Worker 一律显式 `{provider:'huoshan-2', model:'glm-5.3-flash'}`；三层证据分列（①请求参数=显式派发值 ②宿主标签=Worker 运行时上下文自报 ③实际响应=持久化 request/header+context 逐字载荷，仅③可判 provider 实证；自报 unknown 只记"未证实"）。执行命令列=派发该 Worker 的 workflow 工具调用名；退出码=workflow 运行终态（completed=正常返回）。

## W1 profile-probe（真实本机探针 · 证据类别=真实本机探针报告，与车道证据分列）

- 执行命令：workflow `bline-min-slices-1` · agent(label=profile-probe)（parallel 屏障）
- 退出码：workflow completed（2/2 agents 返回）
- ①请求参数：`{provider:'huoshan-2', model:'glm-5.3-flash'}`
- ②宿主标签：Worker 运行时上下文自报 model=`glm-5.3-flash`；provider 未在上下文标注 → **provider 未证实（②层）**
- ③实际响应：**已实证**——宿主持久化会话 C:\Users\25313\.dsh\sessions\--D-dsh-devframe--\<sessionId>\session.jsonl.zstd 首个 request/header **seq=13**：`config.provider="huoshan-2"`、`config.model="glm-5.3-flash"`（逐字）。会话 id→Worker 对应：W1/W2=176475b1、2cfaefe4（bline-min-slices-1）；W3/W4=d5f3c838、75eecf47（bline-min-slices-2）
- 结果：报告实体文件 `worker/profile-probe.md`（178 行）。要点：web 组合证实未挂载 agentBindings（provider 包 session-identity 全仓零 yml 引用）与 v14 三包；apps/cli dependencies 四包全缺（devDependencies 不参与 examples 解析）；command-goal-binding 缺 tsconfig paths 映射（会挂 validateSourcePlaneResolution）；`!!js process.cwd()` 先例=base patch L218；**数组内 `!!js` 无仓库先例（未证实）**——shipped 行因此把 authorizedRoots 留缺省（fail-closed），checks[].cwd 的 `!!js` 用 `--dump-config` 真实探针实证。

## W2 at1-recon（真实本机探针 · 证据类别=真实本机探针报告）

- 执行命令：workflow `bline-min-slices-1` · agent(label=at1-recon)（parallel 屏障）
- 退出码：workflow completed（2/2 agents 返回）
- ①请求参数：`{provider:'huoshan-2', model:'glm-5.3-flash'}`
- ②宿主标签：自报 model=`glm-5.3-flash`；provider 未标注 → **未证实（②层）**
- ③实际响应：**已实证**（同 W1 口径）——本 Worker 会话 request/header seq=13 provider=huoshan-2/model=glm-5.3-flash 逐字
- 结果：`worker/at1-recon.md`。AT1×11：覆盖 5（01/02/04/06/07）/部分 4（03/05/09/10）/缺口 2（08 repairLimit 全树零实现；11 真实任务效用零证据）。Top 缺口：①真实凭据链断（B4 推进）②shipped 未挂 v14 包（B1 推进）③AT1-08+AT1-10 余面。

## W3 at2-recon（真实本机探针 · 证据类别=真实本机探针报告）

- 执行命令：workflow `bline-min-slices-2` · agent(label=at2-recon)
- 退出码：workflow completed（2/2 agents 返回）
- ①请求参数：`{provider:'huoshan-2', model:'glm-5.3-flash'}`
- ②宿主标签：自报 model=`glm-5.3-flash`；provider 未标注 → **未证实（②层）**
- ③实际响应：**已实证**（同 W1 口径）——本 Worker 会话 request/header seq=13 provider=huoshan-2/model=glm-5.3-flash 逐字
- 结果：`worker/at2-recon.md`。AT2×8：覆盖 7 / 部分 1（AT2-05 双存储后端分句；sqlite 后端未参数化挂载）/缺口 0。全部条目验收态保持 not_run；新增三层证据（S6 verdict、markShadow host-designation、集成 profile 投递旅程）均标注机制 B/keyless 不充当全范围验收。8 条全停在包级+机制 B，shipped 挂载是横切阻塞（本 B1 收口）。

## W4 at3-at4-recon（真实本机探针 · 证据类别=真实本机探针报告）

- 执行命令：workflow `bline-min-slices-2` · agent(label=at3-at4-recon)
- 退出码：workflow completed（2/2 agents 返回）
- ①请求参数：`{provider:'huoshan-2', model:'glm-5.3-flash'}`
- ②宿主标签：自报 model=`glm-5.3-flash`；provider 未标注 → **未证实（②层）**
- ③实际响应：**已实证**（同 W1 口径）——本 Worker 会话 request/header seq=13 provider=huoshan-2/model=glm-5.3-flash 逐字
- 结果：`worker/at3-at4-recon.md`。权威编号更正：AT2=Shadow、AT3=Obsidian 记忆×9、AT4=可靠性×8。17 条：覆盖 10 / 部分 5（AT3-07、AT4-01/04/06/07）/缺口 2（AT4-05 请求预算记账面全缺；AT4-08 兼容读取/回滚无 AT 语义绑定）。树内增量闭合 p22 旧缺口：AT4-02/03 真实路径旅程 spec、AT4-04 stop 缝、AT3-01 agent 侧再水化、AT4-01 跨重启 resume 缝。

## 组长自查补充

- 设计实体文件：`lead/design.md`（B1 挂载设计+真实链 12 站表+B4/B5 方法）。
- 全部四份 Worker 报告均只写 `worker/` 域，主树与其他路径零写入（各报告"车道回执"自证 + 本组长 glob 复核仅 5 文件在 v14-udeliver/ 下）。
