# D4 官方 Skill / MCP / Schedule 能力审计

审计时间：2026-09-17
审计对象：`D:\dsh-upstream-latest`（commit `0d1f50007f9bca3f52b06e1c3074fa14d5fb0720`，v0.1.6-alpha.1）

---

## 1. Skill 模块

### 1.1 包结构
官方 DSH 的 Skill 能力体系位于 `packages/skill/` 目录下，包含以下 4 个独立的 npm workspace 包，协同提供完整的技能服务：

1. **`@deepseek-ai/dsh-skill`** (`packages/skill/skill`)
   - **角色**：核心服务定义与注册中心（Service Definition & Registry）。
   - **Cordis 挂载点**：向 Context 注入服务 `ctx.skills` (`SkillRegistry`)。
   - **职责**：维护跨 Host 与 Scope 分层的技能 Provider 列表，合并多源候选（Candidates），裁决同名胜出者，提供目录快照缓存（LRU）与变更广播事件 `'skills/change'`。

2. **`@deepseek-ai/dsh-skill-filesystem`** (`packages/skill/skill-filesystem`)
   - **角色**：本地文件系统技能发现 Provider（Service Provider）。
   - **依赖服务**：`['skills']`，可选挂载 `['fs']`。
   - **职责**：扫描多级物理/虚拟目录根，解析 Markdown + YAML frontmatter，基于 Chokidar 和文件系统变更事件进行实时文件监控与缓存失效。

3. **`@deepseek-ai/dsh-skill-badge`** (`packages/skill/skill-badge`)
   - **角色**：内置静态技能打包 Provider。
   - **依赖服务**：`['skills']`。
   - **职责**：提供官方 "powered by dsh" 徽章技能（`dsh-badge`），带本地图片资源，默认在 composition 中禁用。

4. **`@deepseek-ai/dsh-tool-skill`** (`packages/skill/tool-skill`)
   - **角色**：模型与用户交互 Consumer 端插件。
   - **依赖服务**：`['agents', 'tools', 'skills']`。
   - **职责**：向 `ctx.tools` 注册模型可见的 `skill` 工具；监听 `agent/pre-step` 在会话开头与技能变更时向模型上下文注入动态 `<system-reminder>` 技能目录；拦截用户输入的 `/<skill-name>` 快捷手势并直接注入技能指令内容。

**相关外围包**：
- **`@deepseek-ai/dsh-client-ui-skill`** (`packages/client/ui-skill`)：Web 客户端组件，负责在输入框键入 `/` 时的自动补全菜单（Fuzzy Match 排序）、技能标签渲染、以及会话历史中的 `Instructions` 展开折叠卡片。
- **`packages/api/session-controller/src/skill-catalog.ts`**：`ctx.sessionSkillCatalog` 暴露 `@Remote list(request: SkillListRequest)`，支持客户端 RPC 在不唤醒冷 Agent 的前提下读取当前 Session 可用的技能摘要。

### 1.2 主要 export 与 Config 类型

#### (1) `@deepseek-ai/dsh-skill` (`packages/skill/skill/src/index.ts`)
- **主要 Export 类与函数**：
  - `SkillRegistry`（默认导出 / 命名导出）：Cordis 核心 Service，挂载至 `ctx.skills`。
  - `isSkillName(name: string): boolean`：校验是否为 kebab-case 格式 `^[a-z0-9]+(?:-[a-z0-9]+)*$`。
  - `isModelInvocable(skill)` / `isUserInvocable(skill)`：依据 `SkillInvocationPolicy` 判定权限。
  - `renderSkillContent(skill)`：将加载的技能 Markdown 渲染为标准 XML 块（`<skill_content>` / `<skill_resources>` / `<skill_instructions>`）。
  - `escapeText(value: string)`：XML 转义工具函数。
  - `BUNDLED_SKILL_RANK = 600`：预置技能的标准优先级常量。
- **核心类型**：
  - `SkillInvocationPolicy`：`{ readonly modelInvocable: boolean; readonly userInvocable: boolean }`。
  - `SkillSummary`：调用中立的技能元数据摘要（`name`, `description`, `whenToUse?`, `invocation`, `source`, `provider`, `resourceBase?`, `path?`）。
  - `SkillCandidate`：Provider 提交给注册中心的候选条目，继承自 `SkillSummary`，增加 `rank: number` 与 `locator: unknown`。
  - `SkillDefinition`：完全加载后的完整定义，继承自 `SkillSummary`，增加 `content: string`。
  - `SkillProvider`：第三方或子系统接入必须实现的接口：
    ```ts
    interface SkillProvider {
      readonly name: string
      readonly list: (options: SkillLookupOptions) => Promise<readonly SkillCandidate[] | SkillProviderObservation>
      readonly get: (candidate: SkillCandidate, options: SkillLookupOptions) => Promise<SkillDefinition | undefined>
    }
    ```
  - `SkillProviderControl`：Provider 注册时获得的控制器，提供 `signal: AbortSignal` 和 `invalidate(): void`。
- **Config 类型**：
  - `Config`：`{ collectCacheMaxEntries?: number }`（默认 128）。
- **事件**：
  - `'skills/change'(): void`：无参通知，表明 Provider、运行时技能或文件可能发生变更，消费者应使用自身 `cwd`/`scope` 重新获取快照。

#### (2) `@deepseek-ai/dsh-skill-filesystem` (`packages/skill/skill-filesystem/src/index.ts`)
- **Export**：`apply(ctx, config)`, `FileSystemSkillProvider`, `Config` (Zod Schema & TS Type)。
- **Config 类型**：
  ```ts
  interface Config {
    providerName?: string // 默认 'filesystem'
    includeDefaultRoots?: boolean // 默认 true（是否自动包含 project、user、bundled 根）
    dshHome?: string // 默认 $DSH_HOME 或 ~/.dsh
    agentsHome?: string // 默认 $DSH_AGENTS_HOME 或 ~/.agents
    customSkillDirs?: string[] // 默认 []，自定义目录列表
    watch?: boolean // 默认 true，是否启用 Chokidar 监听
    watchUsePolling?: boolean // 默认 false
    watchStabilityThresholdMs?: number // 默认 200ms
    watchPollIntervalMs?: number // 默认 100ms
    watchMaxProjects?: number // 默认 128
    watchFollowSymlinks?: boolean // 默认 true
    bundledSkillDir?: string // 默认环境变量 DSH_BUNDLED_SKILL_DIR
  }
  ```

#### (3) `@deepseek-ai/dsh-tool-skill` (`packages/skill/tool-skill/src/index.ts`)
- **Export**：`apply(ctx, config)`, `Config` (Schema & TS Type), `SkillCatalogSource`。
- **Config 类型**：
  - `Config`：`{ catalogDescriptionMaxLength?: number }`（默认 500，下限为 3）。

### 1.3 发现与加载机制

1. **发现根与优先级（Local Discovery Priority）**：
   `packages/skill/skill-filesystem/src/index.ts` 按照硬编码的 Rank 阶梯从高到低决定同名冲突胜出者（Rank 数值越小优先级越高）：
   - **Rank 100 (`project-dsh`)**：`<projectRoot>/.dsh/skills`
   - **Rank 200 (`project-agents`)**：`<projectRoot>/.agents/skills`
   - **Rank 250 (`runtime`)**：通过 `ctx.skills.register()` 动态注入的运行时技能
   - **Rank 300 (`custom`)**：`Config.customSkillDirs` 配置的外部路径列表
   - **Rank 400 (`user-dsh`)**：`<dshHome>/skills`（自动跳过 `.system` 内部目录）
   - **Rank 500 (`user-agents`)**：`<agentsHome>/skills`
   - **Rank 600 (`bundled`)**：`Config.bundledSkillDir` 或 `dsh-skill-badge` 注册的预置技能

2. **Project Root 判定**：
   - 依赖当前 Session / Agent 的 `cwd`。
   - 从 `cwd` 向上逐级查找包含 `.git` 目录的最近祖先；若找不到任何 `.git`，则将传入的 `cwd` 自身视为项目根。
   - 当上下文中挂载了虚拟文件系统 `ctx.fs` 时，通过 `ctx.fs` 进行探测，以适配沙箱或远端工作区环境。

3. **技能文件结构规范**：
   - 命名规范：严格小写 kebab-case，匹配 `^[a-z0-9]+(?:-[a-z0-9]+)*$`。
   - 支持两种物理形式：
     - **目录 Bundle**：`<root>/<name>/SKILL.md`（其资源基路径 `resourceBase` 指向该子目录）。
     - **单文件 Flat Markdown**：`<root>/<name>.md`（其资源基路径 `resourceBase` 指向父 root 目录）。
   - **不支持深层递归**：明确不支持 `**/SKILL.md` 的嵌套发现，只扫描 root 目录的直接子项。

4. **YAML Frontmatter 规范与调用策略**：
   - 必须包含以 `---` 包裹的标准 YAML 头。
   - 必填字段：`name: string`，`description: string`。
   - 可选字段：`whenToUse: string`，`metadata: Record<string, unknown>`。
   - 权限控制字段（解析映射至 `SkillInvocationPolicy`）：
     - `disable-model-invocation: boolean`（若为 true，则 `modelInvocable = false`，默认 false）。
     - `user-invocable: boolean`（若为 false，则 `userInvocable = false`，默认 true）。
     - 严格校验：若存在驼峰命名 `disableModelInvocation` 或 `modelInvocable`，直接抛错并拒绝加载该技能。

5. **动态监听与热失效**：
   - **Chokidar 监控**：监控所有现存 root 目录及新增/删除的 `SKILL.md` 或 `<name>.md`。若目录当前不存在，则向上找到最近存在的祖先目录挂载轻量 `watchFile`，当缺失路径被创建时逐步过渡为 Chokidar 深度监听。
   - **模型工具操作响应**：监听 `fs/observed` 事件，当 Agent 调用内置 `write` 或 `edit` 修改了技能路径时，立即同步触发 `provider.observeHostMutation(path)`，进而调用 `control.invalidate()` 清除缓存。

### 1.4 与 agent-loop 的连接点

`packages/skill/tool-skill/src/index.ts` 通过两个并行的 `agent/pre-step` 钩子深入 Agent 循环：

1. **用户显式调用手势拦截（User-explicit Slash Gesture）**：
   - 在每个模型步骤执行前，拦截本次轮次中 `source.kind === 'user'` 的用户输入文本。
   - 正则扫描行首或词边界的 `/<name>`（如 `/deploy`）。
   - 若名称匹配注册中心中已有的 `userInvocable` 技能，则立即通过 `ctx.skills.get(name)` 加载完整内容，调用 `renderSkillContent()` 生成规范 XML 块：
     ```xml
     <skill_content name="...">
     <skill_resources>...</skill_resources>
     <skill_instructions>
     [Markdown 技能正文]
     </skill_instructions>
     </skill_content>
     ```
   - 构造一条 `SkillInvocationSource` 类型的上下文消息，追加在所有其它注入消息（系统提示词、规则等）的最末尾，直接作为模型本次推理的前置指令。
   - **此路径是 `disable-model-invocation: true` 技能的唯一加载途径**。

2. **动态 Session 技能目录注入与替换（Session Skill Catalog）**：
   - 仅当当前 Agent 拥有 `skill` 工具调用权限时生效。
   - 在会话启动的初次推理前，向对话历史追加一条 `<system-reminder>` 消息，列出当前所有 `modelInvocable: true` 技能的 `name` 和截断后的 `description`（格式形如 `- skill-name: description`）。
   - 对目录内容计算 SHA-256 摘要（Digest）。
   - 在后续的每个 `agent/pre-step` 中对比 Digest：若开发者在本地新增/删除了技能，或者技能描述被修改，系统会自动向会话追加一条带 `update: true` 的全量替换目录消息（`renderCatalogUpdate`），告知模型旧目录失效，使用新目录。
   - 若会话历史发生 Compaction（上下文压缩）导致旧的技能目录丢失，检测到后也会自动重发最新目录。

3. **模型显式加载工具 `skill`**：
   - 注册工具名称：`skill`。
   - 参数：`{ name: string }`。
   - 执行逻辑：校验名称合法性 -> 校验是否在当前 scope/cwd 下存在且 `modelInvocable: true` -> 调用 `ctx.skills.get()` 读取内容 -> 返回结构化数据并渲染为 `<skill_content>` 交付模型。

### 1.5 DevFrame 复用缺口

1. **运行时能力完备度**：
   - 官方 `@deepseek-ai/dsh-skill`、`@deepseek-ai/dsh-skill-filesystem` 和 `@deepseek-ai/dsh-tool-skill` 实现了极其完善的分层优先级、Chokidar 监控、`agent/pre-step` 自动注入与模型工具。
   - **结论**：若 DevFrame 后端采用官方 Cordis 运行时或复用其 Host 服务，**上述 3 个包可 100% 直接复用**，零重写成本。

2. **核心缺口（桌面客户端集成与交互）**：
   - **输入框交互支持**：官方虽然在 Web 端提供了 `@deepseek-ai/dsh-client-ui-skill`，但其与官方专有的输入框触发器 `@deepseek-ai/dsh-client-ui-input-trigger` 和特定 Session Hook 深度耦合。DevFrame 桌面版需要有自己的 `/` 快捷输入提示弹窗（Slash Command Popover）。
   - **本地技能管理配置面板**：官方没有提供图形化的“技能管理界面”（例如查看当前安装了哪些技能、开启/禁用指定技能、点击跳转打开 `SKILL.md` 源码、新增自定义目录 `customSkillDirs`）。DevFrame 需新增此类管理 UI。
   - **技能安装与导入**：官方目前依赖用户手动将文件拷贝至 `~/.dsh/skills` 或项目目录，缺少从 GitHub/ClawHub 或本地 Zip 一键导入技能的 GUI 流程。

---

## 2. MCP 模块

### 2.1 包结构
官方 DSH 的 Model Context Protocol (MCP) 相关实现位于 `packages/mcp/` 目录下，由两个核心包组成：

1. **`@deepseek-ai/dsh-mcp-client`** (`packages/mcp/mcp-client`)
   - **角色**：针对单个 MCP Server 的连接与工具桥接插件（Connection Bridge）。
   - **Cordis 规范**：每个外部 MCP 服务器在 `cordis.yml` 中作为一个独立的 plugin 实例加载。
   - **依赖服务**：`['tools']`，可选挂载 `['mcpResources', 'systemPrompt']`。
   - **职责**：
     - 管理 MCP SDK Client 实例的生命周期；
     - 负责 stdio（子进程）与 Streamable HTTP（SSE）的 Transport 创建；
     - 维护断线重连（指数退避）与启动健康检查；
     - 将远程 MCP Server 的 `tools/list` 发现结果自动转换为 Harness 的 `ToolDefinition` 并动态注册到 `ctx.tools`；
     - 将工具执行结果规整化，支持图片 Attachment 存储与不支持类型的安全降级；
     - 提取并发布 Server 端自带的系统提示词（`instructions`）。

2. **`@deepseek-ai/dsh-mcp-resources`** (`packages/mcp/mcp-resources`)
   - **角色**：跨服务器的 MCP 资源调度服务与共享工具集。
   - **Cordis 挂载点**：向 Context 注入服务 `ctx.mcpResources` (`McpResourceRuntime`)。
   - **职责**：
     - 维护当前作用域内所有已连接服务器的 `McpResourceProvider` 注册表；
     - 当作用域内至少存在一个可用的资源提供者时，向 `ctx.tools` 动态注册 3 个共享资源工具（`list_mcp_resources`、`list_mcp_resource_templates`、`read_mcp_resource`）；
     - 向 `systemPrompt` 的 `MCP_SERVERS` 区块动态注入可用的资源服务器名称列表。

3. **客户端 UI 现状**：
   - **官方无专用的 `ui-mcp` 包**！在官方 DSH 中，MCP 服务器的工具直接以原生工具卡片的形式呈现在对话流中，服务器列表仅通过 `cordis.yml` 静态配置，没有独立的前端管理面板。

### 2.2 连接方式（stdio / SSE）

MCP 客户端底层完全基于 Anthropic 官方 SDK（`@modelcontextprotocol/client`）实现，支持自动协议版本协商（默认优先采用 `2026-07-28` 规范，并向后兼容）：

1. **stdio 模式（本地进程）**：
   - 对应代码：`packages/mcp/mcp-client/src/transport.ts`。
   - 使用 `StdioClientTransport`。
   - 配置字段：`command`（可执行程序，如 `npx`、`node`、`python`）、`args`（参数数组）、`cwd`（工作目录）、`env`（环境变量字典）。
   - 特点：在正式启动前，SDK 会通过探测进程完成能力握手。

2. **Streamable HTTP / SSE 模式（网络端点）**：
   - 对应代码：`packages/mcp/mcp-client/src/transport.ts`。
   - 使用 `StreamableHTTPClientTransport`。
   - 配置字段：`url`（HTTP/HTTPS 端点，如 `http://localhost:3000/mcp`）、`headers`（HTTP 自定义请求头，如 `Authorization: Bearer ...`）。
   - 特点：支持现代 Streamable HTTP 以及基于 SSE（Server-Sent Events）的双向通信。

3. **连接生命周期与重试机制（Supervisor）**：
   - 对应代码：`packages/mcp/mcp-client/src/connection.ts`。
   - **指数退避重连**：
     - `reconnect.enabled`：默认 `true`。
     - `reconnect.initialDelayMs`：默认 `500ms`。
     - `reconnect.maxDelayMs`：默认 `30,000ms`（同时作为连接稳定窗口；若连接持续正常运行超过该时长，失败计数清零）。
     - `reconnect.maxAttempts`：默认 `10` 次。若连续重试 10 次全部失败，判定为彻底宕机，清空已注册工具并停止重试。
   - **启动失败控制**：
     - `failOnStartupError: boolean`（默认 `false`）。若为 false，初次连接失败不阻断应用启动，转入后台重试；若为 true，初次失败会导致插件激活抛错，触发 Cordis 回滚。
   - **工具列表变更热更新**：
     - 注册 SDK 的 `listChanged.tools` 回调。当远程服务器触发工具增删通知时，通过串行化队列 `syncChain` 原子替换 `ctx.tools` 上的工具集，避免由于网络抖动产生工具残留或空缺。

### 2.3 资源服务（resources）

1. **资源访问架构**：
   - 由 `@deepseek-ai/dsh-mcp-resources` (`packages/mcp/mcp-resources/src/index.ts`) 统一调度。
   - 各个 `mcp-client` 建立连接后，将其连接绑定的 `McpResourceProvider` 注册进 `ctx.mcpResources.register(serverName, provider)`。
   - 当第一个资源服务器注册时，动态向当前 Scope 注册 3 个共享工具；当最后一个服务器注销时，同步卸载工具。

2. **共享资源工具清单** (`packages/mcp/mcp-resources/src/tools.ts`)：
   - **`list_mcp_resources`**：列出指定 MCP Server 上的资源列表。参数：`{ server: string, cursor?: string }`。
   - **`list_mcp_resource_templates`**：列出资源 URI 模板（带参数的模板）。参数：`{ server: string, cursor?: string }`。
   - **`read_mcp_resource`**：读取指定 URI 的资源内容。参数：`{ server: string, uri: string }`。

3. **系统提示词联动**：
   - `mcp-resources` 自动向 `systemPrompt` 注册名为 `mcp-resource-servers` 的 section，注入当前可用的所有 MCP 资源服务器名称：
     > `## MCP resource servers\n\nUse list_mcp_resources, list_mcp_resource_templates, or read_mcp_resource with one of these names as the server argument: ["github", "web"].`

4. **资源限制**：
   - 仅支持按需（On-demand）拉取，**不支持**资源主动订阅（Subscriptions）或流式推送；
   - 文本资源作为普通工具输出返回；二进制资源被转换为描述性诊断文本，避免无效 token 消耗。

### 2.4 Config 类型与 Secret 处理

#### (1) Config Schema (`packages/mcp/mcp-client/src/index.ts`)
Config 为辨识联合类型（Discriminated Union）：
```ts
type Config = StdioConfig | StreamableHttpConfig

interface CommonConfig {
  serverName: string // 正则 ^[A-Za-z0-9_-]{1,32}$，同 scope 内唯一
  toolCallTimeoutMs?: number // 默认 60,000ms
  failOnStartupError?: boolean // 默认 false
  maxInstructionBytes?: number // 默认 32,768 字节
  reconnect?: {
    enabled?: boolean // 默认 true
    initialDelayMs?: number // 默认 500
    maxDelayMs?: number // 默认 30,000
    maxAttempts?: number // 默认 10
  }
}

interface StdioConfig extends CommonConfig {
  transport: 'stdio'
  command: string
  args?: string[]
  env?: Record<string, string>
  cwd?: string
}

interface StreamableHttpConfig extends CommonConfig {
  transport: 'streamable-http'
  url: string
  headers?: Record<string, string>
}
```

#### (2) 环境变量与 Secret 安全处理
- **父进程环境变量强力脱敏（Scrubbing）**：
  - 源码位置：`packages/mcp/mcp-client/src/transport.ts` 第 21-23 行。
  - stdio 模式启动子进程时，并不直接继承 `process.env`，而是使用 `@deepseek-ai/dsh-subprocess` 提供的 `scrubbedParentEnv()`：
    - 任何包含 `KEY`、`PASSWORD`、`SECRET`、`TOKEN`（大小写不敏感）的环境变量名，一律丢弃；
    - 所有以 `DSH_*` 开头的宿主内部环境变量，一律丢弃；
    - 仅保留标准系统基础变量（如 `PATH`、`HOME`、`USER` 等）。
  - 用户必须在 `config.env` 中显式配置目标 MCP Server 所需的密钥（如 `GITHUB_TOKEN`），显式声明的环境变量会覆盖脱敏后的系统环境。
- **HTTP Headers 保护**：
  - HTTP 模式下的鉴权头（如 `headers: { Authorization: "Bearer ..." }`）通过配置传入，在 Node.js 端由 `StreamableHTTPClientTransport` 处理，不向前端暴露。

#### (3) 工具名称规整化与安全隔离
- 源码位置：`packages/mcp/mcp-client/src/tools.ts` 第 81-87 行 `publicToolName`。
- 命名规则：`mcp__<serverName>__<rawName>`。
- 严格遵循 DeepSeek 函数名约束（长度不超过 64，字符集限定为 `[A-Za-z0-9_-]`）。
- 若包含非法字符或超长，系统进行清洗并截断，并在末尾附加基于 `serverName\0rawName` 的 12 位 SHA-256 哈希后缀（形如 `mcp__server__long_tool_name_abcdef123456`），防止不同工具在规整化后发生碰撞。
- 在与远程 Server 通信时，`tools/call` 始终发送未篡改的 `rawName`，公网模型与 Session 日志则使用清洗后的公共名称。

### 2.5 DevFrame 复用缺口

1. **核心逻辑复用性**：
   - `@deepseek-ai/dsh-mcp-client` 和 `@deepseek-ai/dsh-mcp-resources` 设计极为扎实，具备完善的重连、异常隔离、脱敏与超时控制。
   - **结论**：后端代码可以直接 100% 原样复用。

2. **DevFrame 桌面端缺口（重中之重）**：
   - **完全缺失 MCP UI 管理器（D7 任务范围）**：
     - 官方只有通过编辑 `cordis.yml` 配置文件添加 MCP Server 的方式，前端连查看当前有哪些 MCP 服务的列表都没有。
     - DevFrame 必须新增桌面管理界面：
       1. **MCP 服务器卡片/列表**：展示已配置服务器的运行状态（Connected / Reconnecting / Disconnected / Error）、所用 Transport、工具数量。
       2. **添加/编辑弹窗**：支持可视化表单输入 `command/args/cwd/env` 或 `url/headers`，内置格式校验。
       3. **连通性测试按钮**：在保存前进行临时 probe 握手，确认成功后再挂载。
       4. **工具/资源查看器**：展示当前 MCP 服务器向模型导出的工具名称、参数 Schema、描述以及可用 Resources。
   - **Secret 凭据持久化**：
     - 官方示例在 yaml 中使用 `!!js process.env.GITHUB_TOKEN`，在桌面应用中，用户通常需要图形化输入 Token。
     - DevFrame 需要将用户输入的敏感凭据安全存储到本地加密存储（或系统 Keychain），并在启动 MCP 客户端时安全解密注入，不能以纯明文形式散落在用户全局设置中。
   - **动态热重载机制**：
     - 用户在 GUI 中增删 MCP 服务器后，后端需要能够动态调用 Cordis 的 `ctx.plugin()` 加载或卸载对应的 `mcp-client` 实例，而不需要重启整个应用。

---

## 3. Schedule / Jobs 模块

### 3.1 包结构与定位差异（两者同时存在）
在官方代码库中，`jobs` 与 `schedule` **属于两个职责完全分离的子系统**：

| 子系统 | 目录 | 核心包 | 主要定位 |
|---|---|---|---|
| **Jobs** | `packages/jobs/` | `jobs`, `jobs-local`, `tool-jobs` | **后台长任务运行期**：用于当前会话内需要异步执行的命令或子 Agent（如后台运行 bash、长时间编译、后台子代理），提供类似操作系统后台 Job 的管理能力。 |
| **Schedule** | `packages/schedule/` | `schedule` | **会话持久化定时器/提醒**：用于在未来某个时间点或周期性向当前会话注入一条提醒提示词（Reminder），基于 Session Log 持久化存储。 |

此外，客户端对应存在两个独立的 UI 包：
- `packages/client/ui-jobs` (`@deepseek-ai/dsh-client-ui-jobs`)：会话顶栏的任务进度胶囊与下拉列表。
- `packages/client/ui-schedule` (`@deepseek-ai/dsh-client-ui-schedule`)：会话顶栏的定时提醒闹钟图标与待办列表。

### 3.2 任务定义格式

#### (1) Jobs 模块任务格式 (`packages/jobs/jobs/src/types.ts`)
- **任务标识**：`JobId`（形如 `bash-1`, `subagent-1`，由前缀与递增序号组成）。
- **任务生命周期状态**：
  `type JobStatus = 'running' | 'stopping' | 'completed' | 'killed' | 'failed'`
- **任务发起声明 (`JobStart`)**：
  ```ts
  interface JobStart {
    kind: 'bash' | 'subagent' | string // 任务类别命名空间
    label: string // 简短描述（如命令内容、代理委托描述）
    outputLimitBytes?: number // 模型可见输出截断阈值
    owner?: Agent // 所属的 live Agent 实例
    run(): JobHooks // 执行函数，返回控制钩子
  }
  ```
- **控制钩子 (`JobHooks`)**：
  ```ts
  interface JobHooks {
    cancel(reason?: string): void
    done: Promise<JobOutcome>
    readOutput?(): string // 流式增量读取输出（游标消费模式）
  }
  ```
- **模型端交互工具**（由 `@deepseek-ai/dsh-tool-jobs` 注册）：
  - `job_output({ job_id, wait?, timeout_ms? })`：读取输出（流式消费或最终结果）。
  - `job_list()`：列出当前 Agent 所属的所有活跃及已完成任务。
  - `job_kill({ job_id, reason? })`：请求取消运行中的后台任务。

#### (2) Schedule 模块任务格式 (`packages/schedule/schedule/src/types.ts`)
- **任务标识**：`ScheduleId`（唯一字符串）。
- **规则类型**（三选一，不可混用）：
  1. **`after`（相对延迟）**：
     `{ kind: 'after', prompt: string, afterSeconds: number, scheduledAt: string }`
  2. **`at`（绝对时间）**：
     `{ kind: 'at', prompt: string, scheduledAt: string }`
     - 允许输入 RFC 3339 字符串（如 `2026-09-17T18:00:00+08:00`）或本地时间对象 `{ date: 'YYYY-MM-DD', time: 'HH:mm:ss', time_zone: 'Asia/Shanghai' }`。
     - 入库前会被严格规范化为 UTC 四位年份的 RFC 3339 格式 `scheduledAt`。
  3. **`every`（固定间隔重复）**：
     `{ kind: 'every', prompt: string, everySeconds: number, scheduledAt: string }`
     - **硬性约束**：`everySeconds >= 300`（至少 5 分钟），禁止过高频度轮询。
     - **不支持 Cron 表达式**！仅支持基于创建基准锚点等间隔步进。
- **模型端交互工具**（由 `@deepseek-ai/dsh-schedule` 注册）：
  - `schedule_create({ prompt, after_seconds?, at?, every_seconds? })`
  - `schedule_list()`
  - `schedule_delete({ schedule_id })`

### 3.3 持久化与重启恢复

这是两者最关键的技术分水岭：

#### (1) Jobs 模块：**完全没有持久化（纯内存）**
- 源码位置：`packages/jobs/jobs-local/src/index.ts`。
- 所有状态保存在内存对象 `Map<JobId, TrackedJob>` 中。
- 官方设计明确阐述：
  > *"Jobs managed by the shipped in-process registry die with the harness process; durable execution across restarts needs a different backend implementing this contract."*
- **结论**：进程退出、崩溃或重启后，所有 Jobs 全部丢失，不会在重启后恢复。

#### (2) Schedule 模块：**基于 Session Event Log 的严格持久化与回放**
- 源码位置：`packages/schedule/schedule/src/persistence.ts`、`domain.ts`、`runtime.ts`。
- **持久化载体**：
  - 不使用独立的 SQL 数据库，而是直接使用 DSH 的会话事件日志（Session Event Log）。
  - 记录事件 `type: 'schedule/change'`，包含 3 种 operation：
    - `create`：记录完整的 `ScheduleRecord`。
    - `delete`：记录被删除的 `ScheduleId`。
    - `dispatch`：记录已触发派发（对于 `after`/`at` 是终止状态；对于 `every` 记录本次决策时间 `acceptedAt` 并步进下一次目标时间）。
  - 在每一次增删操作前，强制执行 `ctx.sessions.flush(session)` 落盘屏障。
- **重启恢复机制**：
  - 当会话重新被加载时，`ScheduleRuntime` 从事件日志通过 `foldScheduleEvents` 进行确定性重放（Fold）。
  - 恢复出当前活跃的定时任务列表与历史已分配 ID 集合。
  - **最新补发策略（Latest-only catch-up）**：
    - 如果会话离线期间跨越了多个周期，重复任务（`every`）**绝不补发所有的历史积压批次**，而是直接计算出离线期间的最后一次有效触发点，一次性前进到当前时间之后的最早周期，只补发 1 条最新到期提醒。
- **重要局限：Session-local 交付约束**：
  - Schedule 的所有触发器依赖当前 Session 处于**激活打开状态（Live Agent）**且处于 **空闲（Idle）** 阶段。
  - **没有外部通知通道**：若用户退出了应用，或者会话处于关闭/冷冻状态（Cold），后台没有独立的全局守护进程去发送邮件、短信或系统弹窗。只有当用户再次进入该 Session，Agent 被激活后，才会发现 Overdue 任务并立即通过 `agent.followup()` 发起一次会话内交互。

### 3.4 DevFrame 复用缺口

1. **针对后台任务（Jobs）的缺口**：
   - 官方当前的 `dsh-jobs-local` 仅满足“单个会话中开启子进程或子 Agent 并在后台等待”这一场景。
   - **DevFrame 缺口**：若桌面版需要支持跨重启持久化执行的长周期任务（例如下载大型模型、夜间定时全库索引重构），官方现有 `jobs-local` 无法支撑，必须编写一个基于 SQLite / 磁盘记录状态的 `DshPersistentJobRegistry` 服务提供者。

2. **针对定时调度（Schedule）的缺口（D8 任务核心前提）**：
   - **缺少 Cron 语法支持**：
     - 官方只有固定步长 `every_seconds`（最小 300s），无法满足“每周一上午 9 点运行”、“每天凌晨 2 点备份”等标准桌面调度需求。
   - **缺少应用级全局调度器（Global Daemon Scheduler）**：
     - 官方只绑定在具体某个正在运行的 `Agent` 实例上（Session-local）。
     - DevFrame 桌面端需要在 Electron 主进程或常驻后台 Service 中拥有一个**全局调度引擎**，即使没有打开任何聊天窗口，定时器也能准时唤醒，并在触发时通过操作系统原生通知（Windows Action Center / macOS Notification Banner）提醒用户，或自动在后台唤醒无头 Agent 执行任务。
   - **UI 呈现局限**：
     - 官方 `ui-schedule` 仅为一个在聊天会话右上角下拉的“待办闹钟列表”，缺少全局的定时任务管理看板（创建、暂停、编辑 Cron 表达式、查看历史执行日志）。

---

## 4. 总结与行动建议

### 4.1 可直接复用的接口与模块

| 模块 | 官方包名 | 可直接复用的能力 |
|---|---|---|
| **Skill** | `@deepseek-ai/dsh-skill` | 技能分层注册表、多 Provider 聚合、同名仲裁算法、缓存机制。 |
| | `@deepseek-ai/dsh-skill-filesystem` | 规范的本地技能文件扫描、YAML Frontmatter 解析、Chokidar 监控与模型文件写事件热失效。 |
| | `@deepseek-ai/dsh-tool-skill` | `skill` 模型工具、`agent/pre-step` 自动注入 `<available_skills>` 目录与变更自动更新、`/<name>` 快捷手势拦截。 |
| **MCP** | `@deepseek-ai/dsh-mcp-client` | 基于官方 MCP SDK 的标准连接管理、stdio 启动、环境变量安全脱敏 (`scrubbedParentEnv`)、指数退避重连、工具发现与名称规整化、图片附件桥接。 |
| | `@deepseek-ai/dsh-mcp-resources` | 跨 Server 的资源统一管理、`list_mcp_resources` 等 3 个共享工具、系统提示词联动。 |
| **Jobs** | `@deepseek-ai/dsh-jobs` / `jobs-local` / `tool-jobs` | 进程内后台命令异步执行、状态轮询、取消控制、会话内完成唤醒（适用于短周期后台命令）。 |
| **Schedule** | `@deepseek-ai/dsh-schedule` | 会话内的延时提醒与周期提醒、基于 Session Log 的确定性回放、到期自动插入对话流。 |

### 4.2 需要新增 UI 包的部分

1. **`dsh-desktop-ui-mcp`（MCP 桌面管理面板，对应 D7）**：
   - **现状**：官方完全缺失该界面。
   - **新增需求**：
     - MCP 服务器可视化列表与状态指示器（Connected / Connecting / Disconnected / Error）。
     - 新增/编辑服务器配置表单（支持 Stdio 与 SSE 双模式切换、参数列表、环境变量键值对输入）。
     - 连通性测试与工具列表即时预览卡片。
     - 敏感 Token / Secret 的安全掩码输入。

2. **`dsh-desktop-ui-skill-settings`（技能管理与导入面板，对应 D7）**：
   - **现状**：官方仅有会话内的 `/` 补全菜单与展开卡片，无全局配置界面。
   - **新增需求**：
     - 技能目录设置（配置与展示 `customSkillDirs`）。
     - 已安装技能浏览列表（查看每个技能的名称、描述、生效位置 project/user/custom、调用权限模型/用户）。
     - 外部技能一键安装/导入（从本地文件夹或 Git 仓库拉取至用户技能目录）。

3. **`dsh-desktop-ui-schedule-center`（桌面定时任务中心，对应 D8）**：
   - **现状**：官方仅有会话级只读通知抽屉。
   - **新增需求**：
     - 全局定时任务看板（区分会话级提醒与应用级常驻任务）。
     - 支持图形化或 Cron 表达式配置定时计划。
     - 执行历史日志查看器。

### 4.3 需要 DevFrame 侧额外适配的部分

1. **安全凭据存储（Secure Credentials Store）**：
   - MCP 需要传递大量外部服务的 API Token（GitHub Token、Database Password 等）。官方仅使用环境变量插值。DevFrame 桌面端应提供基于系统安全通道（如 Electron `safeStorage` 或本地加密库）的凭据持久化，避免在配置文件中以明文保存。
2. **操作系统原生桌面通知集成**：
   - 官方定时提醒只能在当前打开的会话窗口内以聊天气泡形式送达。DevFrame 应接入系统的 Native Notification API，在任务到期时发送系统横幅通知，点击后跳转至对应会话。
3. **Cron 表达式解析引擎**：
   - 官方 Schedule 模块硬性限制为固定秒数步长（且 `>= 300s`）。DevFrame 若要在 D8 交付专业定时任务，需在外围引入标准的 `cron-parser`，将自然日历规则计算为下一次触发的绝对时间（`at`）或由独立守护调度器驱动。

### 4.4 D7（技能/MCP UI）和 D8（持久定时任务）的接口前提

#### 面向 D7（技能 / MCP 桌面 UI）的接口前提：
1. **MCP 动态配置接口**：
   - 官方目前采用在 `cordis.yml` 中静态配置的方式。
   - **前提要求**：DevFrame 后端需要暴露一个 MCP 管理服务（例如 `DesktopMcpService`），能够通过 IPC / RPC 接收 UI 提交的配置，动态调用 Cordis 的 `ctx.plugin()` 和 `dispose()` 实现外部 MCP Server 的动态热挂载与卸载，而无需重启 DevFrame。
2. **技能 RPC 路由支持**：
   - 前端需要复用官方的 `ctx.sessionSkillCatalog.list()` 或新增 `ctx.skills.list()` 的桌面端 RPC 代理，使得主进程与渲染进程能够无缝拉取完整的技能列表。

#### 面向 D8（持久定时任务）的接口前提：
1. **架构路线选择**：
   - **路线 A（轻量方案：复用官方 Schedule）**：仅用于“会话内的定时提醒与循环问答”，只需补齐桌面通知和 UI 配置，直接使用 `@deepseek-ai/dsh-schedule`。
   - **路线 B（完整方案：应用级常驻任务调度引擎）**：
     - 独立于单个 Session 之外，基于 SQLite / 本地 JSON 存储；
     - 集成 Cron 解析；
     - 在 Electron 主进程中常驻运行；
     - 当任务到期时，若目标 Session 处于离线状态，可自动静默调用 Session Controller 打开会话并分发指令。
2. **接口前提**：
   - 若走路线 B，建议实现一个遵循 Cordis 规范的 `DesktopScheduleService`，不要直接修改官方 `@deepseek-ai/dsh-schedule`，以保持上游源码仓库的绝对洁净。
