# 2026-06-26 Feishu Bug Records

## Avz6rluJkenUiBclttvcETu9nNb - user prompt image/text spacing

- Link: https://ccn53rwonxso.feishu.cn/record/Avz6rluJkenUiBclttvcETu9nNb
- Base record id: `recvmIdLrHJPZm`
- Bug: 复制图片到输入框，和文字一起发送后，会话详情里图片和文字间隔较远。
- Evidence: Feishu attachment `image.png` shows a narrow screenshot preview above the user text bubble with a large visual gap before the text.
- Cause: User prompt image thumbnails were rendered inside a fixed 80px square preview. Wide clipboard screenshots could make the preview area read as empty spacing before the following text bubble.
- Fix: Render single user prompt images as proportional thumbnails with a 160px column and 80px max height, while keeping multi-image grids compact at 80px columns.
- Verification:
  - `corepack pnpm --dir packages/agent/gui exec vitest run --environment jsdom shared/agentConversation/components/AgentTranscriptItemView.spec.tsx`
  - `corepack pnpm --filter @tutti-os/agent-gui typecheck`
  - Web check: opened `http://127.0.0.1:5173/`; page rendered Agent GUI without framework overlay. Current local workspace had no user image message to reproduce visually.
- Status: fixed locally
- Commit: `40cb83d1`
- Feishu status update: confirmed `已修复待打包`.

## QZHZrXdLje5vLNcl0o5c7J61ndb - agent link opens new browser node

- Link: https://ccn53rwonxso.feishu.cn/record/QZHZrXdLje5vLNcl0o5c7J61ndb
- Base record id: `recvngl9SFXOxy`
- Bug: 打开浏览器后再在会话里点击网页链接，会覆盖之前打开的浏览器窗口。
- Evidence: Feishu screen recording shows an existing browser node on Google search, then a conversation URL click navigates that same browser node to the new URL.
- Cause: Agent GUI `open-url` actions used the default workspace browser launch behavior, which reuses the current browser node when one exists.
- Fix: Pass `reuseIfOpen: false` for Agent GUI URL actions so conversation links launch a fresh browser node instead of replacing the current one.
- Verification:
  - `node --import ./apps/desktop/test/register-asset-stub.mjs --test --experimental-strip-types ./apps/desktop/src/renderer/src/features/workspace-agent/services/desktopAgentGUILinkActions.test.ts`
  - `corepack pnpm --filter @tutti-os/desktop typecheck`
  - Web check: opened `http://127.0.0.1:5173/`; page rendered Agent GUI. Existing local conversation link clicks were blocked by the current virtualized transcript/preview layer, so the browser-node behavior was verified by the targeted link action test.
- Status: fixed locally
- Commit: pending; final hash recorded in batch summary.
- Feishu status update: confirmed `修复中`.
- Feishu status update: confirmed `已修复待打包`.

## C9Ywrblb9epPvHctNLicN4Z6nJd - completed session still processing

- Link: https://ccn53rwonxso.feishu.cn/record/C9Ywrblb9epPvHctNLicN4Z6nJd
- Base record id: `recvnkVFkJKczo`
- Bug: 会话已完成但一直显示“正在规划下一步”，再发消息显示排队中。
- Evidence: Feishu attachment shows completed tool calls while the transcript still has the processing row and the composer send button remains busy/queued.
- Cause: Agent Activity snapshot projection mapped legacy Host DTO status from `session.status` alone. Runtime state can report lifecycle `active` with `currentPhase: idle` or `turnLifecycle.phase: settled`; ignoring those fields leaves Agent GUI with stale working/queued state.
- Fix: Normalize `status`, `currentPhase`, and `turnLifecycle.phase` together when projecting activity-core sessions into Agent GUI Host DTOs.
- Verification:
  - `corepack pnpm@10.11.0 --filter @tutti-os/agent-gui test -- shared/agentActivitySnapshotProjection.spec.ts`
  - `corepack pnpm@10.11.0 check:agent-activity-runtime-boundaries`
- Status: fixed locally
- Commit: `95b39cc0`
- Feishu status update: confirmed `修复中`.

## CQs9rF6GhekdMAcbDhsc1Q9PnWA - Create App session stops early / command detail empty

- Link: https://ccn53rwonxso.feishu.cn/record/CQs9rF6GhekdMAcbDhsc1Q9PnWA
- Base record id: `recvnD5oHgq1ot`
- Bug: 创建应用任务跑到一半自动停止显示完成，点击最后输出的“执行命令”无任何显示。
- Evidence: Feishu log bundle `tutti-logs-20260626-143851.zip` shows ACP event flow around the issue with `call.failed`, later `session.updated`, and no app crash; app-center snapshot shows the `系统监控` factory job failed validation because no `tutti.app.json` was produced.
- Cause: Same Agent GUI projection gap as above made runtime lifecycle/phase transitions unreliable in the transcript and composer state. The app factory itself marked the job failed after validation; the user-visible "completed/empty command" symptom came from the conversation state projection.
- Fix: Same shared status tuple normalization used for the completed-session issue.
- Verification:
  - `node /Users/wwcome/.codex/skills/feishu-bug-runner/scripts/feishu_bug_fetcher.mjs analyze /private/tmp/feishu-bug-runner/recvnD5oHgq1ot/tutti-logs-20260626-143851.zip --issue '创建应用 任务 跑到一半 自动停止 显示完成 最后输出 执行命令 无任何显示' --anchor '2026-06-26 14:38:42'`
  - `corepack pnpm@10.11.0 --filter @tutti-os/agent-gui test -- shared/agentActivitySnapshotProjection.spec.ts`
  - `corepack pnpm@10.11.0 check:agent-activity-runtime-boundaries`
- Status: fixed locally
- Commit: `95b39cc0`
- Feishu status update: confirmed `修复中`.

## MJHVrTjR2eqvnUcfV4ocT9AKnfe - new session shows previous prompt

- Link: https://ccn53rwonxso.feishu.cn/record/MJHVrTjR2eqvnUcfV4ocT9AKnfe
- Base record id: `recvnDMstUaTMO`
- Bug: 有时候新建会话会显示上一个会话的提示词。
- Evidence: Feishu attachment `image.png` shows the Agent GUI home composer after creating a new conversation, but the prompt input still contains the previous prompt text `AI 文档 打开应用`.
- Cause: When external node data cleared `lastActiveAgentSessionId`, the controller only moved the routing intent to `home`. It did not clear `activeConversationIdRef` or `activeConversationId`, so the composer could still read the previous session draft while the UI appeared to be on the new-conversation home screen.
- Fix: Treat an external empty `lastActiveAgentSessionId` as a real home transition: unactivate the previous session, clear the active conversation ref/state, clear loading/detail state, mark the composer as home, and reload draft composer options without echoing another data write.
- Verification:
  - `corepack pnpm --dir packages/agent/gui exec vitest run --environment jsdom agent-gui/agentGuiNode/controller/useAgentGUINodeController.spec.tsx`
  - `corepack pnpm --filter @tutti-os/agent-gui typecheck`
  - `corepack pnpm check:agent-activity-runtime-boundaries`
- Status: fixed locally
- Fix commit: `5a64b5a3`
- Feishu status update: confirmed `已修复待打包`.

## GB7lrt1N0eQmyxcxbvZcVQgEnxc - new session message lands in previous session

- Link: https://ccn53rwonxso.feishu.cn/record/GB7lrt1N0eQmyxcxbvZcVQgEnxc
- Base record id: `recvng5DWYjznF`
- Bug: 新建会话发的消息有时候会显示在之前的会话里。
- Evidence: Feishu attachment `image.png` shows a message typed from a newly created conversation appearing in the old `你好` conversation. The log bundle includes `messages.jsonl` entries where both `你好` and later `hi` share `agentSessionId=48ae216f-cbc5-4db2-8f96-02e9a635196e`, confirming the prompt was sent to the previous session rather than only rendered there.
- Cause: Same stale active-session state as above. After an external home transition, `submitPrompt` still read the old `activeConversationIdRef`, so it continued the previous session through `sendInput`/`exec` instead of starting a new session.
- Fix: Same controller synchronization fix. A regression test now clears `lastActiveAgentSessionId` externally, submits from the home composer, and asserts the controller calls activation with `mode: "new"` and never calls backend `exec` for the previous session.
- Verification:
  - `corepack pnpm --dir packages/agent/gui exec vitest run --environment jsdom agent-gui/agentGuiNode/controller/useAgentGUINodeController.spec.tsx`
  - `corepack pnpm --filter @tutti-os/agent-gui typecheck`
  - `corepack pnpm check:agent-activity-runtime-boundaries`
- Status: fixed locally
- Fix commit: `5a64b5a3`
- Feishu status update: confirmed `已修复待打包`.

## Hi5wrn9t0eg49tcHz9fcSMrznKh - task status colors in @ panel

- Link: https://ccn53rwonxso.feishu.cn/record/Hi5wrn9t0eg49tcHz9fcSMrznKh
- Base record id: `recvnESQ7oGQYI`
- Bug: @ 面板的任务列表里不同任务状态都显示成灰色，任务中心也需要统一颜色和文案。
- Evidence: Feishu attachment `image.png` shows `未启动`、`执行中`、`待验收` badges all rendered as the same gray badge.
- Cause: @ 面板和任务中心分别维护任务状态展示映射，且 `ui-rich-text` 的 issue badge 只给 completed/failed 类状态上色，running/pending 状态最终落到灰色。
- Fix: Add a shared issue-manager status presentation helper for badge variant、mention tone and normalized `data-status`; have @ 面板 consume it, extend rich-text issue badges with running blue and pending purple, and keep @ 面板 status copy aligned to task-center copy (`待开始` / `Todo`, `待验收` / `In review`, `已完成` / `Done`).
- Verification:
  - `corepack pnpm --filter @tutti-os/workspace-issue-manager test -- --test-name-pattern status`
  - `corepack pnpm --filter @tutti-os/agent-gui exec vitest run --environment jsdom agent-gui/agentGuiNode/AgentFileMentionPalette.spec.tsx`
  - `corepack pnpm --filter @tutti-os/ui-rich-text typecheck`
  - `corepack pnpm --filter @tutti-os/workspace-issue-manager typecheck`
  - `corepack pnpm --filter @tutti-os/agent-gui typecheck`
  - Note: `corepack pnpm --filter @tutti-os/agent-gui test -- AgentFileMentionPalette.spec.tsx` ran the full package and hit an unrelated timeout in `agent-message-center/WorkspaceAgentMessageCenterPanel.spec.tsx`.
- Status: fixed locally
- Commit: pending; final hash recorded in batch summary.
