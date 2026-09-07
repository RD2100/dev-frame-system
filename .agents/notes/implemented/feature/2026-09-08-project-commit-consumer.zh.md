# Agent Note: Host-controlled Worker artifact commits through project_commit

Status: implemented

[English](2026-09-08-project-commit-consumer.md) | 中文

## 问题

项目 Worker 在其链接检出中写入任务工件，却无法提交它们：沙箱把 Worker shell 挡在 anchor 仓库的 `.git/worktrees/*` 之外（写入以 EACCES 失败），而 `project_deliver` 要求干净且已提交的工作树。[宿主 worktree 提交 Service](../architecture/2026-09-08-host-worktree-commit.zh.md) 解决了 Git 边界问题，但没有任何东西把它暴露给模型，而天真的暴露会重新引入该 Service 要消除的风险：dirty 集读回会执行检出控制的 clean filter，dirty 集证明不了任务归属，Worker 提供的 HEAD、holder 或路径值都是可伪造输入。

## 决策

交付消费者再注册一个角色工具 `project_commit`（`taskId`、显式相对 `paths`、可选单行 `message`），与 `project_deliver`、`project_review` 处于同一条 per-task 串行链。宿主从真实绑定与一次可信观察推导请求的每个字段；Worker shell 永远不运行 `git commit`。注册时探测合并后的 commit Service，加载的 provider 构建落后即在 apply 时 fail-loud。

### 授权是部署的路径范围

`commitPathsByTask`——交付消费者新增的可选 Config 映射，apply 时校验并冻结——登记每个任务可提交的工件路径。未登记范围的任务拒绝；请求路径越出范围即拒绝并列出越界项；不存在或非文件路径在跑任何其他东西之前先在文件系统上拒绝。范围即事实源：消费者不做任何 status 或 dirty 扫描，因为普通 `git status` 会执行检出控制的 clean filter，而 dirty 集分不清 Worker 产出与任何触碰该路径的东西。请求 ⊆ 范围，因此多轮提交合法。

### 一次只读观察，落在 owner 上

消费者运行的唯一 Git 命令是对 owner 工作区目录（由 registry 行解析，绝不经过 Worker 检出可自行改写的 `.git` 指针）执行 `rev-parse --verify --end-of-options refs/heads/<branch>`。分支引用在 anchor 中，位于 Worker 写边界之外。trim 后的输出必须是完整 40/64 位十六进制对象 id，并原样作为 `expectedHead` 携带；Service 在其固定的链接 gitdir 内复核分支与期望 HEAD，竞态或被重定向的检出都会以 Service 拒绝收场。

### 静默是证据，复核两次，绝不是强制

后台作业注册表每次调用解析一次（`ctx.get('jobs')`）；没有它的组合直接拒绝而不是假设安静。调用者任何 `running` 或 `stopping` 作业都拒绝提交，且该闸在 HEAD 观察之后再跑一次，飞行中出现的新作业仍被拒绝。工具绝不杀作业。per-task 串行链只互斥 commit/deliver/review 族——作业闸是瞬时证据，不是操作系统锁；与第二次复核竞速的写入者会经 Service 自身验证或交付闸浮现。

### 不确定性被报告，不被分类

提交后非清洁的树是成功结果，其文本把剩余变更称为未核实；交付仍要求完全清洁的工作树。在那里报错会因 expected HEAD 前移毒化重试。

## 已考虑的替代方案

- **以 dirty 集交叉核对作为授权**（初稿把请求路径与 `git status` 输出求等）：否决——相等证明不了归属，读回本身会执行检出控制的程序；Config 范围取代它。
- **经 Worker 检出观察 HEAD**：否决——检出拥有自己的 `.git` 指针并可重定向它；owner 侧引用读的锚点在 Worker 写边界之外。
- **把 jobs 服务注入交付消费者**：否决——每个挂载交付消费者的组合都得挂载 jobs 注册表；每次解析加显式拒绝让缺席保持响亮，而不强迫该依赖。
- **提交前杀掉调用者的非终态作业**：否决——摧毁用户工作；拒绝加重试保住它。
- **为提交工具开第二个 loader 命名空间**：否决——独立的串行链会分叉提交必须与交付共享的静默次序。

## 后果

Worker 恰好提交宿主登记的范围，同时工作树仍归其写入；伪造身份、伪造 HEAD、重定向检出与越界路径全部拒绝。代价：scope 路径上的用户编辑与 Worker 编辑按路径不可区分——Config 范围界定爆炸半径；Service 暂存前完成的写入会进入提交（仍受范围限定），暂存与 clean 读之间完成的写入落入未核实面；没有 jobs 实现的组合完全无法提交。本切片不附带 recorded-session 快照场景：A2 候选链的真实全跑是其验收证据，快照推迟到该组合定型之后。

## 验证

- `node node_modules/vitest/vitest.mjs run packages/experimental/project-controller/tests/commit-consumer.spec.ts`（22 例）覆盖真实角色授权（伪造参数惰性、非指派 Worker、非 developing 任务、authority 翻转守卫）、范围面（缺失、越界、不存在、目录、junction 包含逃逸、语法边界）、静默（缺注册表、running、stopping、观察后晚到作业）、owner 观察（stale-HEAD 干扰、worktree 行消失），以及两条具名反例：Worker `.git` 指针重定向到另一注册工作树以 `does not belong` 拒绝，观察与 Service 调用之间的干扰提交以 `expected HEAD` 拒绝。
- `pnpm run gen-tool-catalog` 再生 `project_commit` 的 schema；catalog 入口的 registry 替身携带 commit seam，因为注册会拒绝没有它的 provider。
