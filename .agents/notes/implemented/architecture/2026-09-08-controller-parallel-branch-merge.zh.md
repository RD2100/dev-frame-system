# Agent Note：总控集成以真实合并承接并行已审查分支

Status: implemented

[English](2026-09-08-controller-parallel-branch-merge.md) | 中文

## 问题

[总控 Git 集成恢复决策](2026-09-07-controller-git-integration-recovery.zh.md)只接受快进变更：`merge-base --is-ancestor` 会拒绝第二个任务——其已审查提交与已集成的兄弟任务从同一 base 分出。两个并行开发的 Worker 因此永远无法双双集成——第二个被永久拒绝，仅有的出路是把开发串行化或改写其中一侧。

## 决策

确切源契约不变，模式改为显式。`IntegrationGitRequest` 携带 `mode: 'fast-forward' | 'merge'`，并持久化到集成意图（存储域版本 4 增加模式与实际合并结果 head；更早版本在打开时拒绝）。只读关系探针把两个 head 分类为 identical、fast-forward、already-integrated、diverged，集成消费者显式选择模式：分叉的已审查源——两个 Worker 从同一 base 分支时的正常形态——集成为真实合并提交，其父提交为观察到的目标 HEAD 与确切已审查源；其余关系一律保留快进路径及其拒绝。并行场景的两次集成走同一准入：包含两个 taskId 的 Goal 绑定、各自独立的交付、验证与评审，总控仍是唯一写入者。

合并边界隔离其环境。变更命令以显式配置束运行（`merge.ff=false`、`commit.gpgsign=false`、`core.hooksPath=/dev/null`）并带 `--no-verify`，其子进程把 `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` 重定向到空文件以剥离全局与系统 Git 配置，检查阶段拒绝本地配置定义了自定义 merge driver 或外部 filter 的目标。树内 `.gitattributes` 引用了任何可达配置都未定义的机制时是惰性的：只有 Git 内建合并参与运行。作者身份来自宿主持有的目标检出本地配置。applied 回执记录观察到的合并 head，绝不让源提交冒充它（快进的 head 就是源提交，这是如实的观察）。

失败状态保留其名称。冲突合并以 HEAD 不动停止，且只有当 `MERGE_HEAD` 与未合并索引条目同时证实合并状态时才报告 `conflicted`——取消或外部写入造成的脏目标加 HEAD 不动保持 `ambiguous`。章鱼提交（多于两父）永远不满足 applied 形态，保持 `ambiguous`。协调区分两个阶段：prepared 意图但 Git 已应用的，从观察到的两父合并修复记录；applied 回执钉住确切的 applied head，因此目标被 amend 成同两父不同提交时拒绝报告 applied。

## 已考虑的替代方案

**把第二个任务串行化在 rebase 之后。** 让第二个 Worker rebase 到前进后的目标再重新交付，会把并行开发变成串行重确认，并改写已审查提交；合并模式按交付原样集成已审查提交。

**在 Git 层内自动选择模式。** 隐藏默认值掩盖了实际运行的路径；关系探针让选择显式，且检查为所选模式重新验证关系。

**拒绝一切带全局 filter 配置的仓库。** 在合并子进程剥离全局与系统配置即可隔离机器级配置面，而不会让装有 LFS 的宿主不可用；本地配置面由宿主持有，定义了可执行进程条目时直接拒绝。

## 后果

真实 Git 套件覆盖：干净兄弟合并的精确两父顺序与最终内容、带合并状态证据的显式冲突、章鱼提交与脏目标的歧义、模式误配拒绝、无关历史、本地 driver 拒绝（快进面完好）、以及无可达配置的 attribute 选择机制。总控套件经真实 Loader 驱动两个兄弟任务——先快进后合并，无 rebase 无重新交付——并持久化模式与 applied head；冷恢复可协调 prepared 合并意图，被 amend 的同两父目标拒绝报告 applied。

快进路径保留其既审面貌，包括其对钩子与 filter 的既有暴露；只有合并路径携带隔离配置束。存储域版本 4 在打开时拒绝版本 3 状态，这是部署激活决策而非迁移。
