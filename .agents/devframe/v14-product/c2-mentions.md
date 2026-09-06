# C-2 核验：显式 @codex @claude @cursor 提及解析/补全面（packages/client 最新实现）

- 工作树：`D:/dsh-devframe-v14-product-lead`（分支 `codex/v14-product-lead`，HEAD `6b31951491`）
- 核验范围：只读源码检索 + 只读 git 历史 + 只读运行单测；未做任何 git 写操作，除本报告外未创建/修改/删除任何文件。

## 一、@ 管线与全部 source 清单

### 管线核心

- **触发检测**：`packages/client/ui-input-trigger/src/core/detect.ts:48-76`（`detectTrigger`）。`@` 优先走共享语法 `activeAtToken`（detect.ts:6 导入，:50 调用），来自 `packages/context/file-reference/src/grammar.ts:26-35`：识别行尾 `@token` 与开放引号 `@"token…` 两种形式，`@` 处于其他 token 内部（如邮箱 `a@b.test`）不触发。`/` 由 detect.ts:61-74 向后扫描并带 URL 豁免。guard 三档（`packages/client/ui-input-trigger/src/types.ts:219-222`）：plain 双活，claimed 抑制 `/` 但 `@` 仍活，frozen 全灭。
- **注册表唯一入口**：`InputTriggerService.registerSource`，`packages/client/ui-input-trigger/src/client/service.ts:49`；(trigger, name) 重复注册抛错（:51-53）；roster 按触发字符过滤并按 `order` 排序（:92）；注册/注销向活会话控制器广播（:55-70）。`TriggerChar = '/' | '@'`（types.ts:32）——管线层面不存在第三个触发字符。

### 全部已注册 source（src，非测试；全仓 `registerSource` 调用点穷举）

| 触发字符 | name | 注册方 | source 定义 | 注册点 | 候选来源 |
| --- | --- | --- | --- | --- | --- |
| `/` | `command` | ui-commands | `packages/client/ui-commands/src/client/service.ts:148-156` | 同 :148（inline `ctx.effect`） | `ctx.remote.commands.list`（宿主命令目录；subagent 会话返回空，:141） |
| `/` | `skill`（order 2） | ui-skill | `packages/client/ui-skill/src/client/index.ts:137-153` | :188-194 | 每会话 skill catalog 拉取（宿主 dsh-tool-skill，pre-step 边界渲染）。**确认 ui-skill 注册的是 `/`，不是 `@`** |
| `@` | `reference`（showGroupTitle:false） | ui-reference | `packages/client/ui-reference/src/client/index.ts:44-114` | :115-116（effect 标签 `ui-reference: @ source`，任务锚点 :116 命中） | `@file`：`ctx.remote.fileReferences.list`；`@session`：`ctx.remote.sessionReferenceResolver.candidates`；两域并行、独立降级（:48-55） |
| `@` | `cordis`（order 1） | ui-cordis（`packages/extensions`，在 packages/client 之外但属默认 Web 组合） | `packages/extensions/ui-cordis/src/client/index.ts:150-169` | :170-171（effect 标签 `ui-cordis: @pluginId source`） | 本会话 plugin inventory 行（agentId 过滤 + query 包含匹配，:148-149）；pick 插入字面 `@<pluginId> `（:168）；带 lexicon/subscribeLexicon 参与草稿装饰 |

默认 Web 组合挂载：`packages/bundle/web-app/cordis.patch.yml:251-264`（ui-input-trigger / ui-commands / ui-skill / ui-subagent / ui-reference）、:232-233（ui-cordis）。

### ui-subagent 澄清（与任务前提的偏差，如实记录）

- **当前树 `packages/client/ui-subagent/src` 没有任何 `InputTriggerSource` / `registerSource`**（src 仅为 header lineage/catalog/composer）。全仓 `registerSource` 穷举中无此包。
- git 历史（只读）：`git log -S "trigger: '@'" -- packages/client/ui-subagent` 仅两条——`a27be43ac1`（2026-07-27 03:17，slash 系统引入）与 `ad3632f122`（2026-07-27 15:25，"feat(web): add file and session references"，该提交整体删除旧 ui-subagent 插件文件，其 @ source 退役，会话候选并入 ui-reference 的 session 域）。
- 陈留元数据：`README.md:38-40` 与 :88 仍描述「`@` reference source / picked candidate reaches the user message as literal `@label`」，`package.json:3` description 仍写 "…and '@' reference source"，`.agents/notes/implemented/feature/2026-07-27-web-subagent-conversations.md:76` 的 "existing `@label` source" 指退役前状态。**即：任务前提中「ui-subagent 注册运行中子代理 @ source」在当前树不成立**，当前 `@` roster 只有 `reference` 与 `cordis` 两个 source。

附注：`packages/client/ui-conversation/src/client/input/decorations.ts:60` 会给草稿中 `@` token 打装饰标记，属渲染侧装饰，不是 source 注册。

## 二、@codex/@claude/@cursor 专项结论

**结论：缺失。packages/client 最新实现（乃至整个 packages 树）不存在显式 @codex/@claude/@cursor 提及的解析或补全。**

搜索证据（ripgrep；node_modules/lib 产物经 gitignore 自动排除，vendor 不在 packages 下）：

1. 字面 `@codex|@claude|@cursor`：全 packages **0 命中**。
2. packages/client 大小写不敏感 `(codex|claude|antigravity)`：唯一命中 `packages/client/ui-settings-plugin-inventory/tests/components.client.spec.tsx:58`——测试夹具里的插件清单 entryId `'codex'`，与提及解析无关。
3. packages/client `cursor`（294 处）：全部为 CSS `cursor:` 属性（pointer/default/text/col-resize/zoom-in/crosshair/grabbing/not-allowed）、ANSI 终端光标重放逻辑（`ui-primitives/src/ansi.ts`）、连接 fixture 分页 cursor 变量——**记录并排除，均非提及解析**。
4. packages 树 `codex` / `claude-code` 命中均为非提及面，**记录并排除**：hooks 桥（`packages/hooks/hooks-codex`、`hooks-claude-code`，运行既有 hooks.json 的模型侧钩子桥；`hook-protocol/src/types.ts:48` 定义 `HookDialect`）；宿主 subagent 提供方（`packages/subagent/subagent-codex`、`subagent-claude-code`，注册到 `ctx.subagents`，默认 providerName `codex`/`claude-code` 且可配置）；preset 工具行（`packages/preset/agent-presets/presets/*.cordis.yml` 的 `tool-subagent-codex` / `tool-subagent-claude-code`）；LLM provider `openai-codex`（`packages/llm/llm-pi-ai`）。
5. `antigravity` 与 `agy`：全 packages **0 命中**。
6. packages/client `adapter` 命中均为 React/slot/session/model-selection 适配器；无任何 worker-adapter 提及解析/补全实现。
7. 唯二 `@` source（`reference`、`cordis`）候选来源均为宿主 RPC / 本会话插件清单，不含 provider 名单硬编码；`@` 补全的语义只到「文件/会话/插件 id」三种。

## 三、可自动测面结论

- 命令：`pnpm exec vitest run packages/client/ui-input-trigger/tests`（cwd `D:\dsh-devframe-v14-product-lead`；vitest v4.1.8）
- **exit code：0**
- **结果：Test Files 5 passed (5)，Tests 137 passed (137)**，Duration 3.61s，无失败清单。
- 文件：`apply.client.spec.ts`、`core-detect.client.spec.ts`、`core-menu.client.spec.ts`、`menu-view.client.spec.tsx`、`service.client.spec.ts`。
- 覆盖面：`@`/`/` 触发检测（quoted、claimed tier、word boundary、URL 豁免）、(trigger,name) 去重、roster 通知、菜单归约与渲染、pick/claim 路由——@ 解析器核心单测证据面全绿。

## 四、最小修复建议（若要补齐该专项；本切片不实现、不改码）

管线本身零改动即可承载新 source：detect.ts 的 `@` 检测与 source 名无关，roster 动态按触发字符过滤 + order 排序，(trigger,name) 唯一性已有守卫。设计选项：

1. **宿主侧来源契约（推荐）**：沿用 `sessionReferenceResolver` / `commands.list` 既有模式，新增宿主 Remote 域暴露「可提及的 subagent provider 目录」（live provider 名 + 描述，来自 `ctx.subagents` 实际注册表；providerName 本就可配置，如 `codex-safe`），客户端新建薄插件注册 `@` source 消费该 RPC。roster 不进客户端插件、不硬编码，避免与宿主注册漂移；pick 落地字面 `@name ` 文本 + codec，若需模型侧语义走 pre-step 校验并保持 Model-visible ⟺ logged。
2. **组合层挂载**：新 source 作为独立 client 插件经 `bundle/web-app/cordis.patch.yml`（或可选 Bundle）挂载，与 ui-cordis 的 `@` source 共存，order 区分分组，唯一性守卫天然防冲突。
3. **不做的事**：不在 ui-input-trigger / detect.ts 内置 provider 名单（违反「No hardcoded tunables in plugins」与 client 管线 presentation-only 定位）；不在 hooks/subagent 提供方包内做浏览器侧提及解析（模型侧桥与浏览器补全面是不同角色）。
4. 顺手记录项（非本切片）：ui-subagent `README.md:38-40`、:88 与 `package.json:3` 的 `'@' reference source` 陈留描述宜在后续 docs pass 清理。

## 五、四态结论与三层证据分列（组长汇总）

四态（对应 remaining/WORKLIST.md C2 行）：

| 态 | 结论 |
| --- | --- |
| 源码 | 专项提及解析/补全：缺失（§二 零命中证据）；@ 触发管线与既有 @ source（reference/cordis）存在且最新（§一）。宿主侧可提名词单天然来源在案：packages/subagent/subagent-codex、subagent-claude-code（providerName 可配置） |
| profile | n/a——专项无实现可挂载；@ 管线自身挂载在案 web-app/cordis.patch.yml:251-264、232-233 |
| 运行 | 解析器核心自动化绿：ui-input-trigger 137/137 exit 0（§三）；专项行为无实现故无测试对象 |
| 生产验收 | 不适用（缺失）；实现后另立切片验收 |

三层证据分列（车道纪律）：

| 层 | 内容 |
| --- | --- |
| ①请求参数 | workflow agent {provider:'huoshan-1', model:'glm-5.3-flash'} |
| ②宿主标签 | c2-mentions-verify |
| ③实际响应 | 回执自报 unknown（无自证能力）——provider 实证待总控侧日志载荷提取回填；model=glm-5.3-flash 为运行时声明；测试 137/137 exit 0 |

修复切片裁定待总控：§四 选项 1（宿主 subagent provider 目录 RPC + 薄客户端 @ source、组合层挂载）为最小合规路径；客户端 roster 硬编码已排除（违反 no-hardcoded-tunables）。
