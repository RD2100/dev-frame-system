# mock adapter 最小接口确认（lead 遗留步骤补齐）

前任组长 9fa566f7 在 design.md §1 `lib/mock-adapter.mjs` 条目中把适配器方法写作 "`run`"，
其被打断前正在确认真实接口。本组长从 src 实证补齐（commit 4fce69f194 树内代码，只读审读）：

- **基类**：`LlmAdapter`（`packages/llm/llm/src/index.ts` L193-275，导出自 `@deepseek-ai/dsh-llm`）。
  唯一抽象/必须实现的方法是 **`stream(options: GenerateOptions): AsyncIterable<StreamChunk>`**
  （L274）。其余成员均有基类默认实现，无需覆写：`providerInfo`、`providerRetryPolicy`、
  `imageRequestPricing`、`listModels`、`resolveModel`、`prepareCall`。
- **注册**：`ctx.llm.registerAdapter(['mock'], adapter)`（`LlmRuntime.registerAdapter`，
  packages/llm/llm/src/index.ts L380；返回 disposer）。路由名 `'mock'` 与全部测试先例一致。
- **agent 创建**：`ctx.agentLoop.create(SessionId(id), { provider: 'mock', model: 'mock' })`
  （`SessionId` 自 `@deepseek-ai/dsh-session` 导入，packages/core/session/src/types.ts L24）。
- **行为**：`stream` 为 async generator，首次拉取即
  `throw Error('ACCEPTANCE_LLM_TOUCHED...')`、绝不产出 chunk——任何场景触达 LLM 即 fail-loud
  （design §0 无 LLM 触碰不变量）。
- **约束**：实现自包含于 harness `lib/mock-adapter.mjs`，禁止从任何 `packages/**/tests`
  路径导入（零触碰禁区）。

Worker 实际交付（harness commit d6e3f9d534）与本确认一致：`AcceptanceMockAdapter extends
LlmAdapter` 只实现 `stream`，`registerMockAdapter(ctx)` 封装注册。

## 运行解析事实（lead 实测佐证）

- harness `.mjs` 在 `node --import tsx/esm` + `TSX_TSCONFIG_PATH=<tree>/tsconfig.json` 下，
  `@deepseek-ai/dsh-*` 经 tsconfig.base.json paths 解析到 workspace src；`tsx/esm` 子路径导出
  存在（`./dist/esm/index.mjs`，tsx ^4.22.4 为根 devDependency）。
- 七场景全部实际运行通过该解析（S1-S7 真实退出码与证据见 results.md）。
