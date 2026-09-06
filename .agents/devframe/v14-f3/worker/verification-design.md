# v14-f3 GAP F3 区分性验证设计（只设计，不实施）

目标：一个"修复前红 / 修复后绿"的验证，且对三个候选方案有判别力——不是对所有方案都通过。

## V1：语料级 shell 栈唯一性静态守卫（判别主刀）

- **内容**：在 `scripts/session-snapshot-corpus.corpus.ts` 新增一条不变量用例：解析每个 headless composition owner 的 `cordis.yml` 与 `cordis.snapshot.yml`，对 `{posix, win32}` 两个平台家族断言"每个 shell 工具名家族（`bash`：tool-bash / tool-bash-persistent；`pwsh`：tool-pwsh / tool-pwsh-persistent）在该家族相关行被触碰时恰好一行活跃"。disabled 表达式用 `evaluate` 注入 `{ process: { platform } }` 求值（复用 base.spec.ts:79-80 的既有原语）。
- **修复前**：红——`persistent-pwsh-tool-turn` 的两个 composition 在 win32 家族下同时活跃 `tool-pwsh`（基座行）与 `tool-pwsh-persistent`（insert 行）。
- **修复后**：绿——方案 A 补上 `tool-pwsh: disabled: true` 后两个平台家族都恰一行。
- **判别力（为何不是对所有方案都通过）**：
  - 方案 A → 绿（组合里真的只剩一行活跃）。
  - 方案 B → 配合 A 绿；单独 B 无意义（守卫本身在没有 A 时持续红——它就是检测器不是修复）。
  - 方案 C（core/tools 替换/幂等注册）→ **仍红**：守卫是静态行集求值，不看注册表运行时行为；两个活跃 `pwsh` 行依然并存，不变量依旧被破坏。这正是设计意图——C 不解决组合矛盾，只把矛盾降级为静默。
- **归属 tier 与放置**：Snapshot 车道的语料不变量（`vitest.snapshot.config.ts:48` 已 include 该 corpus 文件；`pnpm run test:snapshot` 即执行）。keyless、全平台跑、无子进程——在 POSIX CI 上就能抓到 win32 才炸的错，这是它相对 tier 2 的核心增量。按 docs/testing.md:13 的 Snapshot tier 归属；语料所有权依据 testing.md:52-54。

## V2：win32 门控快照回放（动态证实）

- **内容**：`pnpm run test:snapshot -t persistent-pwsh-tool-turn`（win32 宿主、装有 pwsh）。场景清单见 snapshot.yml:1-9（profile headless / composition persistent-pwsh / platform pwsh / header pin）。断言不变：`runLoaderSmoke` 期望退出码 0（headless.snapshot.ts:696-699）、持久会话与 fixture 逐行相等（752-759）、`verifyHeaders` 对 pin 的 header/schema 重建比对（760 → 496-544）。
- **修复前（win32）**：红——dsh 加载失败非零退出，stderr 含 `plugin tree failed to load` 与 `tool "pwsh" is already registered …`（app-boot index.ts:795,808-825；重名文案 core/tools index.ts:720）。Battery 链已持有该红证据，设计阶段不重跑。
- **修复后（win32）**：绿——加载成功、工具 schema 与 POSIX 录制一致（持久插件 schema 平台无关）、header pin 通过。
- **判别力**：
  - 方案 A → 绿。
  - 方案 C → **仍红，但红点不同**：加载可能成功，但两行只剩一行 `pwsh`，若幸存者非持久插件，schema 集与录制 pin 不符，`verifyHeaders` 失败——验证把"库纪律破坏"翻译成可见红，而不是放行。
  - 在 POSIX 宿主上此 tier 修复前后都绿（基座行平台禁用）——**单靠 V2 无判别力**，这正是缺口的本质，也是必须配 V1 的原因。platform: pwsh 的 skip 规则（headless.snapshot.ts:643-647）使本 tier 只在有 pwsh 的宿主运行；win32 覆盖归 CI 平台矩阵（testing.md:20）。
- **归属 tier 与放置**：Snapshot tier（docs/testing.md:13），场景文件已在 `snapshots/session/persistent-pwsh-tool-turn/`，无需新文件；A 落地的 PR 直接以该场景为 keyless 回放证据。

## 组合使用

V1（任何宿主，静态）+ V2（win32 宿主，动态）成对：V1 提供"修复前在任何宿主可复现的红"与对 C 的否决信号；V2 提供产品路径上的最终绿证。两者都不是 pass-for-all：C 在两层分别以"静态不变量仍破"与"header pin 失配"被拒，A 在两层全绿，B 单独在 V1 红（作为检测器的自检）。
