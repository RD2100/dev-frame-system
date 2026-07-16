# 2026-06-12 Feishu Bug Records

## recvmdFQRJNXCm

- Link: https://ccn53rwonxso.feishu.cn/record/JvzqrNEm0egshlc8n9qcaiPLnQh
- Bug: 筛选执行中的任务筛选不出
- Cause: The backend status count projection exposed `inProgress`, but the generated API mapping and renderer domain mapping always converted it to `0`.
- Fix: Added `inProgress` to the OpenAPI/generated contracts and mapped backend counts through to the issue-manager shell.
- Verification:
  - `node --test --experimental-strip-types packages/workspace/issue-manager/src/ui/internal/shell/IssueManagerShellState.test.ts`
  - `go test ./services/tuttid/api/workspace -run TestGeneratedIssueManagerStatusCountsFromDomainIncludesInProgress -count=1`
  - `pnpm --filter @tutti-os/workspace-issue-manager typecheck`
  - `go test ./services/tuttid/api/workspace`
- Status: fixed
- Commit: `790a6b3b`

## recvmdTUXDFOOi

- Link: https://ccn53rwonxso.feishu.cn/record/Xe7xrsvGUesNpOckmJccelLQnUc
- Bug: 主任务的执行产物要显示主任务和所有子任务的产物
- Cause: Issue details only returned outputs for the latest run, so earlier task/subtask outputs were hidden.
- Fix: Aggregated outputs from every recent run in the issue detail response while keeping task detail scoped to the selected task.
- Verification:
  - `go test ./packages/workspace/issues -run TestServiceGetIssueDetailIncludesOutputsFromAllIssueTasks -count=1`
  - `go test ./packages/workspace/issues -run 'TestServiceRunLifecycleTransitionsTaskAndIssue|TestServiceCreateIssueRun' -count=1`
  - `go test ./packages/workspace/issues`
- Status: fixed
- Commit: `11bce7e1`

## recvmdxw2KHv19

- Link: https://ccn53rwonxso.feishu.cn/record/DaT5riT06el2YJcduQFcNO0EnXt
- Bug: 执行产物未明确显示可跳转的样式
- Cause: Output rows were buttons, but their presentation looked like passive metadata rows.
- Fix: Added file and arrow icons, explicit open label, title, and aria affordances to output rows.
- Verification:
  - `node --test --experimental-strip-types packages/workspace/issue-manager/src/ui/internal/issue/IssueManagerIssueSections.test.ts`
  - `pnpm --filter @tutti-os/workspace-issue-manager typecheck`
- Status: fixed
- Commit: `e729fee3`

## recvmdNP1ocybB

- Link: https://ccn53rwonxso.feishu.cn/record/MekNrAvD4elL7ocAxgicSKW7njc
- Bug: 已完成任务再次执行时子任务状态和执行范围异常
- Decision: Skipped duplicate execution per user instruction because the corresponding issue-manager completed-task work had already been completed.
- Verification: not rerun
- Status: skipped
- Commit: none

## recvlW9ftsk14j

- Link: https://ccn53rwonxso.feishu.cn/record/MkzirXlzSeIkvsc632fcBlJrnog
- Bug: 浏览器点击登录，输入邮箱后点击下一步仍提示要输入邮箱
- Investigation: Evidence points to a real Electron webview form/input behavior on the Google login page. I did not find a precise, testable code path from the screenshot and existing unit coverage.
- Status: not fixed; needs Electron runtime reproduction or richer webview diagnostics before changing code.
- Commit: none

## recvm0NbzTEqfV

- Link: https://ccn53rwonxso.feishu.cn/record/CGvgrN2cmeyCYHcJjT9cuEOmnLg
- Bug: 浏览器里创建飞书文档后本地未显示/未跳转文档详情
- Cause: BrowserNode guest `open-url` events requested `reuseIfOpen: false`, so target-blank/window-open document URLs launched beside the current browser instead of reusing the current local browser context.
- Fix: BrowserNode now emits guest open-url events with `reuseIfOpen: true`; workspace-app-specific window-open behavior remains unchanged.
- Verification:
  - `node --test --experimental-strip-types packages/browser/workbench-node/src/electron-main/electronMain.test.ts --test-name-pattern 'blocks cross-origin|converts guest preload open-url|registerBrowserNodeElectronMain routes guest open-url'`
  - `node --test --experimental-strip-types apps/desktop/src/main/ipc/workspaceAppWindowOpen.test.ts`
  - `node --test --experimental-strip-types apps/desktop/src/renderer/src/features/workspace-workbench/services/internal/workspaceBrowserService.test.ts apps/desktop/src/renderer/src/features/workspace-workbench/services/internal/contributions/appCenterWorkbenchContributionFactory.test.ts`
  - `pnpm --filter @tutti-os/browser-node test`
- Status: fixed
- Commit: `a8d486a2`
