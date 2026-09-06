# Agent Note: 快照会话录制与 UI 期望变体

Status: proposed

[English](2026-09-06-snapshot-session-recording-and-ui-variants.md) | 中文

## Problem

pinned 侧车的平台期望变体落地后，Windows B 族漂移仍剩四个残留面：persisted-replay 比对持续失败，因为 `session.jsonl` 既是 replay 脚本又是比对目标，其录制中的工具调用名为 `bash`，而 win32 组合中不存在该工具；tool-schema pin 断言始终不可达，因为 `assertReplaySession` 先执行 persisted-replay 比对并遮蔽其后的一切；用例 1 的内联快照活在测试文件里，没有任何平台消费通道；`ui.expected.md` 在期望词表之外，其 `[data-sample="bash"]` 选择器永远无法命中 win32 渲染的 pwsh 卡。机制虽在，win32 运行依旧红。

## Proposal

在快照场景配置中扩展录制侧与呈现侧两类变体：

- manifest 根级 `sessionVariants` 字段（`win32: true`）声明 canonical 录制的平台变体，由新解析缝 `resolveSessionFixturePath` 解析为基础文件同目录的 `session.win32.jsonl`（命名平行于既有 `session.<n>.jsonl` 子文件家族）；声明了变体而文件缺失 fail-loud；borrower 场景（带 `session` source 引用）禁止声明。
- `ui` 加入 `SnapshotExpectationKind`（stem `ui`、扩展名 `md`），`ui.expected.md` 因此获得完整期望机制：变体解析、清单放行、所有宿主的存在性校验、corpus 门扫描。
- web 通道两者皆消费：`assertReplaySession` 经解析缝取 fixture，pin 断言前移至 persisted-replay 比对之前（解除遮蔽），minimal-preset 用例经单一平台缝驱动 shell、内联快照保持 POSIX 规范形（cwd token 化、分隔符归一），工具清单改为按平台显式断言而非改名成假的共同形态。
- minimal-preset 语料落地 `session.win32.jsonl`（恰四行录制的 bash 调用改写为 pwsh）与 `ui.win32.expected.md`（pwsh 卡行），manifest 双双声明，corpus 门放行声明的录制变体并对其执行与基础文件同款的 typed-identity 固定点与 scrub 校验。

PROMPT 常量裁定不动并如实记录：system-prompt 面两平台一致（阶段 2 实测）、authored 措辞无平台条件行为、参数化会强迫脚本与 UI 行的变体连锁且无断言收益。诚实残留——win32 用户措辞问 bash 而脚本化模型调 pwsh——属 authored 语料的外观分歧，登记而非掩盖。

## Key design

- **显式声明而非推断。** 读取宿主的 `process.platform` 经同一注入缝映射到既有期望变体词表；解析器内部不读全局，未声明变体的平台读基础文件，POSIX 行为按构造不变。
- **双向清单闭环扩展到录制。** 声明的录制变体必须提交且在所有宿主校验存在性；磁盘上无 manifest 声明的录制变体被拒绝；声明的变体 JSONL 执行与基础文件同款的 typed-identity 固定点与请求头 scrub 校验——corpus 门扩展是放行它们，不是豁免它们。
- **解除遮蔽要挣得独立观测。** pin 断言前移由破坏性负观测证明：损坏 win32 schema 变体后运行恰在 tool-schema pin 断言处失败——被遮蔽的顺序永远无法呈现这一点。
- **诚实优先于归一。** 内联快照保持两平台共用的单一 POSIX 规范形；工具清单移出快照、改为按平台显式断言（win32 上 `[pwsh, str_replace_editor]`），而不是把 pwsh 改名成 bash 以维持共同形态。

## Alternatives considered

**把变体塞进既有 `session` 字段。** `session` 字段是 borrower 判别式（corpus 门与 scaffold 以 `session !== undefined` 判只读借入者）；让它承载变体声明会破坏该语义。独立根字段保持判别式干净。

**UI golden 豁免出词表。** 让 `ui.expected.md` 留在期望机制之外，其平台分歧就持续无主，win32 行对清单守卫与 corpus 门均不可见。收录 `ui` 为类别即闭环侧车类别已有的同一循环。

**win32 工具断言里把 pwsh 改名 bash。** 假的共同名字会让 win32 运行变绿同时断言一个不存在的工具。按平台显式断言更长但真实。

**参数化 PROMPT 常量。** 按上文记录拒绝；本波交付的缝（shell 缝、变体文件）已覆盖实际观测到的每一个平台条件行为。

## Acceptance criteria

- minimal-preset lib 模式 delta 运行从基线 2/3 失败转为 **3/3 全绿**：persisted replay、内联快照、Web 卡片用例全部转绿，清单守卫保持绿。
- 损坏 win32 schema 变体后运行恰在 tool-schema pin 断言处失败（破坏性负观测），还原后工作树回净。
- `session.win32.jsonl` 与基础录制的差异恰为四行录制工具调用行（bash→pwsh 及 pwsh 命令文本），session 头 token 与基础同构（`{{cwd}}`、稳定 `createdAt`）；`ui.win32.expected.md` 差异恰为 pwsh 卡行。
- corpus 门在变体放行与同款 typed-identity/scrub 校验下通过；session-snapshot 包套件、包 `tsc -b`、仓库 build、`gen-cordis-catalog` 全干净；翻译配对保持一致。

## Risks

- 本波全部执行证据来自 win32 宿主；POSIX 行为由构造保证（无 posix 声明、基础文件解析）并被单测钉住，但 lib 模式 delta 未在 POSIX 宿主实跑——合并 CI 门拥有该通道。
- headless/sdk/acp 的 suite 通道不消费录制变体；非 web 场景今天声明 `sessionVariants` 会解析通过但无消费者，与 pinned 侧车波同款过渡纪律。
- record 模式（带 key 重录）未对录制变体演练；本语料为 authored 不重录，但未来带平台变体的 live 录制场景需要重新验证 refresh/record 写回路径。
- corpus 门扩展是机械必要性（未声明名拒绝会打红已提交的变体）；它只放行声明的变体并对其执行基础文件同款校验，但未来 manifest 契约变更必须让门与解析器词表同步演进。
