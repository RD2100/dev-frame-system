---
description: P05 sourceFingerprint 重算引擎设计（AT1-05 变体 5"审查后改未跟踪文件"的依据面）：指纹构成/规范化算法/错误码族/输入输出形状/平台不变性、未跟踪文件与热路径两条边界登记、引擎接入点裁定请求及 2026-09-06 总控裁定（案 B 独立 verify 面先行，已落地；案 A 定性为案 B 的前移使用，留 controller 波）。
---

# P05 sourceFingerprint 重算引擎设计（纯计算引擎波）

- 基点：`p/fprecompute` @ `526e773b23`（=main HEAD）。范围：`packages/experimental/devframe/src/source-fingerprint.ts`（新）、`packages/experimental/devframe/src/index.ts`（出口一行）、`tests/source-fingerprint.spec.ts`（新）、本文档。**不改** `controller/goal-binding.ts`、`events.ts`、`session-journal.ts`、schemas、agent-evidence/agent-hierarchy/session-identity（裁定未批，见文末裁定请求）。
- 权威断言面：[anchor-matrix AT1-05](anchor-matrix.md)（"审查后改未跟踪文件"行，现登记为 GAP）与 [p05harden-design.md 残余缺口](p05harden-design.md)（"审查后改未跟踪文件（真实指纹重算）"仍为 GAP）。本波交付该变体的**依据面**：一个可从 GoalBindingController 域调用的纯计算引擎——给定 worktree 目录，产出可与 `ProjectWorkBinding.sourceFingerprint` 比对的品牌化指纹。比对面已按 2026-09-06 总控裁定随案 B 落地（见裁定节）；集成面/controller 波待后续裁定。
- 总控骨架采纳：最小真实引擎 = HEAD 提交哈希 + tracked 文件状态规范化哈希；fail-loud 结构化错误；性能边界 = 显式 verify 调用入口、不进热路径。

## 指纹构成与规范化算法

指纹值 = `SourceFingerprint` 品牌字符串 `dsh-source-fp-v1-<headCommit>-<stateHash>`（复用 `shared/types.ts` 的 `SourceFingerprint` 品牌与工厂形态；`events.ts` 的 `sourceFingerprintSchema` 是 trimmedString 品牌化，非空即可通过，无形状耦合）：

1. **headCommit**：`git -C <dir> rev-parse --verify --quiet HEAD` 的 stdout（40/64 位十六进制；SHA-1 与 SHA-256 仓库均接受，入库前做 hex 形状校验，形状不符 → `GIT_FAILED`）。
2. **stateHash**：`git -C <dir> ls-files -s -z --full-name -- :/` 的**原始字节流**（每条记录 `<6位八进制mode> SP <小写十六进制blob> SP <stage 0-3> TAB <repo 相对 path> NUL`）直接过 sha256，不做任何文本解码。`:/` pathspec 把枚举范围钉在仓库根（嵌套输入目录与仓库根产出同一字节流，实测逐字节相等），`--full-name` 钉死 repo 相对路径输出。
3. 指纹值 = sha256 无关的拼接（head 与 stateHash 均为定长 hex，`-` 分隔无歧义），未再哈希一次——两个组成部分本身就是规范化哈希。

**规范化算法的确定性论证**（选 `ls-files -s -z` 原始字节而非自造序列化的理由）：

- 该字节流是 git 自己的规范化序列化：mode/ stage 定宽、blob id 小写 hex、NUL 分帧——文件名禁止含 NUL，故分帧无歧义；`-z` 关闭 `core.quotePath` 的 C 转义，非 ASCII 路径按原始字节输出。哈希原始字节 = 零解码 = 零编码方差（UTF-8/GBK 文件名、组合字符均逐字节稳定）。
- 不受 mtime 影响：`ls-files -s` 读 **index**（暂存对象库状态），不 stat worktree；index 缓存的 stat 信息过期与否都只影响 `status` 类命令，不影响本输出。
- 不受 CRLF/行尾影响：index 里的 blob 是 `git add` 时经 clean/`text` 过滤后的对象；worktree 行尾改写不重 staged 就不进 index。
- 不受路径分隔符影响：index path 按仓库相对 POSIX 斜杠存储，是 git 内部表示，无平台转换面。
- 不受 env/locale 影响：stdout 形状由 `-s -z` 完全固定（无 color、无 pager——非 tty）；`LC_ALL=C` 只为错误路径 stderr 消息分类而设，不触碰成功路径输出。
- stage 字段忠实保留：合并冲突时 stage 1/2/3 记录出现即指纹变化（冲突态是真实源状态）；mode 100644/100755/120000/160000（含 submodule gitlink）同面。
- 放弃 `git write-tree`（树对象即规范化哈希）的理由：它向对象库**写对象**，违背只读计算缝；放弃 `git status --porcelain` 的理由：含 untracked/重命名检测且形状更宽、更慢；放弃自扫 worktree 文件哈希的理由：mtime/行尾/权限全部方差化（退回手写规范化，恰是本设计删掉的东西）。

## 错误码族（新族，fail-loud，绝不静默回退）

`SourceFingerprintError extends Error`（结构对齐 `GoalBindingError` 的 message+code 形态），`code: SourceFingerprintErrorCode`：

| 码 | 触发 | 分类依据（实测 git 2.53，win32；分类法与平台无关） |
| --- | --- | --- |
| `SOURCE_FINGERPRINT_INVALID_REQUEST` | 输入形状非法：空/相对 worktree 路径、空 git 命令名 | 引擎前置校验，不触 git |
| `SOURCE_FINGERPRINT_NOT_A_WORKTREE` | 目录不存在或非目录；不在任何 git 仓库内；bare 仓库（`--is-inside-work-tree` 返回 `false`） | `fs.stat` 前置探针 + `rev-parse --is-inside-work-tree` 退出码/stdout |
| `SOURCE_FINGERPRINT_NO_COMMIT` | 仓库内但 unborn HEAD（零提交） | 已过 worktree 门后 `rev-parse --verify --quiet HEAD` 退出码 **1**（git 文档化的 `--quiet --verify` 语义；退出码分类，不匹配消息） |
| `SOURCE_FINGERPRINT_GIT_UNAVAILABLE` | git 可执行文件不存在（ENOENT）或不可执行（EACCES） | execFile spawn 级错误的 string error code |
| `SOURCE_FINGERPRINT_GIT_FAILED` | 其余一切 git 失败：非零退出且未落入上两类（如 index 损坏）、输出超过收集上限、异常退出 | 非"not a git repository" stderr / maxBuffer 错误码 / 兜底臂 |

分类流水线（三次只读子进程调用，全部 `-C <dir>` 定位，不依赖进程 cwd）：

1. `fs.stat` 前置：不存在/非目录 → `NOT_A_WORKTREE`。
2. `rev-parse --is-inside-work-tree`（env 钉 `LC_ALL=C`）：spawn 失败 → `GIT_UNAVAILABLE`；stdout `false` → `NOT_A_WORKTREE`（bare 仓库或 `.git` 目录内）；非零且 stderr 含 `not a git repository`（大小写不敏感；locale 已钉死使该消息跨平台稳定）→ `NOT_A_WORKTREE`；其余非零 → `GIT_FAILED`。
3. `rev-parse --verify --quiet HEAD`：退出 0 → headCommit；退出 1 → `NO_COMMIT`；其余 → `GIT_FAILED`。
4. `ls-files -s -z --full-name -- :/`（`encoding: 'buffer'`）：成功 → 原始字节进哈希并数 NUL 得 `trackedEntryCount`；spawn 失败 → `GIT_UNAVAILABLE`；其余（含 `ERR_CHILD_PROCESS_STDIO_MAXBUFFER`）→ `GIT_FAILED`，消息聚合 stdout/stderr。

 unborn HEAD 语义裁定：**明确错误码而非静默语义**。无 commit 即无"HEAD 提交哈希"分量，指纹退化为纯 index 哈希，比对语义与正常态不同；binding 一个从未提交的源树超出本引擎契约，fail-loud 让调用方（未来集成面）决定是引导先提交还是拒绝绑定。

## 输入/输出形状

**输入选绝对路径而非 WorkspaceId**（设计选择）：`WorkspaceId` 是宿主拥有的不透明身份，无路径语义（一个 workspace 可对应多 checkout/搬迁目录）；指纹引擎需要的是具体文件系统目录，`WorkspaceId → 路径` 的映射属调用方（未来集成 adapter）职责，不属计算缝。品牌化路径未做——路径是文件系统位置不是跨边界不透明 id（`dsh-brand` 约定只管 opaque id）。

```ts
interface SourceFingerprintRequest {
  /** 绝对路径：仓库内任意目录（含子目录，按所在 worktree 求值）。 */
  readonly worktreePath: string
  /** git 可执行名/路径注入点；缺省 'git'（可测性缝，替代 PATH 全局态篡改）。 */
  readonly gitCommand?: string
  /** 单条 git 命令 stdout 收集上限字节；缺省 64 MiB（约 2M 条 index 记录）。 */
  readonly maxOutputBytes?: number
}

interface ComputedSourceFingerprint {
  /** 品牌 fingerprint 值 `dsh-source-fp-v1-<headCommit>-<stateHash>`，直接可入 `ProjectWorkBinding.sourceFingerprint`。 */
  readonly fingerprint: SourceFingerprint
  readonly headCommit: string          // 解析出的 HEAD 提交 id（hex）
  readonly trackedStateHash: string    // index 原始字节流 sha256（hex）
  readonly trackedEntryCount: number   // index 记录条数
  readonly algorithm: 'v1'             // 规范化算法代际标签；指纹值前缀同源，换代即变值
}
```

**子进程工具选择**：`node:child_process.execFile`（promisify，非 shell、argv 数组、`-C <dir>`、`windowsHide`、`encoding: 'buffer'`、错误聚合 stdout/stderr 进结构化消息）。理由：仓库唯一既有可复用 subprocess 面是 Cordis `ctx.subprocess` Service（`SubprocessRuntime`），它是**服务**不是 util——消费它需 live Context + 插件装载，纯计算入口（无 context）不可达；devframe 既有 src 对 `dsh-subprocess` 的引用仅类型面（`reliability/stop.ts` 的 `SubprocessHandle`）。仓库先例一致：`scripts/*` 的 git 调用全部直接 `execFile(Sync)`。未来若集成面落在 plugin 内，可在 adapter 层换接 `ctx.subprocess`，计算缝不变。

**平台不变性总论证**：输出只由（HEAD 对象 id，index 字节流）决定，两者都是 git 对象库内容寻址的事实；进程 cwd、路径分隔符、行尾、mtime、locale、env（除显式钉死的 `LC_ALL=C` 错误路径）均不进入输入面。指纹不含 toplevel 路径——同一内容在不同克隆位置产生同值。

## 边界登记（已裁定，如实覆盖/不覆盖）

1. **未跟踪文件面**：本指纹**不覆盖**未跟踪文件集合。`ls-files -s` 只读 index：纯 untracked 文件（未 add 未 commit）不改变指纹。AT1-05 变体 5"审查后改未跟踪文件"的覆盖方式是**间接且部分的**：改动一旦被 `git add`（staged）或 commit 即进 index/HEAD，指纹必变、verify 可拒；仅停留在 untracked 态的改动本指纹不可见——此为**已裁定边界**，由本设计登记，待总控确认是否在集成面以 untracked 集合补强（例如 `ls-files --others` 的第二指纹分量）或接受"证据链要求改动入库"的纪律约束。本波用例以"untracked 不变指纹 + staged 即变指纹"两条真实行为把该边界钉成可执行事实。
2. **热路径性能面**：绑定记录后 `resolveResultBinding` 的重算比对**不在热路径自动发生**。引擎只有一个显式异步入口 `computeSourceFingerprint`（三次 git 子进程，非热路径成本）；控制器内既有比对仍是存储的 fingerprint 字符串等值比较，零子进程。verify 何时调用（绑定前/结果路由时/审查时）属接入点裁定，见下节。

## 裁定请求项（2026-09-06 已批复：案 B，见下节）

**引擎接入点两案对比**：

| 维度 | 案 A：进 StartGoalRequest 绑定流程 | 案 B：独立 verify 面 |
| --- | --- | --- |
| 形态 | `GoalBindingController.start` 在持久化绑定前接收/计算指纹（controller 需新增可选注入的指纹端口或请求字段携带预计算值+显式 verify 校验） | 引擎旁新增 `verifySourceFingerprint(worktreePath, recorded): Promise<VerifyVerdict>`（match/mismatch 结构化结果），controller 零改动 |
| 影响面 | 触 `controller/goal-binding.ts`（start、`resolveStartRequest`、可能加错误码族路由）；`StartGoalRequest`/schema 语义联动；agent-evidence 的绑定元组断言面需同步审视 | 新文件自成一体；controller/events/schemas/journal 零 diff；`ProjectWorkBinding.sourceFingerprint` 消费方语义不变 |
| 性能面 | 绑定时刻多三次 git 子进程（一次性 admission 成本，可接受）；若要求 `resolveResultBinding` 自动重算则**违背热路径边界**，需显式 opt-in 入口 | verify 只在被显式调用时付子进程成本；热路径天然零改动 |
| 接口面 | start 请求多一字段或依赖注入，未来 P23/S4 命令面要跟着走 schema 演进 | 新公开函数 + verdict 类型；不碰既有接口，批复后一个 src 波可落 |
| 变体 5 证据强度 | 绑定时点重算可在 admission 拒绝脏树，证据最早 | verify 时点拒绝晚于绑定，但证据链（拒绝理由=计算值 vs 记录值）等价可审计 |
| 风险 | start 时序已严格（close admission → create → disarm → persist → resume），插入重算点选错会扰动失败回滚面 | 比对面落点（journal 事件/独立断言）仍需单独裁定，但不动生命周期 |

**建议**：**案 B 先行**。理由：本轮硬边界已禁改 controller/events/schemas（裁定未批），案 B 与该边界完全同构；变体 5 的直接诉求是"重算并给出可信拒绝依据"，独立 verify 面以最小 blast radius 交付该依据；案 A 的 admission 时点校验可在案 B 落地且总控批准 controller 波后叠加（两者不互斥，A 是 B 的前移使用）。落点建议：比对面与引擎同模块（`source-fingerprint.ts` 内 `verifySourceFingerprint`），避免新增模块边界；journal 事件面不进。

## 裁定（2026-09-06 总控）

**批准案 B：独立 verify 面先行，本轮落地。** `verifySourceFingerprint(worktreePath, recorded): Promise<VerifyVerdict>` 与引擎同模块落地（`source-fingerprint.ts` 内追加，`index.ts` 既有 `export *` 自动出口）。`VerifyVerdict` 为 `kind` 判别联合：`match`（记录值与现算值品牌串等值=通过，携带通过值 `fingerprint`）；`mismatch`（双值呈现：`recordedFingerprint`=原样记录主张（不可信侧），`computed`=新鲜 `ComputedSourceFingerprint` 全摘要（可信侧），JSDoc 写明各臂可信取值）。理由：

1. **零扩散**：`controller/goal-binding.ts`、`events.ts`、schemas、`session-journal.ts` 全部零 diff；`ProjectWorkBinding.sourceFingerprint` 消费方语义不变。
2. **热路径边界天然成立**：verify 是显式异步入口，三次 git 子进程成本只在被调用时发生，绑定/结果路由热路径零改动，无需 opt-in 机制——与边界登记②一致。
3. **直接交付 AT1-05 变体 5 审计诉求**：重算并给出可信拒绝依据，mismatch 双值证据链（记录主张 vs 现算全摘要）可审计，不等 controller 波。

**recorded 输入类型裁定**：裸 `SourceFingerprint` 品牌串（非 `ComputedSourceFingerprint`）——持久记录 `ProjectWorkBinding.sourceFingerprint` 就是该品牌串，verify 面镜像记录形态，调用方原样传存储值；判等语义=品牌字符串等值（与既有比对一致），headCommit 等派生摘要字段不参与判等，避免派生字段过期造成假 mismatch；mismatch 时新鲜全摘要有 `computed` 一侧完整呈现，无证据损失（持有全摘要的调用方传 `.fingerprint` 即可）。

**错误面**：引擎 5 码经 verify 原样冒泡（verify 内部就是同一次 `computeSourceFingerprint` 调用，无包装无吞）；verify 面不设 `gitCommand` 注入缝（它验证的就是生产引擎面），`GIT_UNAVAILABLE`/`GIT_FAILED` 的分类证据留在引擎用例，verify 用例钉真实可达的 `NOT_A_WORKTREE`/`NO_COMMIT`/`INVALID_REQUEST` 三码。

**案 A 定性：案 B 的前移使用，留 controller 波叠加，本轮不实现。** 绑定时点 admission 校验待总控批准 controller 波后叠加（两者不互斥），届时复用本 verify 入口；verify 结果的 journal 事件/断言落点仍属后续集成裁定。

## 放弃的替代案（一行各记）

- `git write-tree` 树对象哈希：向对象库写对象，违背只读缝。
- `git status --porcelain=v1 -z`：含 untracked/重命名归并、形状宽、更慢，且把未跟踪面混入 tracked 指纹（与边界登记①冲突）。
- 自扫 worktree 文件字节哈希：mtime/行尾/权限方差化，退化成手写规范化。
- `ctx.subprocess` Service 注入：纯计算入口无 Cordis Context，服务语义错位（留给未来 plugin 内 adapter）。
- 输入接 WorkspaceId：不透明 id 无路径语义，映射属调用方。
- unborn HEAD 静默空 head 分量：指纹语义随仓库态漂移，违背 fail-loud。

## 用例与隔离规约（dsh-ci-test-reliability 硬规则逐条）

- 每用例 `fs.mkdtemp` 唯一临时根（`dsh-devframe-sfp-` 前缀）内 `git init --quiet --initial-branch=main` 真实 repo；`git config` 本地 user.name/email；**所有夹具 git 调用**传 `env: {...process.env, GIT_CONFIG_GLOBAL/GIT_CONFIG_SYSTEM: 临时根内空文件}`，进程全局 env 零篡改（无捕获/恢复面）。
- 清理在 mkdtemp 返回后**立即注册**（数组 + afterEach 兜底 drain），`fs.rm {recursive, force, maxRetries: 20, retryDelay: 25}`——Node 内建 Windows EBUSY/EPERM 有界线性退避（本机探针实测到一次 "in use" 竞争，预算按 20×25ms 线性 ≈ 5.25s 上限定，低于默认 hookTimeout），等待的真实完成信号 = rm 的 resolve。
- mtime 无关性用例**不做 mtime 写回**（NTFS 100ns tick 往返无损假设不成立）：直接同内容重写文件后断言指纹不变，期望值全部来自新鲜计算读取。
- CRLF 用例在两平台同语义（staged 前的 worktree 行尾改写不进 index），无平台 skip；POSIX 权限探针（EACCES）不做——Windows 无对应语义，ENOENT 注入已覆盖 GIT_UNAVAILABLE 分类面。
- git 不可达用例走 `gitCommand` **注入**（引擎自带缝），不用 PATH 篡改（进程全局态）。
- 负面对照（"指纹变化检测"缺实现必失败的用例）：**staged 未提交**用例断言 `fingerprint 变化 && headCommit 不变`——只哈希 HEAD 的实现（缺 index 态检测）在该用例返回同值必失败；同时 untracked 用例断言不变，把边界登记①钉成可执行事实。
- 覆盖豁免（带理由的 v8 ignore，两处防御臂）：unborn HEAD 检出后的 generic 兜底臂（discovery 成功后 `--verify --quiet HEAD` 的可达失败只有 unborn，exit 1 由 git 文档化语义钉死）；HEAD 输出 hex 形状不符臂（`--verify` exit 0 必然产出可解析对象 id，跨平台无 fixture 可伪造成功且非 hex 的 git——Node 拒绝无 shell 的 .cmd/.bat spawn）。两处均已用行为用例钉住可达路径（unborn 用例、happy path）。

## 残余/未竟

- 案 B 比对面已按 2026-09-06 裁定落地（见裁定节）；verify 结果的 journal 事件/断言落点与案 A controller 波仍待后续裁定与实现。
- EACCES（不可执行）分类臂无平台可复现用例（POSIX-only 语义），以 ENOENT 用例覆盖同分类臂；如需 POSIX 强证据需 CI Linux lane 补充。
- 大仓库（>64 MiB index 流）行为只有上限注入用例（`maxOutputBytes: 1`）钉分类，未做真实大仓库压测。
