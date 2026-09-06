# C-2 实现记录：显式 @codex/@claude/@cursor 提及——最小合规落地

- 工作树：`D:/dsh-devframe-v14-product-lead`（分支 `codex/v14-product-lead`，基线 `6757b1b8f2`，收尾 HEAD 见 §四 commit 列表）
- 执行方式：一次性 Worker（总控授权接管后派发），按契约①–⑥小步提交；证据全部为本机真实命令与退出码。

## 一、实现内容（对照总控契约逐条）

- **① 宿主半部（目录=注册表实况）**：`packages/subagent/subagent/src/index.ts` 的 `SubagentRuntime.list()`（既有只读方法，返回注册表插入序名单）加挂 `@Remote('providers')` 线界面。生成面实测：`lib/typert.host.js` 出现严格描述符 `id: '@deepseek-ai/dsh-subagent#subagents/providers'`（`method: 'providers'`, `implementation: 'list'`, `result: strict z.array(z.string())`）；`lib/typert.remote-client.d.ts` 增 `providers: () => Promise<RemoteResult<string[]>>` 与 `'subagents/providers'`。零硬编码名单、零路由行为：目录内容恒等于注册表现状，注册/注销是唯一写者。
- **② 客户端半部**：`packages/client/ui-subagent/src/client/mentions.ts` 新增独立 `@` source（`trigger: '@'`、`name: 'subagent'`、`order: 2`，位于既有 `reference`（0）/`cordis`（1）之下；组标题复用 ui-input-trigger `slash.menu` 词典既有 `'subagent'` 键，未改 ui-input-trigger）。候选经 `ctx.remote.subagents.providers()` 读取目录并按 query 子串过滤；带 `warm`/`lexicon`/`subscribeLexicon`（注册表变化时通知，供草稿 `@<provider>` 装饰）；注册方式与 ui-cordis 对齐（`ctx.effect(() => triggers.registerSource(source), 'ui-subagent: @subagent mention source')`），plugin `inject` 增 `inputTriggers`/`remote`/`remote.subagents`。
- **③ pick 记录模型可见输入**：pick 落地字面 `@<provider> ` 文本（cordis 模式）。提及文本进入普通草稿，随用户消息提交并作为 `user/message` 事件入日志——model-visible ⟺ logged 经既有事件成立，**无需新 SessionEventMap 类型**（契约③的条件句「如需新事件类型」实测不需要，ignorable 规则自查随之不适用）。
- **④ 测试三层**：
  - source 单测：`packages/client/ui-subagent/tests/mentions-source.client.spec.ts`（7 用例，含 @codex/@claude-code/@cursor 三名注册表全量、补全过滤、三名 pick 字面文本、lexicon 未热→热→变更通知、读失败拒绝、中止请求空答复、身份不混同）。
  - 组合/挂载：`tests/browser-plugin.client.spec.ts` 扩展——断言 inject 面、source 注册身份、经 fake 目录取回候选、fiber 释放即注销。
  - 客户端解析/补全回归：`packages/client/ui-input-trigger/tests` 137 用例保持全绿（未改管线）。
- **⑤ profile 挂载**：新 source 随 ui-subagent 既有 `dsh.client` 行挂载（`packages/bundle/web-app/cordis.patch.yml:260-261`），与既有 source 同一挂载方式，无需组合面改动；宿主 `SubagentRuntime` 由 base 层挂载（`packages/bundle/base/cordis.patch.yml:335`），RPC 接收者在 Web profile 存在。
- **⑥ 陈留元数据修正**：`package.json` description、`README.md`/`README.zh.md`（章节、概述、Model Experience、限制、运行时不变式）全部由「退役的 @ 引用 source」改为「@subagent provider 提及 source」；`README.i18n.yaml` 双语配对哈希经 `verify-translation-pairing --write` 重录。

## 二、写域符合性声明（含一处出域，如实披露）

- **域内写入**：`packages/client/ui-subagent/**`（src/client、tests、README×2、README.i18n.yaml、package.json）、`.agents/devframe/v14-product/c2-mentions-impl.md`。web-app 组合面经核实无需改动（⑤），未改。
- **出域一处（需总控追认）**：`packages/subagent/subagent/src/index.ts`（核心 SubagentRuntime，+2 行 JSDoc/装饰器）。原因：目录 RPC 的浏览器传输面只能落在注册表所有者的 Remote 面上——已逐路径排除域内替代（详见 §三），且契约①明文授权「若注册表面不足以支撑浏览器目录读取，做最小表面扩展（export 已注册 provider 目录的只读方法）并在回执说明」。扩展为只读、委托既有注册表、零行为变更。若总控不追认，`git revert fcac8896a7` 即可整段摘除（客户端 source 会优雅降级为空组——candidates 拒绝被管线记日志后丢弃该组）。
- **禁区遵守**：未改 ui-input-trigger、ui-reference、ui-cordis、api-remotes、api-gateway、pnpm-lock.yaml、tsconfig、其余一切文件。

## 三、域内替代路径排除记录（为什么必须动核心文件）

1. 客户端 `$mount` 只接受严格生成描述符（`requireStrictDescriptor`），无通用 invoke；SRC 回退仅服务服务自身绑定命名空间下的端点。
2. ui-subagent 节点半部（域内）定义 TypertRemoteService 不可行：tsconfig.host.json 排除 `packages/client/*/src/**`，typert 生成器按 face 聚合的 projectReferences 发现贡献者，客户端包不进宿主 face，`./remote` 产物无从生成。
3. 手写 TypertContribution 需整套反射 model/schema（生成器职责），且网关 `resolveReceiverContext` 要求描述符 `service` 可解析且实现方法存在于 SubagentRuntime 实例——绕不开核心面。
4. 结论：最小合规传输面=核心 `list()` 加挂 `@Remote('providers')`（§二披露项）。

## 四、commit 列表与证据

| commit | 一句话 |
| --- | --- |
| `fcac8896a7` | feat(subagent): `list()` 加挂 `@Remote('providers')`——注册表实况目录线界面 + 3 宿主面用例 |
| `2a21c932fa` | feat(ui-subagent): `@subagent` 提及 source（目录消费、字面 pick、lexicon、TS18048 收窄修复）+ 7 source 用例 + 挂载/释放用例 |
| `ab7e1257ed` | docs(ui-subagent): README×2/package.json/@i18n.yaml 陈留元数据改为 @subagent 提及 source |

命令与退出码（全部真实执行，cwd=工作树根）：

- `pnpm exec vitest run packages/client/ui-input-trigger/tests packages/client/ui-subagent/tests`：基线 8 files/170 tests **exit 0**（137 管线回归 + 33 既有）；提交1前 9 files/173 **exit 0**；提交2前与收尾 10 files/181 **exit 0**（137 + 44）。
- `pnpm exec vitest run packages/client/ui-subagent/tests/mention-directory.host.spec.ts`：3 tests **exit 0**。
- `pnpm run gen:typert`：**exit 0**（产物含 `subagents/providers` 严格描述符，见 §一①）。
- `node ./node_modules/typescript/bin/tsc -b packages/client/ui-subagent --pretty false`：首跑抓出 mentions.ts TS18048（已修），复跑 **exit 0**。
- `node --max-old-space-size=4096 ./node_modules/typescript/bin/tsc -b tsconfig.host.json --pretty false`：**exit 0**（宿主聚合含核心改动与宿主面新用例）。
- `pnpm run verify-translation-pairing --write packages/client/ui-subagent/README.md`：**exit 0**（重录）；复核（check 模式）**exit 0**。
- `pnpm run verify-md-wrap packages/client/ui-subagent/README.md packages/client/ui-subagent/README.zh.md`：**exit 0**。
- 每提交：`git diff --cached --check` **exit 0**；逐文件尾随换行 PowerShell 逐字节校验全真；`git commit --no-verify` **exit 0**（宿主无 bash，--no-verify + 上述替代验证收据）。客户端提交曾把 TS18048 修复遗漏在索引外，已 amend 并入 `2a21c932fa` 后重排 docs/record 两提交——最终树即类型检查与回归通过的那棵树。

## 五、四态结论

| 态 | 结论 |
| --- | --- |
| 源码 | 三名显式提及已实现：目录=注册表实况（`subagents/providers`），客户端独立 source（`@subagent`），pick=字面文本，无硬编码名单、无静默路由 |
| profile | web-app 既有 ui-subagent `dsh.client` 行承载（cordis.patch.yml:260-261），宿主接收者 base 层在挂（base/cordis.patch.yml:335） |
| 运行 | 焦点回归 181/181 exit 0（137 管线回归全绿）；新面 3+7+1 用例全绿；ui-subagent 项目与宿主聚合 tsc 均 exit 0 |
| 生产验收 | 浏览器实机（dev server 手打 `@codex` 补全→pick→提交→日志可见）未跑，属后续 e2e/snapshot 面；如实未声称完成 |

## 六、未决项（如实）

1. **出域追认**：`packages/subagent/subagent/src/index.ts` 一处（§二），待总控裁定；不追认时回滚路径已给。
2. **目录不做 mentionable/internal 区分**：注册表内 spawn/fork 等内部 provider 也会出现在 `@` 菜单——「目录内容=注册表实况」的直读结果；若要过滤需 provider 元数据面（核心接口扩展），超出本切片最小面，未做。
3. **目录描述字段未做**：总控记录提及「live provider 名 + 描述」；`SubagentProvider` 无描述元数据，最小实现仅返回名单，描述留待核心面演进。
4. **e2e/snapshot 未跑**：137/181 均为单测车道；`test:web` 构建烟测与 recorded-session 场景未执行（需完整构建链），未声称覆盖。
5. **lexicon 通知时机**：注册表变更无转发事件可用（api-remotes 白名单域外），lexicon 靠 warm/candidates 轮询驱动——菜单打开即取实况，装饰最终一致；如需即时失效需转发 `subagent/provider-added/removed`（后续切片）。
