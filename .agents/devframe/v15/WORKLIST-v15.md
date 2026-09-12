# DSH V1.5 总控四态清单（工作文件）

- 总控会话：本会话；goal：goal-264c053a-c0e5-4a1e-ba21-df694c50e045（rev 2，complete）
- 基线：`.agents/devframe/v15/baseline-20260908-171726.json`（127 项）；当前 main tip `06839fcf3e`
- 用户授权：main 合并权在 V1.5（B 选项）；按工件对表不等 V1.2 回复；Worker 模型 glm-5.3-flash（用户显式选择）；每火山账号 ≤2 实质 Worker；单写面。
- 本文只记状态与证据锚点，不替代审查报告。

## 一、源码态（代码是否落好）

| 条目 | 状态 | 证据锚点 |
| --- | --- | --- |
| Slice A：terminal ownership 源码（ownership.ts / index.ts / host-stop.ts 挂线） | ✅ 已提交（`4ea2d2618b`） | 硬阻断 D1 已修：3×loader-composition spec 加 import+Map 项，pwsh 复跑 1 passed exit 0；D4/D10 在残留收口片完成 |
| Slice A：e2b 组合修复（D3） | ✅ 完成（ffba7990） | composition.e2e.ts 挂 AgentRegistry + `ctx.terminalOwnership`/`ctx.terminals` instanceof 断言；SHA 4CEEC6EE 抽验 MATCH |
| Slice A：terminal README D6-D8 | ✅ 完成（f44bf717） | 三文件 SHA 抽验 MATCH；配对门禁（含 sidecar --write 重录）+md-wrap+limitations 全绿 |
| Slice A：catalog 生成收口（D2） | ✅ 完成（72d40f7b）+ 总控复核通过 | 生成器 exit 0（11 written）+ `verify-cordis-catalog` exit 0（115 up to date）；7 类型全走 linkedTypePages；5 文件 SHA 抽验 MATCH；超面 9 个生成器写盘文件经 diff 抽验确认全在 GENERATED 区内；`projectRun`→agent-hierarchy.md + runtimeServiceExclusions 按家族先例接受（复审二次确认） |
| Slice A：typert 契约修（我修） | ✅ | run.ts `startProject(): ProjectLifecycleState`、`requireAdmittedTask(): TaskRecord`（生成器从 2 类报错推进到 type-link 阶段） |
| Slice B：command-goal-binding | ✅ 完成（cgb-incremental，huoshan-2）+ 总控核验通过 | 5 观察项全落实（JSDoc workspaceId/admission 包装、resolveStopBinding 重排=先拒绝后持久化、口径收窄、tree 面条件修正、deny 断言绑定文本）；focused 24 passed exit 0；配对门禁 4 次 exit 0；10/10 哈希 MATCH；净变更面与回执自洽（index.ts/host-stop.spec.ts 的 diff 为既有未提交改动） |
| Slice B：tsconfig completion-consumer | ✅ | verify-tsconfig-paths exit 0（早前已验） |
| Slice C：terminal 契约钉死（D5） | ✅ 完成（terminal-pin，huoshan-2）| service.spec.ts 净增 +15/-0（silent deactivation 契约测试），31 passed exit 0 + 单跑确认；机制 fiber.ts:704-710 亲证；SHA 15C8BAD6 MATCH |
| Slice A/D9+D4+D10 残留收口 | ✅ 完成（terminal-residual，huoshan-2）+ 总控裁决收口 | D9=单数删除、5 处测试改 plural 逐字同义；D4=neverBundle 外置化（ownership.js 零类定义+外部自导入，撤销 worker 应验收命题加的 `export { TerminalError }`——总控一行集成修正，撤销后重验：build 0/0、55 tests 0、catalog check 0，ownership.ts=BCBE12F3）；D10=两处 commit 期裸 Error→TerminalError(OWNER_NOT_LIVE) 同 message，L29 内部不变量裸 Error 保留（裁决：接受，非用户可达+全仓先例）；owner 复用裁决：接受（message 区分、避免 union 扩面）；目录重生成 gen+check 双 0 |
| Slice C：agent-dispatch 完成门 | ✅ 完成（3d0cca27） | e2e 一次整跑 6/6 绿 exit 0（80.28s）；consumer.ts fail-loud（GOAL_BINDING_INJECT 单源 + 10s 有界等待 + `ctx.get` 探测点名抛错）；断言证据修正（lead 日志 tool/call + lead 路由请求含 followup 标记）；SHA 8493F22B / E8FCD51B 抽验 MATCH |
| Slice C：candidate request-budget 挂载顺序 | ✅ 已提交（`06839fcf3e`） | `consumer.ts` 在 `candidateRootSessionId` 模式等待嵌套预算 fiber 后才发布 `agent_dispatch`；回归测试 `request-budget-mount.spec.ts` 断言未激活前 apply 与工具注册均保持未完成；focused vitest 12 passed，package tsc `--noEmit` 0；提交全 hooks 绿 |
| D9 `prepareReopenOwned` 单数无生产调用 | ✅ 已完成并随 `4ea2d2618b` 提交 | 生产 API 删除为 `prepareReopenOwners`；相关测试改为 plural 形式并通过 55 项 terminal/cgb 验收 |

## 二、profile 态（配置/门禁是否一致）

| 条目 | 状态 | 证据锚点 |
| --- | --- | --- |
| tsconfig.base.json | ✅ | `/ownership` 别名移出生成区（含注释）；`completion-consumer` 保留在区外（overlay Loader 真用）；`verify-tsconfig-paths` exit 0 |
| SERVICE_PAGE / cordis 目录 | ✅ | 生成 + check 双 exit 0；生成物只由工具产出，超面页面改动均在 GENERATED 区 |
| 双语配对 | ✅（terminal README）/ 债务（tool-catalog en/zh 88 行，保留） | f44bf717 门禁绿；债务登记 |

## 三、运行态（真实运行证据）

| 条目 | 状态 | 证据锚点 |
| --- | --- | --- |
| 3080 GUI | ✅ 已重启（PID 20020，2026-09-09） | `node --import tsx/esm apps/cli/src/bin.ts web --no-open`；监听已恢复；无认证 HTTP 访问返回预期 401 |
| 候选预算 live-fullchain-1788825148717 | 未动 | 95/96、0 集成、terminal-failed |
| 模型路由 | 实测记录 | settings `agent-default-model` = huoshan-2/glm-5.3；`workflow` `agent()` 支持 per-agent provider/model 覆盖（huoshan-2+glm-5.3-flash 探针返回 OK）；普通 `subagent` 工具无路由参数（限制已记） |
| Worker 归因 | 未知（记为限制） | 4 子代理 provider 未从持久化 session JSON 实证（短 id 未匹配到文件）；按「归因只认 session JSON」纪律记未知 |
| e2b 组合真实运行 | 缺凭据 → 2 skipped（skip≠pass） | 降级证据：本地等价组合复现（挂 AgentRegistry 前 undefined → 挂后激活，含目录登记路径）；真实绿待有 E2B_API_KEY 环境 |
| 账号负载 | 本轮已收口 | 当前无运行中 Worker；本轮 h1/h2 均有 `glm-5.3-flash` 实际会话记录，所有 Worker 已 settled，未留下空转任务 |

## 四、生产验收态（能否提交）

| 条目 | 状态 | 证据锚点 |
| --- | --- | --- |
| 候选完成门 e2e 终验 | ✅ **提交后复跑 6/6 绿，exit 0（68.72s，2026-09-09 08:51）** | `pnpm exec vitest run --config vitest.e2e.config.ts packages/experimental/agent-dispatch/tests/candidate-fullchain.e2e.ts`；同时保留前次定稿树日志 `.agents/devframe/v15/test-candidate-e2e-final-20260908-1905.log` |
| 静态门禁矩阵 | ✅ 全绿：tsconfig-paths 0 / cordis-catalog --check 0（撤销后复验）/ package-dependencies 0（52 包）/ **export-jsdoc 0（补 isGenerationAdvance JSDoc，HEAD 既有违规，goal-binding.ts=D91DF3BE）/ md-wrap 0**。⚠ repo-wide translation-pairing 红=HEAD 既有债（docs/tool-catalog.md 对 + plugin-package-inventory-deepseek README 对，工作树均未动），非本批引入，提交时按 hooks 实况处理 | 各命令 exit 0 记录 |
| 独立复审 | ✅ 完成 | workflow-3 的 E FAIL（run.ts 重复导入）已修；最终字节复审（`31e4c33c-7127-42ea-a960-ebd4dffbb2d4`）确认 terminal 残留与总控修正通过，D4 打包类身份问题已修后重验 |
| 提交前置 | shim 预检完成 | 真 git 全套在 codex deps；主树 `native/git/usr/bin/sh.exe` 提交时按 V1.4 硬链接 shim 法补建；core.hooksPath=.git/dsh-hooks（lefthook 三钩子） |
| 提交执行 | ✅ **四批全部落地，全 hooks 绿，diff-stat 逐批核对** | `82943376a5` gate-fix（1 file +3）；`4ea2d2618b` A=terminal ownership（29 files +514/−27，含 notes 三件套与 terminal 目录页）；`d44aa006e8` B=command-goal-binding（11 files +368/−102；lint 拦下 composition.ts:224 超长已重包）；`89840292e7` C=agent-dispatch+catalog（22 files +869/−92；lint 拦下 consumer.ts timer prefer-const，已 const 内联重构 + lint/tsc 双 0）；**提交后 e2e 终确认 6/6 绿 77.79s**。bash shim=复制 codex-git sh.exe 为 native/git/usr/bin/{sh,bash}.exe（硬链接跨盘不可行，已实测修正 V1.4 记录法）；提交后剩余脏面=精确 leave-set |

## 残留登记（后续切片或决策）

1. `candidate-request-budget` 挂载竞态 → **✅ 已提交 `06839fcf3e`（await 子 fiber）并验证**：request-budget-mount.spec（53 行）、agent-dispatch focused 12 tests、包级 tsc --noEmit、提交后 e2e 6/6（68.72s，见上表）。保留 HMR 期间父 fiber 卸载/重载的**专项观察**（需具体失败观察才可立项；registry 贡献处置已有 service.spec dispose→移除观察覆盖），当前 3080 进程未触碰。
2. ~~tool-catalog 双语配对 + 生成器回归~~ → **✅ 已提交 `fadc05e0c6` 并独立复审 PASS**：manifest 三处补挂 agents+ownership（注入链 agents←ownership←terminals）；en 重生成拾取 completion-consumer 小节（+50）；zh 补齐两段演进+重生成行（+154/−6，80/80 JSON 块逐字节一致）；两条 sidecar 重录（git hash-object 4/4 吻合）；repo-wide 配对 1195 对全一致、md-wrap 2408 文件 0、--check 0。复审身份 glm-5.3-flash（huoshan-1）。
3. POSIX loader spec（bash/tool-terminal）：win32 `describe.skip` 机制正确，验证归 CI 平台矩阵——本地无动作，记录归属。
4. e2b 组合真跑：缺 `E2B_API_KEY`，凭据环境才可收口；本地保持降级证据（等价组合复现 + instanceof 断言在位）。
5. e2e:136 10s 硬超时 + :958-981 50ms 全 zstd 扫描稳定性——观察项，非阻塞。
6. reviewer C ④（冷恢复不可达分支）、⑥（Note 拟议态保持）；reviewer A/B 延迟项 D4/D9/D10/D5 均已由 terminal-residual / terminal-pin 收口并在 `4ea2d2618b` 后重验。
7. **Shadow 入口（已提交 `76643612f8`）**：实测 web profile 组合（dump-config 567 行）不含 shadow-router/devframe 层——功能在 main 但入口缺失。交付=①真实 e2e 三路径 spec（`shadow-router/tests/profile-entry.spec.ts`：声明式 shadowSessionId→四工具安装+project_open 真实打通；未配置→unknown tool fail-closed；相对/缺失 authorizedRoots→服务永不激活）spec 3/3 绿、整包 51 passed+1 skipped exit 0、staged lint 0；②用户入口模板 `apps/cli/config/examples/shadow/cordis.patch.yml`；③README 双语「启用 Shadow」三步小节已提交 `208a005565`（+26/−2，配对重录 check=0，md-wrap 0）；④独立复审（huoshan-1）完成：路径1 PASS、路径2 PASS-with-finding（"anywhere" 为机制推断+单探针，host-designation.spec 双 scope 断言互补）、示例补丁 PASS-with-findings、**路径3 FAIL**——裸 ctx 缺五个注入依赖致 fiber 永久 PENDING，断言对配置零区分度；已修复 `97e34b7bb7`（全依赖 mount 真跑 Service.init，rejects.toThrowError 两分支），整包 exit 0。**本项闭环**。遗留可选：四件套 schema 在本 spec 补断言（host-designation 已覆盖，互补项）；live 热应用未在真实 GUI 实测。
8. **GUI 启用 Shadow（用户已选路径 a：正式发布安装包；进行中）**：实测 `dsh plugin --profile web add` 失败——pnpm 重解析需拉 5 个 GitHub release tarball 全部 UND_ERR_DESTROYED，但 Invoke-WebRequest HEAD 同一 URL **200 成功**（pnpm fetch 层问题，非断网）；`gh` CLI 未安装、无发布凭证。既有发布模式=每包独立仓库 `github.com/NOirBRight/<pkg>/releases/download/v<ver>/<pkg>-<ver>.tgz`。**当前 3080 GUI 未装 shadow-router，勿误报已启用**。下一步：①构建 shadow-router 及其 @deepseek-ai 依赖闭包（需 build 授权，实验包 lib 现状未知）→ ②pnpm pack 出 tarball → ③确认/创建 NOirBRight 下的发布仓库并传 release（需 gh 或 token；token 在 ~/.dsh/.credentials.yaml，禁读，需用户操作或明确授权）→ ④profile package.json 按 URL 依赖加入 + 处理 pnpm fetch 层问题（或换用 store 缓存/离线 tgz 安装）→ ⑤写 cordis.patch.yml（insert+config，shadowSessionId=session-8c2ada33-ff47-4e54-b80d-566500722725，authorizedRoots 待用户确认，建议 D:/dsh-devframe）→ live 热生效。
9. **发布与接入实况（本会话完成）**：测试漂移 9 文件+client 导入修复已提交 `eb0a841ad4`（lint 拦截系钩子 --fix 落工作区未进暂存，re-add 即解）；**Release 已上线** `RD2100/dsh-devframe` tag `shadow-router-v0.1.2-alpha.4`（单 tarball，peer 走宿主约定+范围版本）；`release-assets.githubusercontent.com` CDN 被网络掐断，pnpm/Invoke-WebRequest 均断连，**gh API 通道可用**（往返 32796 字节一致）；已物化进 profile node_modules+manifest 登记+cordis.patch.yml 写入 insert+config（shadowSessionId=session-8c2ada33…，authorizedRoots=[D:/dsh-devframe]）；**dump-config 验证组合含 shadow-router 全配置 exit 0**。⚠ 遗留观察：四工具在运行 GUI 的出现待会话下次工具清单刷新确认（若 live 热应用未触发，重启 GUI 在 boot 时应用）；**全仓 build:lib 仍红**——client 面 apps/web/tests（dispatch-gate.e2e/scaffold，主树已提交内容）rootDir/file-list 违规系主树预存问题，与 shadow-router host 产物无关，独立工作流待派。
10. **记忆功能同流水线接入（本会话完成）**：`project-memory-v0.1.2-alpha.4` Release 已上线（同仓 tag）；gh API 回流物化进 profile node_modules；manifest 登记 URL 依赖；vault 建 `C:/Users/25313/.dsh/vault`；补丁层 insert+config（vaultRoot、writeEnabled: true、userScopeEnabled: false）；dump-config 双插件+配置验证 exit 0。**生效条件=重启 GUI（用户动作，宿主进程承载本会话无法自重启）；重启后 Shadow 四工具+记忆三工具同时上线。** 可视化状态卡片仍属新需求未排期。**用户已裁决：走 A（正规发布族）。** 执行序：①workflow-3 修漂移使 build:lib 绿（进行中）→ ②实测圈定发布闭包（预计 10-15 包：shadow-router+本体依赖+6 运行时 peer 及其传递依赖）→ ③逐包 private→publishConfig 定版 0.x alpha、pnpm pack → ④gh release create 挂 RD2100/dsh-devframe（tag 建议 v0.1.2-alpha.4-shadow.1，15+ tgz 资产）→ ⑤profile package.json 加 URL 依赖（处理 pnpm fetch UND_ERR_DESTROYED：优先排查代理/store，兜底手动灌 store）→ ⑥写 cordis.patch.yml（insert+config，shadowSessionId=session-8c2ada33-ff47-4e54-b80d-566500722725，authorizedRoots 待用户确认，建议 D:/dsh-devframe）→ live 热生效。**维护税已向用户言明并接受。**
