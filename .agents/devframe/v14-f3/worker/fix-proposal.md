# v14-f3 GAP F3 最小修复文件域提案

前提（证据见 `semantics.md`）：win32 宿主上 dsh-base 的 `tool-pwsh` 行启用（cordis.patch.yml:256-258），场景 composition `persistent-pwsh-tool-turn` 只 disable 了 `tool-bash` 并 insert `tool-pwsh-persistent`（cordis.snapshot.yml:89-95 / cordis.yml:81-87），两个插件激活期都在根全局层注册 `pwsh`，第二个注册者抛 `tool "pwsh" is already registered …` → `plugin tree failed to load` → 场景红。POSIX 上录制/回放天然绿（基座行平台禁用），因此缺口是**平台条件式冲突对录制宿主不可见**。

以下三个候选并列权衡；A 是最小修复，B 是防复发的守卫，C 经评估建议**不采纳**（论证保留备查）。

---

## 方案 A（推荐采纳）：场景 composition 补全——补 `tool-pwsh` disable 行

**性质**：只触碰 `snapshots/**`，属**测试资产**（录制会话语料），非产品代码。修复所有权归属：composition owner 规则下该场景自己就是 `persistent-pwsh` composition 的 owner（headless.snapshot.ts:472-475），回放 patch 与 live patch 必须成对保存在同一场景目录（session-snapshot/README.md:77 "Each composition owner keeps its replay patch beside its live patch"）；语料所有权与放置规则在 docs/testing.md:52-54（`dsh-session-snapshot` 拥有共享存储规则与 profile 适配器，`snapshots/` 拥有会话驱动场景）。评审归快照语料/测试面，不改 `packages/**`。

**精确文件清单与最小改动形状**（两文件对称，各加一个按 id 打中基座行的 disable 行，行为级描述、不写实现）：

1. `snapshots/session/persistent-pwsh-tool-turn/cordis.snapshot.yml`——在既有 `- id: tool-bash … disabled: true`（89-91 行）旁补一行同构的 `- id: tool-pwsh / name: '@deepseek-ai/dsh-tool-pwsh' / disabled: true`：语义是"该 composition 接管 shell 工具栈时对基座两个原生 shell 行**都**表态"。写法镜像同语料 `pwsh-tool-turn` composition 已有的两行表态（其 cordis.snapshot.yml:83-91：tool-bash disabled:true + tool-pwsh disabled:false）。
2. `snapshots/session/persistent-pwsh-tool-turn/cordis.yml`——同样的行加进 live composition（81-83 行 tool-bash 旁），保持 owner 的 replay/live 成对一致。

**影响面/风险**：

- POSIX 上零行为差：该行在 POSIX 本来就因基座平台表达式而禁用；补行只是显式化。win32 回放/录制从"加载失败"变为"仅持久 pwsh 注册"，模型可见工具集与 POSIX 录制 fixture 一致（持久插件 schema 平台无关），header pin（snapshot.yml:6-8）比对通过。
- 风险极低：不改任何产品行；唯一注意点是保持两个 composition 文件同步改（漏改其一会让 record/replay 行为分叉）。
- 需要回放验证一次 `-t persistent-pwsh-tool-turn`（verification-design.md 的 tier 2）。

**与 AGENTS.md 契约的契合**：不改库行为、不动 spec 断言；"Tests describe behavior"——场景修复只修正测试资产自身的组合矛盾；行内无需注释赘述（同语料 pwsh-tool-turn 已示范该写法，保持对称即可）。

**它不解决什么**：不阻止下一个 composition 再犯同类错（无守卫）；不动 core/tools 语义；对语料之外的宿主组合（用户 cordis.patch.yml 里 insert 一个撞名工具插件）无影响——那类场景本来就在加载期 fail loud，属既定设计。

---

## 方案 B（推荐与 A 成对采纳）：语料级"每个平台家族恰好一个 shell 工具栈"静态守卫

**性质**：产品侧/测试基础设施（`scripts/**`），不触碰 `snapshots/**` 与 `packages/**` 运行时。动机：A 修的是个案；本缺口是平台条件式的——录制宿主（POSIX）永远看不到红，win32 才红。按 AGENTS.md "Misconfiguration fails loud at load when self-contained, otherwise **at the earliest resolvable point**"，对这类非自包含错配，"最早可解点"是所有宿主都能跑的静态语料守卫。

**精确文件清单与最小改动形状**：

1. `scripts/session-snapshot-corpus.corpus.ts`——新增一个 `it(...)` 用例（该文件已在 `test:snapshot` 车道执行，vitest.snapshot.config.ts:48）：对每个 headless 场景 composition owner 的 `cordis.yml` 与 `cordis.snapshot.yml`，解析行集后断言——凡 composition 插入/启用 `tool-pwsh-persistent`（或 `tool-bash-persistent`），则对应 shell 家族的原生行（`tool-pwsh` / `tool-bash`）必须在 composition 内被显式 disable（按 id 打中），反之启用原生行时禁止插入同名持久孪生。判定方式复用现成原语：`evaluate` from `@deepseek-ai/cordis-plugin-loader`，以 `{ process: { platform } }` 注入求值 disabled 表达式（`packages/bundle/base/tests/base.spec.ts:12,79-80` 已示范该用法），按 `posix`/`win32` 两个平台家族各断言"恰好一个活跃 shell 工具行"。
2. 无新依赖、无新文件（`entryListSchema` 解析与 js-yaml 已在语料 spec 的依赖面内；base.spec.ts:11 同款）。

**影响面/风险**：

- 今天跑必红（恰好命中 persistent-pwsh-tool-turn 这一对 composition），A 落地后转绿——判别力见 verification-design.md。
- 风险：守卫建模的是"已知四个 shell 行 + 持久孪生"的封闭家族；若未来出现第三种 shell 工具需扩家族表。为避免过度约束，断言范围应限定在"composition 触碰了任一 shell 行"的场景，不波及 ptc/web/advanced 等不涉 shell 的 composition。
- 它是静态检查，不证明运行时（运行时由 tier 2 的真回放覆盖；平台矩阵归 CI——testing.md:20 "CI owns … the platform matrix"）。

**与 AGENTS.md 契约的契合**：守卫是"mechanically checkable invariant"，放进已执行的车道（test:snapshot 语料 spec）并可用 A 之前的红作 invalid case；符合"When adding or changing a mechanically checkable invariant, wire it into an executed top-level gate … cover each changed acceptance path with an invalid case"；也不违反"never default to the full suite"（挂在既有 test:snapshot 车道内，无新增套件）。

**它不解决什么**：不是运行时护栏（不改 core/tools、不改 bundle）；对语料之外的组合（用户自建 profile、SDK 宿主）无效——那些继续依赖加载期 fail loud；单独采用（不配 A）会让语料守卫常红，因此 B 必须与 A 成对。

### B 的变体（按代码事实评估后否决，记录备查）

- **基座平台门控行"成对性"加固**：已是现状——base.spec.ts:52-84 逐行对 `bash-sandbox`/`tool-bash`/`pwsh-sandbox`/`tool-pwsh` 在 win32/linux 两个注入平台上断言反相对称，base README.md:76 文档化。本缺口的行来自 overlay（场景 insert），bundle 内部测试原理上看不见 overlay，无法关洞。
- **工具插件注册守卫**（tool-pwsh-persistent 在 apply 时探测已有 `pwsh` 并给组合级诊断）：与注册表自身的 fail-loud 重复，不增加判别力（POSIX 录制依旧绿），反而在两个平级插件间加耦合；core/tools 的重名文案（index.ts:720）已给出可操作的指引。

---

## 方案 C（评估后建议不采纳）：core/tools 引入替换/幂等注册模式

**形状（假想）**：给 `ctx.tools.register()` 加 replace/idempotent 语义（如"已存在则覆盖"或 `{ replace: true }` 选项），触碰 `packages/core/tools/src/index.ts`（register 与 ToolLayer duplicate 诊断）、`packages/core/scope/src/store.ts`（NamedEntries 增 replace API）及其 spec。

**为何违背库纪律（四条独立论据）**：

1. **现行为是测试钉死的契约**：tools.spec.ts:1984-1996 断言同名二次注册抛错并随 fiber dispose 注销；改语义必须连测试一起改（"Change obsolete behavior with its tests"），且 720-721 行错误文案本身就在引导"per-agent 变体请走 `agent.ctx`"——库已给出了正确的逃逸口（scoped 层）。
2. **与 fs 双注册先例同类**：fs 服务双注册"fail the load"是文档化的设计（base README.md:76,127）；把工具重名改成静默替换会拆掉同一缺陷类的防线（"two claims on one name is a contradiction, not a merge"——同类表述见 index.ts:711-715 对 presentation mode 单格的理由）。
3. **替换语义与"行序无加载语义"正面冲突**：base cordis.patch.yml:12-13 明确行序不承载加载语义、激活由服务可用性驱动。"后注册者赢"会让模型可见工具集依赖激活顺序——跨宿主、跨重构不稳定，等于把确定性换掉。
4. **即便实现也换不来绿**：替换后 win32 上两行只剩一行 `pwsh`，与 POSIX 录制的 header pin（tool-schemas sidecar）比对的是持久插件 schema；若替换方向不是持久插件，schema 集与录制不一致，verifyHeaders（headless.snapshot.ts:496-544）照样红——只是把响亮的加载错误降级成静默工具集漂移，然后换一个红。收益为负。

**结论**：C 违反 "Misconfiguration fails loud" 与 registrations-as-effects 纪律，且对本缺口无判别力；不建议采纳。若未来真出现"合法替换"需求，应作为显式新能力（Service Definition 层面设计三角色）另立项，而不是借本缺陷入场。

---

## 采纳建议

A + B 成对落地：A 止血（场景绿），B 防复发（语料级红在任何宿主可见）。C 否决。两方案合计触碰三个文件（两个 snapshots YAML + 一个 scripts corpus spec），零产品运行时改动。
