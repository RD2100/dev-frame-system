# Handover doc: Shadow Conversation Entry

English | [中文](handoff-shadow-conversation.zh.md)

> Handover time: 2026-09-11. Previous model: DeepSeek (glm-5.3-flash); the main session ran in the DSH Web GUI (127.0.0.1:3080, inside the host process). Workspace: `D:\dsh-devframe` (all paths are relative to this root unless written as absolute).

---

## 1. The final semantics of the user's request (read this first, do not repeat the mistakes)

The user's request converged step by step in that session; every step rejected the previous implementation. **Final semantics**:

> **The Shadow = one permanent, independent agent.** The sidebar "影子" (Shadow) button opens its own one fixed conversation (the designated session), rendered with the standard DSH session UI; every click enters **the same** conversation; it must **not** create a new session per click, and it must **not** produce junk entries like "Ungrouped/New chat" in the session list.

Implementations explicitly rejected by the user (do not go back to these):
1. ❌ A self-made popup chat panel (plain text lines + polling) — "你搞的是个什么东西？" ("what on earth is this thing you built?")
2. ❌ Any self-made dialog replacing the standard session view — the Shadow must use the **exact same** standard conversation UI as the main chat.
3. ❌ Pointing at the old designated session session-8c2ada33 (with full history) — the user asked to "start a new one"; it was switched to a new designated session (see §4 config).
4. ❌ Creating a brand-new session per click — that would add an "Ungrouped" category and "New chat" labels in the session list; the user explicitly refused.

Retained secondary entry: next to the wide sidebar's "影子" (Shadow) trigger there is a small **"管理" (Manage)** button (`data-shadow-manage`) that opens the original dialog (status + project management + read-only conversation area) as a secondary entry.

---

## 2. Current code state (the exact position at handover)

Package: `packages/experimental/client-ui-shadow-entry` (`@deepseek-ai/dsh-experimental-client-ui-shadow-entry`)

### ⚠️ Unfinished state: tests are currently red
The last all-green run (55/55 + the 100% coverage gate + tsc + bundle rebuild) was on the "create a session per click" version. After that I changed two more files and **have not re-run the tests**:

1. `src/client/mount.ts` — finished (final semantics): `onOpenConversation` = `readStatus` → if not listed, `refresh()` → `open(sessionId)`. **Never call `sessions.create` again** (reason in §3).
2. `tests/shadow-mount.client.spec.ts` — only the bench stub was changed (`sessions` gained `list`/`refresh`, a new bench option `sessionNotListed`); **the assertion array has not been updated yet**; it still asserts the old adopt semantics `sessions/create:session-shadow`, so it will fail.

### First step for the successor: finish the spec (about 15 minutes)
- Change the expectation array of `registers one disposable footer action...` to (create removed):
  ```
  ['shadow/readStatus',
   'shadow/openProject:D:/projects/beta',
   'shadow/sendToController:ws-1:ship it',
   'shadow/releaseProject:ws-1',
   'shadow/readConversation:{}',
   'shadow/postMessage:hello shadow',
   'shadow/readStatus',
   'sessions/open:session-shadow']
  ```
- Add the branch test (the coverage gate requires it; the code has exactly 4 paths: ok+listed / ok+not-listed / readFailure / no sessionId):
  ```ts
  it('opens the designated session without create when it is not listed yet', async () => {
    const b = await bench({ sessionNotListed: true })
    const face = (b.entry()!.inject as unknown as () => { onOpenConversation: () => Promise<void> })()
    await expect(face.onOpenConversation()).resolves.toBeUndefined()
    expect(b.calls).toEqual(['shadow/readStatus', 'sessions/refresh', 'sessions/open:session-shadow'])
  })
  ```
- The existing `does not adopt a session when the status read fails or names no session` (the readFailure and sessionIdMissing arms, expecting `['shadow/readStatus']`) stays unchanged.
- The `create` member of the sessions stub in the bench is now called nowhere and may stay or be deleted (test code; does not affect the coverage gate).

### Then run the three checks
```
# 1) 测试 + 逐文件 100% 覆盖率门
node_modules\vitest\vitest.mjs run packages/experimental/client-ui-shadow-entry --coverage.thresholds.100 --coverage.include='packages/experimental/client-ui-shadow-entry/src/**'
# 2) typecheck
node_modules\typescript\bin\tsc -b packages/experimental/client-ui-shadow-entry/tsconfig.json
# 3) 重建 bundle（必须，否则 GUI 看不到改动）
cd packages\experimental\client-ui-shadow-entry
node D:\dsh-devframe\node_modules\tsdown\dist\run.mjs
```
Once everything is green, **just have the user refresh the page** (pure client changes; no host restart needed).

### Every file changed in that session (all uncommitted, stacked on top of the daytime session's large uncommitted set)
- `packages/experimental/client-ui-shadow-entry/src/client/mount.ts` — inject gained `'sessions'`; the face gained `onOpenConversation` (the refresh-then-open version, see above).
- `src/client/slots.ts` — the face gained `onOpenConversation(): Promise<void>` (JSDoc: the fixed conversation of the permanent independent agent).
- `src/client/ShadowCard.tsx` — the trigger's onClick → `void onOpenConversation()` (the trigger no longer opens the panel); wide mode gained a "管理" (Manage) button that opens the panel; the dialog became a large centered conversation-first view (default chat view + `[data-shadow-view-toggle]` to switch to project management).
- `src/client/ShadowCard.module.css` — `.trigger` (flex:1), `.manageButton`, `.rail .trigger` (flex:none), the centered dialog, `.chatPane/.composer/.chatInput`, etc.
- `src/client/locales.ts` — `trigger.aria`='打开影子对话'/'Open the Shadow conversation'; `trigger.manage`='管理'/'Manage'; plus `panel.projectsTab`, `panel.close`.
- `tests/shadow-card.client.spec.tsx` — 29 cases all green: the `openPanel` helper now clicks "管理" to open the panel; the `showProjects(b)` helper clicks the view toggle; the trigger asserts the name `打开影子对话`; new view round-trip/close cases. The bench already includes `onOpenConversation: vi.fn(async ...)`.
- `tests/shadow-mount.client.spec.ts` — see above, **to be finished**.
- **Not done**: the package README.md / README.zh.md have not been updated to the "permanent independent agent conversation entry" semantics (bilingual lines aligned); this change has no Agent Note yet (repo rules require a note for non-trivial changes; the existing `.agents/notes/implemented/bug-fix/2026-09-10-shadow-conversation-reachability.*` triplet covers the conversation wiring — the trigger-semantics change can update that note or add a new one).

---

## 3. The critical root cause just discovered (the successor must know this)

**The `session/create` RPC always fails for the designated Shadow session**:

```
POST /api/session/create  {args:{request:{sessionId:"session-0e48cb66-..."}}}
→ {"ok":false,"error":{"code":"session/conflict",
   "message":"session \"...\" records no cwd and cannot be adopted for \"D:\\dsh-devframe\""}}
```

The Shadow agent creates the designated session at host startup **without recording a cwd**, while create's adopt path requires an existing session's recorded cwd to match the request cwd → always conflict. The earlier create "success" against the old session session-8c2ada33 happened because that session had recorded a cwd.

**Conclusion**: the only correct client path to open the Shadow session = `open()` (with `refresh()` as the fallback), never `create()`. If create must ever be used (for example the session is not in the list and refresh cannot fetch it), the correct fix is host-side: pass a cwd when `shadow-controller/src/shadow-agent.ts` creates the designated session (the ensureSession call site is around line 202, right after `const id = SessionId(designation)`).

Also: `open(id)` "fails loud" for ids not in the list (the contract says unknown ids fail loud); `refresh()` fetches the authoritative list exactly for this race. If the error is swallowed by `void onOpenConversation()`, the symptom is "click and nothing happens" — in the current implementation a readStatus failure / missing sessionId returns silently (deliberate), and an open failure becomes an unhandled rejection (visible in the console). If a user-visible error is needed, consider adding an error channel to the face later.

---

## 4. Environment, paths, and live state (all verified in practice)

### Binaries and commands
- Node (not on PATH): `C:\Users\25313\.workbuddy-ai\binaries\node\versions\22.22.2-2\node.exe`
- Git (not on PATH): `C:\Users\25313\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe`
- Only Windows PowerShell 5.1 (`powershell.exe`); **no pwsh 7**. Note that `Set-Content -Encoding utf8` writes a **BOM**; to write without one use `[System.IO.File]::WriteAllText($path,$text,[System.Text.UTF8Encoding]::new($false))`.
- The tsdown entry is `dist/run.mjs` (not run.js).

### Host and configuration
- Host supervisor state: `C:\Users\25313\.dsh\dsh-web-supervisor.json` (contains url+token, startedAt, restartCount). The host was restarted at 2026-09-11T07:17:49Z and **has loaded the new designated session**.
- Deployment patch (the Shadow designation lives here): `C:\Users\25313\.dsh\profiles\web\devframe-deployment.yml` → `shadowSessionId: session-0e48cb66-32d0-413f-a034-904e8997f6d5` (in effect, confirmed by probe). **That file currently carries a UTF-8 BOM** (I broke it once; the YAML parser tolerated it and the probe works, but it is worth removing the BOM and keeping the trailing newline). A backup of the original sits in the same directory as `devframe-deployment.yml.bak.20260910-shadow-reset`.
- Shadow routing configuration facts: `shadowSessionId` is a `shadow-router` Config field, and `devframe-deployment.yml` is the last `--patch` override layer; the in-repo `devframe-profile` patch declares the triplet shadow-router / shadow-controller / shadow-agent (around lines 26-39 of `packages/experimental/devframe-profile/cordis.patch.yml`).

### Live RPC probe (verified working envelope format)
```
# 先拿会话 cookie
Invoke-WebRequest -Uri "{base}/?token={token}" -SessionVariable ws
# POST，信封 method 必须写完整端点名；args 按参数名；返回 RemoteResult
POST {base}/api/shadow/readStatus
body: {"type":"client-request","rpcId":"p4","method":"shadow/readStatus","payload":{"args":{}}}
→ {"ok":true,"value":{"mounted":true,"shadowSessionId":"session-0e48cb66-...","shadowLive":true,"authorizedRoots":["D:\\dsh-devframe"],"bindings":[]}}
```
The route is the **slash** form `/api/shadow/readStatus` (the dotted form 404s). Write methods' args look like `{"request":{...}}` (keyed by the parameter name `request`).

### Host-side architecture facts (do not re-derive)
- `shadow-controller/src/shadow-agent.ts`: at host startup it create-or-resumes the designated session and runs the Shadow agent (Fix B: `await this.ctx.get("loader")?.await()` before ensureOnce, against the startup race; the fix is already in lib).
- The client `ctx.sessions` runtime is `ClientSessions` (implementing `ISessions`), but at the **type layer** it shares a declaration merge with the host `dsh-session`'s `SessionStore`, so the property proxy's type is wrong → always funnel through `ctx.sessions as unknown as ISessions` (the current mount.ts state). The `ISessions` contract lives in `packages/api/session-controller/src/client/contract/sessions.ts`: `list` (ObservableSnapshot, `SessionListState.ids`), `open(id)`, `refresh()`, `create({workspaceId?,cwd?,sessionId?})`.
- mount.ts's `inject` export (the informational dsh.client manifest) is now `['remote','slots','locale','sessions']`; the actual cordis injection is `ctx.inject(['remote.shadow','slots','locale','sessions'], registerUi)`.
- The Web GUI is served the package through `lib/client.js` (the rev parameter); **after a tsdown rebuild, refreshing the page is enough** to see the new client code — no dev:web, no host restart. Only a host restart re-reads the yml config.

---

## 5. Successor action list (in order)

1. **Finish the spec** (the expectation array from §2 step one + the not-listed branch test).
2. **Run the three checks** (vitest+coverage / tsc / tsdown), all green.
3. **Have the user refresh the page** and click "影子" (Shadow) to verify: it should open the standard conversation of session-0e48cb66 (a clean empty session); repeated clicks enter the same one; the session list gains no new entries.
4. **Close out the docs**: update the package README.md/README.zh.md (bilingual lines aligned) to the final semantics; update/write the Agent Note (trigger semantics: permanent independent agent conversation + the create-conflict root cause + the open/refresh path).
5. **Known leftovers** (propose to the user as needed; do not expand on your own):
   - The designated session will have one entry in the session list (the title is auto-generated after the first message; it previously showed "New chat"). The user may ask to **hide it from the list entirely** — that requires changing the list filtering of the sessions domain (object layer/host), an independent design decision needing the user's sign-off.
   - The Shadow agent creates the session without recording a cwd (the host-side fix option in §3).
   - Click failures are currently silent to the user (void-swallowed); if a visible error is required, the face needs an error channel.

## 6. User preference reminders
- Communicate in Chinese throughout; results first, reasons after; do not dump log hashes.
- The user is a "hands-on, look at the effect" type: after each change, state clearly "what you do now" (refresh the page / restart the host).
- **Tell the user before restarting the host** (it is the GUI they are using; and this session itself runs inside the host process — killing the process kills yourself).
- Do not treat governance-style actions (hiding session-list entries etc.) as this task's goal or expand on your own — the final semantics are in §1; ask first about anything beyond it.
