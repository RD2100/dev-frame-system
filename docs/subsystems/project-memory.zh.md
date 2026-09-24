# 有界项目记忆

[English](project-memory.md) | 中文

项目记忆子系统实现有界 Obsidian 记忆：用户选定的 Vault 只保存经过选择的事实、偏好、经验与未解决问题——绝不保存执行历史或权威——且服务只管理仅追加的 `<vault>/devframe-memory/` 子树。其组合层提供 `ctx.projectMemory` 并注册三个模型工具（`memory_search`、`memory_read`、`memory_append`）；回执 seam 搭乘会话日志，冷重启从回放日志恢复。按出厂默认，该行以未配置、只读状态挂载，部署配置 Vault 根目录之前每次工具调用都报告 `MEMORY_UNAVAILABLE`。记忆内容是不受信任的上下文，绝不授予工具、权限或权威。[包 README](../../packages/experimental/project-memory/README.zh.md) 负责安装路径、层配置与模型体验。

## 服务面

`ctx.projectMemory` 是 Vault 服务。核心操作：

- `search` — 对单个作用域笔记正文做确定性、按字节计界的文本匹配；命中携带笔记 id、摘录、信任标签与新鲜度，`coverageComplete: false` 表示扫描达到上限，绝不表示知识不存在。
- `read` — 按 id 读取一条完整笔记及其信任标签与来源；`memory_changed` 或 `incomplete_note` 表示存储文件与其已提交回执不一致，应视内容为未验证。
- `append` — 独占创建、幂等地追加一条有界笔记；回执在 `created` 返回之前送达调用会话的日志，被拒绝的正文只点名筛查规则，绝不回显疑似秘密。

## 约定要点

每种失败模式都以稳定代码呈现在 `ProjectMemoryError` 上（`MEMORY_UNAVAILABLE`、`MEMORY_APPEND_DISABLED`、`MEMORY_NOTE_TOO_LARGE`、`MEMORY_CONTENT_REJECTED`、`MEMORY_PATH_REJECTED`，以及 request、query、workspace、note、receipt、scope、write 各族代码）；冲突或被外部修改的笔记是结果，绝不是静默覆盖。限额按 UTF-8 字节计数（默认 8 KiB 笔记、16 KiB 返回、10 条结果、200 个候选、2 KiB 查询），候选扫描是排序的确定性遍历，摘录只在完整码点上截断。笔记 id 是 `sha256(namespace, sourceEventRef)`，同一追加的每次重试都落在同一文件；文件以独占创建 `wx` 写入并 flush，绝不截断或替换。包含约束优先于信任：workspace id 是单个安全路径段，笔记 id 是 64 位十六进制摘要，每个路径组件都检查意外的 symlink/reparse 点，解析后的目标必须留在 Vault 根 realpath 之内。信任标签随每次命中与读取一同携带、绝不被提升——`confirmed` 用户偏好需要宿主提供的人工确认引用。

## 子系统边界

三个工具经组合层加入 [tools](tools.zh.md) 注册表，把出厂默认变成已配置 Vault 的行覆盖语义由[基础组合包](../../packages/bundle/base/README.zh.md)负责。回执 seam 搭乘 [session](session.zh.md) 日志而不是存储域：Vault 是用户选定的文件系统根，不是 JSON 域表，内存回执存储的持久化由宿主负责。筛查是一种缩减而非保证，召回是有界文本匹配——按设计不存在后台索引或嵌入。

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.zh.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxagentmemory--agentmemoryservice"></a>

### `ctx.agentMemory` — `AgentMemoryService`

Persistent memory service. Storage is optional at activation so a missing or unavailable backend degrades to explicit MEMORY_UNAVAILABLE errors while the host agent continues its ordinary task.

```ts cordis-catalog
/**
 * Record one task episode.
 * @param input - Bounded task facts and their memory scope.
 * @returns The durable episode row.
 */
async recordEpisode(input: EpisodeInput): Promise<MemoryEpisode>

/**
 * Upsert one semantic fact, superseding weaker old facts or marking equal conflicts.
 * @param input - Sourced fact fields and their memory scope.
 * @returns The durable fact row and its resolved lifecycle status.
 */
async upsertFact(input: SemanticInput): Promise<SemanticMemory>

/**
 * Register or version a procedure; candidates remain candidates until explicitly promoted.
 * @param input - Procedure steps, trigger, and scope.
 * @param status - Lifecycle status assigned to the new procedure.
 * @returns The durable procedure row.
 */
async registerProcedure(input: ProcedureInput, status: MemoryStatus = 'candidate'): Promise<ProceduralMemory>

/**
 * Retrieve ranked semantic, procedural, and episodic context under a byte budget.
 * @param request - Query, scope, and optional budget for the retrieval.
 * @returns Ranked context, rendered text, and its durable trace id.
 */
async retrieveContext(request: RetrieveRequest): Promise<MemoryContext>

/**
 * Delete a memory item immediately; deleted ids are absent from retrieval.
 * @param id - Durable memory identifier to delete.
 * @returns Whether a row existed and was deleted.
 */
async forget(id: string): Promise<boolean>

/**
 * Read-only trace inspection for diagnostics and evaluation.
 * @param id - Durable retrieval trace identifier.
 * @returns The trace row, or undefined when it is unknown.
 */
inspectTrace(id: string): MemoryTrace | undefined

/**
 * Return candidates for future consolidation without mutating active memory.
 * @param scope - Scope whose repeated episodes should be considered.
 * @returns Candidate procedure summaries backed by episode ids.
 */
consolidate(scope: MemoryScope): readonly ConsolidationCandidate[]
```

Source: [`packages/experimental/agent-memory/src/service.ts`](../../packages/experimental/agent-memory/src/service.ts)

<a id="ctxmemorylibrarygateway--memorylibrarygateway"></a>

### `ctx.memoryLibraryGateway` — `MemoryLibraryGateway`

Host service backing the generated `ctx.remote.library` namespace.

```ts cordis-catalog
/**
 * Read the current library status and file listing in one call.
 * @returns availability metadata plus the accessible files; an unconfigured
 *   vault yields an `UNAVAILABLE` status and an empty listing.
 */
@Remote('view') async view(): Promise<MemoryLibrarySnapshot>

/**
 * Inspect vault availability without touching any file.
 * @returns the same status object the model tool reports.
 */
@Remote('status') status(): Promise<LibraryStatus>

/**
 * List the accessible library files with an optional depth cap.
 * @param request - Listing options.
 * @returns the sorted file metadata rows.
 * @throws {@link ProjectMemoryError} with `MEMORY_UNAVAILABLE` when no vault
 *   is configured or the vault is inaccessible.
 */
@Remote('list') async list(request: MemoryLibraryListRequest): Promise<readonly LibraryFile[]>

/**
 * Read one library file for preview, with its real absolute on-disk path.
 * @param request - Relative path inside the vault (forward slashes).
 * @returns the file content and the absolute copy/reference target.
 * @throws {@link ProjectMemoryError} with the same codes as
 *   {@link readLibraryFile}; the absolute path is computed only after the
 *   path has passed the full containment and symlink validation.
 */
@Remote('read') async read(request: MemoryLibraryReadRequest): Promise<MemoryLibraryReadResult>

/**
 * Search the library by name and text content from the UI.
 * @param request - Non-empty query and an optional result cap.
 * @returns the bounded search hits.
 * @throws {@link ProjectMemoryError} with the same codes as
 *   {@link searchLibrary}.
 */
@Remote('search') async search(request: MemoryLibrarySearchRequest): Promise<readonly LibrarySearchResult[]>
```

Source: [`packages/experimental/project-memory/src/gateway.ts`](../../packages/experimental/project-memory/src/gateway.ts)

<a id="ctxprojectmemory--projectmemoryservice"></a>

### `ctx.projectMemory` — `ProjectMemoryService`

The project memory service. One instance is bound to one calling session's workspace identity and allowed scopes; construct it with a spec resolved by `resolveMemorySpec` and a host-owned receipt store.

```ts cordis-catalog
/**
 * Search one allowed namespace: deterministic filename order, bounded
 * candidate scan, bounded text matching, and explicit partial-coverage
 * reporting. Scope checks run before any note content is read; notes that
 * disagree with their receipt, are incomplete, or are superseded inside
 * the same namespace are excluded from automatic recall.
 * @param request - Scope, query text, and optional result cap.
 * @returns the bounded hits with coverage and truncation facts.
 */
async search(request: MemorySearchRequest): Promise<MemorySearchResult>

/**
 * Read one note by host-issued id within one allowed namespace. Unknown
 * ids, missing files, changed files, and incomplete files are each
 * reported honestly; nothing is chased across namespaces.
 * @param request - Scope and the host-issued note id.
 * @returns the honest read outcome for the note.
 */
async read(request: MemoryReadRequest): Promise<MemoryReadResult>

/**
 * Append one note: validate, screen, derive the stable id, check the
 * committed receipt, then create the file exclusively and commit the
 * receipt before returning `created`. The candidate body is never
 * regenerated; conflicting or externally changed files are never modified.
 * @param request - Scope, stable source reference, kind, candidate body,
 *   assertion status, optional snapshot, and optional superseded note.
 * @returns the append outcome with the note id and expected path.
 */
async append(request: MemoryAppendRequest): Promise<MemoryAppendResult>
```

Source: [`packages/experimental/project-memory/src/memory.ts`](../../packages/experimental/project-memory/src/memory.ts)
<!-- END GENERATED cordis-surface -->
