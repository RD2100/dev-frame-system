# B5 — AT 验收矩阵 36 条逐条对账（汇总表）

对账基准：本树 codex/v14-udeliver-lead（=main@908f627101 + compos 7c21ed0fc2 + goalstore cd676781c3 及后续；当前含 B 线收口提交）。四分片 Worker 报告：`worker/at1-recon.md`（AT1×11）、`worker/at2-recon.md`（AT2×8）、`worker/at3-at4-recon.md`（AT3×9+AT4×8，权威编号 AT2=Shadow/AT3=Memory/AT4=可靠性）。每行判定三值=证据覆盖（覆盖/部分/缺口），**≠验收通过：全部 AT* 验收态仍 not_run**。硬规则执行：机制 B/keyless 证据一律标注范围；S2-S7 通过不提升为全范围验收；同提交同环境同命令通过结果复用不重跑。

## AT1×11（目标绑定与宿主命令面）

| ID | 判定 | 关键证据（详见 at1-recon.md） | 缺口→处置 |
| --- | --- | --- | --- |
| AT1-01 | 覆盖 | 包级 `team_task_update` 具名探针闭合 p22 缺口 | fixture 录制归 snapshots 属主 |
| AT1-02 | 覆盖 | 包级三用例（由部分升级） | 无 |
| AT1-03 | 部分 | 缝级全锚；真实模型旅程缺（原 S1 keyless BLOCKED） | **B4 已翻面**：huoshan 显式路由真实调用 PASS（`b4-evidence.md`，request/header seq=10）；组合级真实旅程随 B1 链 S2/S3 站 |
| AT1-04 | 覆盖 | 缝级 | 无 |
| AT1-05 | 部分 | 4/6 具名+schema 收口；变体 5 untracked 边界差如实登记 | 补变体 5 用例（包内小切片） |
| AT1-06 | 覆盖 | 缝级+宿主命令面（compos 波 /devframe-start/resume REAL composition 测试） | 无 |
| AT1-07 | 覆盖 | 包级/装配层 | **shipped 挂载已落地**（2380aae9a3；boot-evidence.md：dump 152 行零重复+真实 boot 探针过） |
| AT1-08 | 缺口 | repairLimit 全树零实现零测试（grep 复核仅文档命中） | 需实现小切片（devframe 属主，Config 化 repairLimit+四断言） |
| AT1-09 | 部分 | 分立锚点齐含 durable 重启；旅程场景缺 | 旅程场景随 snapshots 录制 |
| AT1-10 | 部分 | /devframe-start/resume/goal-complete 已实现+REAL composition 测试（由缺失升级） | 余 stop/abandon/中断注入/用量保持面 |
| AT1-11 | 缺口→推进中 | 真实任务效用零证据（keyless 不可替代） | **B4 PASS 打通真实调用面；B1 链 S2-S7 站产出真实任务效用证据（进行中）** |

## AT2×8（Shadow 路由）

| ID | 判定 | 关键证据（详见 at2-recon.md） | 缺口→处置 |
| --- | --- | --- | --- |
| AT2-01 | 覆盖（包级+组合级机制 B） | lifecycle.spec + S6 verdict + 集成 L1 | 产出面真实旅程→**B1 链 S11 站（进行中）**；fixture 录制归 snapshots 属主 |
| AT2-02 | 覆盖 | whitelist 五类拒面+s6-markshadow-scope+host-designation | open 级越权根具名用例（一行级）；滥用探测随 B1 链 |
| AT2-03 | 覆盖（包级） | provisioning 5 用例+行级冷恢复+S6 cold bonus | fixture 录制即可 |
| AT2-04 | 覆盖（包级，平台变体 skipIf） | aliases 5 条目+平台门控不宣称机制 | POSIX 分支对应平台验收时确认 |
| AT2-05 | 部分 | 投递两写/恢复/crash-window 齐；**双存储后端分句零锚点**（套件单挂 StorageJson） | 小切片：helpers 加 storageBackend 变体（json+sqlite）跑 delivery-recovery+s6-crash-window |
| AT2-06 | 覆盖 | delivery-limits 3 用例+S6 冲突面 | fixture 录制即可 |
| AT2-07 | 覆盖 | stop-isolation+s6-stop-settlement（p22 后新增） | 组合级真实 owned job 变体随 B2 站 |
| AT2-08 | 覆盖 | status 分页/received≠completed/零副作用/observedAt | queued 态读出断言（一行级）+UI 状态集映射归产品波 |

## AT3×9（Obsidian 记忆）

| ID | 判定 | 关键证据（详见 at3-at4-recon.md） | 缺口→处置 |
| --- | --- | --- | --- |
| AT3-01 | 覆盖 | recall+receipt-log+agent-rehydration（真实 Vault+真实派发） | fixture 录制归 snapshots 属主；**B1 链 S12 站补 shipped 面冷恢复（进行中）** |
| AT3-02 | 覆盖 | recall UTF-8/上限截断 6 用例 | 无 |
| AT3-03 | 覆盖 | append 并发/幂等/冲突 + S7 真实 already_exists | 无 |
| AT3-04 | 覆盖 | path-safety 7 用例 | 非 Windows 语义平台验收时确认 |
| AT3-05 | 覆盖 | trust 数据身份+权限拒面 | 无逐字工具调用探针（非阻断） |
| AT3-06 | 覆盖 | trust 推断/矛盾/陈旧/supersession | 无 |
| AT3-07 | 部分 | failure 三态+cold-restore+S7 | 任务级联动（controller 旅程+memory_unavailable 警告）→小切片；**B1 链 S12 站补真实写/读（进行中）** |
| AT3-08 | 覆盖 | failure 畸形/秘密筛查/有界重试 | 无 |
| AT3-09 | 覆盖 | append 外部变更如实报告+cold-restore | 无 |

## AT4×8（可靠性）

| ID | 判定 | 关键证据（详见 at3-at4-recon.md） | 缺口→处置 |
| --- | --- | --- | --- |
| AT4-01 | 部分 | agent-reliability+goal-binding+file-store 跨实例重启+compos 重启 resume | 单一旅程组装→S5 骨架补两分支注入小切片；**B1 链 S8-S10 站即真实跨进程重启+显式 resume（进行中）** |
| AT4-02 | 覆盖（包级真实路径旅程） | at4-02 journey（真实子进程写标记+context 终止） | 真实 harness 进程 kill 注入未做（机制 B 范围如实标注） |
| AT4-03 | 覆盖（包级真实进程树） | at4-03 journey（真实子+孙心跳树） | 无 |
| AT4-04 | 部分 | stop.spec 核心缝四断言 | needs_attention 态替代写入者探测一条用例 |
| AT4-05 | 缺口 | 全树零实现（README:112 自证 budget 只限任务态） | P06 记账小切片（Config 化+四断言），源码级缺失 |
| AT4-06 | 部分 | at4-06 准入关闭半边收口 | 在途任务有界取消半边待总控裁定语义后补用例 |
| AT4-07 | 部分 | 刷成功/失败闩锁+events JSONL 往返 | 真实磁盘层故障注入+脱敏断言小切片 |
| AT4-08 | 缺口（AT 层） | 无 AT4-08 语义绑定（core repair/版本机制是契机） | 绑定 dsh-session 属主+三场景具名锚定 |

## 汇总与翻转清单

- 判定分布（36）：覆盖 24 / 部分 9（AT1-03/05/09/10、AT2-05、AT3-07、AT4-01/04/06/07 中计入 9 个部分位）/ 缺口 3（AT1-08、AT4-05、AT4-08）。**全部验收态 not_run 不变。**
- 四态翻转清单（B 线交付引起的行级变更）：
  1. B1 源码行已有→**profile 行翻绿**（shipped 挂载四包，boot-evidence.md 实证）。
  2. B4：S1 场景 keyless BLOCKED→**真实凭据 PASS**（运行态真实证据，b4-evidence.md）。
  3. AT1-11 / AT1-03 / AT2-01/02 / AT3-07 / AT4-01 的"真实任务效用/shipped 面"缺口由 **B1 链逐站证据推进**（链结算后补链至本表）。
  4. p22 矩阵的"not_run+旧缺口"中已被树内增量覆盖的：AT1-01/02/06/07、AT2 全组（+S6/P21-S/集成 L1 新证据）、AT3-01、AT4-02/03/04——均已按上表链接，不重跑。
- 剩余小切片清单（按依赖排序）：①AT2-05 双后端参数化（纯测试改动）②AT1-05 变体 5 用例 ③AT1-08 repairLimit 实现（devframe 属主）④AT4-05 请求预算记账（P06，源码级）⑤AT4-08 语义绑定（dsh-session 属主）⑥AT4-06 在途取消（待总控裁定）⑦AT4-04/07 各一条用例 ⑧fixture 录制批次（snapshots 属主，29 篇草案）。
