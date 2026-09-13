# DSH 项目长期记忆（D:\dsh-devframe）

## 环境（Windows + Git Bash，每次都用得上）
- Node（不在 PATH）：`C:\Users\25313\.workbuddy-ai\binaries\node\versions\22.22.2-2\node.exe`
- Git（不在 PATH）：`C:\Users\25313\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd`，需要 `export PATH=...:$PATH`，否则 tsx 脚本里的 `spawnSync('git')` 会静默 SIGTERM。
- **没有 pnpm 在 PATH**：跑 `package.json` 脚本要直接 `node node_modules/tsx/dist/cli.mjs scripts/<name>.ts`（`scripts/verify-*.ts` 均可这样单跑）。
- **`git update-ref` 被环境 SIGTERM**（`git hash-object -w` 正常）→ `verify-translation-pairing --write` 必然失败；改文档后只能用纯 Node 复刻 blob 哈希写 `.i18n.yaml`（sha1("blob <len>\0"+content)），再用只读模式复验。
- tsdown 入口：`D:/dsh-devframe/node_modules/tsdown/dist/run.mjs`（用 Windows 路径，`/d/...` 会被 Git Bash 转坏）。

## 覆盖率门（CI 是真门禁）
- 必须显式 `--coverage`；只给 `--coverage.thresholds.100` 不会开启覆盖率且退出码仍 0（曾导致"假阳性全绿"）。
- 单包：`node node_modules/vitest/vitest.mjs run packages/<group>/<pkg> --coverage --coverage.include='packages/<group>/<pkg>/src/**/*.{ts,tsx}'`。
- 阈值是**逐文件 100%**；类型文件（如 `slots.ts`）与 `src/index.ts` 显示 0% 但不触发失败。
- 不可达的防御分支按仓库先例加 `/* v8 ignore next -- <理由> */`（参考 `packages/experimental/client-ui-agent-team/src/client/TeamAction.tsx:193`）。

## 文档约定
- 双语 README / Agent Note 必须是 `.md` + `.zh.md` + `.i18n.yaml` 三件套，且**两侧物理行数完全相等**（结构逐节对齐）。
- 交叉链接：EN 侧指向 `X.md`，ZH 侧指向 `X.zh.md`，且相对路径必须真实存在（放错目录会报 "link target diverges"）。
- Agent Note：`{lifecycle}/{class}/yyyy-mm-dd-topic.md`，implemented 骨架为 `## Problem` / `## Decision` / `## Alternatives considered` / `## Consequences`（可加 `## Testing`/`## Related`）；首三行固定，`# Agent Note: <title>` 与 `Status:` 在中文侧也保持英文。
- 非平凡改动必须配 Agent Note；改文档别用"previously/now"讲历史。

## 影子（Shadow）产品语义（用户已拍板）
- 侧栏「影子」触发器 = 打开该永久独立 agent 的**指定会话**，走标准 DSH 对话视图；永远同一个对话，**绝不 create、不在会话列表新增条目**。
- 指定会话由宿主启动时经 agent 路径创建，**不记 cwd** → `session/create` 必然 `session/conflict`；客户端唯一正确路径是 `sessions.open(id)`，未列出时先 `refresh()`。
- 「管理」按钮（仅宽侧栏）打开原面板（对话视图为默认 + 项目视图切换）。
- **指定会话从列表隐藏已落地**（2026-09-11，纯客户端）：`ISessions.markInternal(id)` → `SessionSummary.internal` → `ui-workspace` 的 `sessionVisible()` 过滤；影子入口每次 `readStatus()` 成功后打标。**刷新页面即可，无需重启宿主**。行仍留在 list store，因为 `open()` 要求会话已列出。
- 该「隐藏」曾试过四个载体，全部因结构性阻碍被否（勿再提）：① 给持久化 `origin` 加 `'shadow'` 值 —— 宿主是 **resume** 指定会话而非重建，新值到不了既有行；② 复用归档集合 —— 归档是用户动词，取消归档会复活不该出现的行；③ 让 `ui-workspace` 自持注册表 —— 依赖反向，且其他列表消费者照样列出；④ 宿主从 `session/list` 省略 —— 对每个客户端都消失且破坏 `open()` 前置条件。详见 `.agents/notes/implemented/feature/2026-09-11-internal-session-classification.md`。
- 遗留待用户拍板：打开失败的用户可见错误；宿主侧为指定会话补 cwd（补了 `create` 才能收编它）。
