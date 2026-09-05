---
description: 机器重启后全量基线重认证（P22 归档，验证域）：build 绿；experimental+extensions sweep 130 文件 1256P+1S 绿（agent-hierarchy 40/40 专项）；gen-cordis-catalog 0 违规（附带派生文档刷新 3 文件）、test:docs 15/15、verify-cordis-config 133、verify-package-invariants 39；快照 3 文件抽样 88F 两轮同数同签名=R5 B 族 Windows 残余延续，非重启漂移（A=0、C=0）。
---

# 重启后基线重认证（postrestart certification）

- 执行者：L-Verify（总控派单，验证域）。分支 `p/postrestart` @ main `526e773b23`（"dispatch postrestart certification and fingerprint engine chains"）。
- 纪律：三层规则（fail-loud、单一命令通道、隔离边界）；隔离 home `C:\Users\25313\.dsh-builtbin` 沿用；生产与既有隔离 home 未触碰。
- **汇总：8/9 项绿；1 项红（快照抽样）经复跑+签名对表判定为 R5 已知 Windows 宿主残余（B 族根）延续，非重启环境漂移，fail-loud 单列**。

## 认证矩阵（逐命令 exit 码 + 计数）

| # | 命令 | exit | 计数 | 判定 |
| --- | --- | --- | --- | --- |
| 1 | `pnpm install --frozen-lockfile` | 0 | Done in 6s | 绿 |
| 2 | `pnpm run build` | 0 | `recorded 220 client artifact(s)`；`bin.js=True` | 绿 |
| 3 | `pnpm exec vitest run packages/experimental packages/extensions` | 0 | **Test Files 130 passed (130)；Tests 1256 passed / 1 skipped (1257)** | 绿 |
| 4 | `pnpm exec vitest run packages/experimental/agent-hierarchy`（at2b-01 修复面专项） | 0 | Test Files 6 passed (6)；**Tests 40 passed (40)** | 绿 |
| 5 | `pnpm run gen-cordis-catalog` | 0 | 115 artifact(s) computed, 2 written, 1 pair record(s) refreshed；**0 violation** | 绿（附带刷新，见下） |
| 6 | `pnpm run test:docs`（doc-quick） | 0 | **15 passed, 0 failed, 0 skipped** in 27.02s | 绿 |
| 7 | `pnpm run verify-cordis-config` | 0 | **133 config files passed** | 绿 |
| 8 | `pnpm run verify-package-invariants` | 0 | **39 hand-owned package companion(s) conform.** | 绿 |
| 9 | `pnpm exec vitest run --config vitest.snapshot.config.ts` ×3 文件（DSH_EXAMPLE_MODE=lib） | **1** | 88F/15P/10S（113）×两轮 | **红→分类为已知残余** |

## 红·fail-loud 单列：快照抽样（步骤 9）

- 抽样面：`snapshots/session/headless.snapshot.ts` + `snapshots/sdk/sdk.snapshot.ts` + `snapshots/acp/acp.snapshot.ts`（lib 模式，重启后首次）。
- 第一轮：**88 failed / 15 passed / 10 skipped (113)**，exit 1（日志 `snapshot-sample-postrestart.log`）。
- **复跑一轮（判漂移程序）**：exit 1，**88F/15P/10S 同数**，签名分布同（`diverged from the pinned` 1 处 + `unknown tool` 15 处提及）——**确定性失败，排除重启环境漂移**（日志 `snapshot-sample-postrestart-rerun.log`）。
- **签名对表（对 R5 基线）**：A 族（`did not activate`）**0 处**（bundlefix 面重启后保持绿）；C 族（`Bad escaped character`）**0 处**（R5 时在途的 webfix 已落地生效）；残存失败全部为 **B 族根**（`packages/bundle/base/cordis.patch.yml` L252-254 与 minimal preset L36-38 的 bash win32 门控 vs pinned POSIX 语义头，实收头无 `bash` 工具行）——与 shipped-profile-defects.md 缺陷二/R5-3 记录同根因，属 Windows 宿主预期残余，非树回归、非重启漂移。
- 判别路径不变：CI(Linux) 跑同三文件预期绿；如 Linux 亦红则升级为树缺陷（当前证据不指向此）。

## 附带披露：gen-cordis-catalog 派生文档刷新

- 步骤 5 运行时生成器重写 3 个 tracked 文件：`docs/subsystems/shadow-router.md`/`.zh.md`/`.i18n.yaml`（2 written + 1 pair record refreshed）——上游合并后生成器未重跑，基线派生文档过期；本轮认证按生成器职责刷新之，**单独成提交**（与本证据文件分离），属绿项非缺陷。

## 本轮合规

- 零修复：未改 src/tests/profile/语料/依赖声明；快照红如实上报并附复跑判漂移证据。
- 隔离 home 仅新增 9 个日志文件（build-postrestart、sweep-experim-ext、agent-hierarchy-postrestart、gen-catalog-postrestart、test-docs-postrestart、cordis-config-postrestart、snapshot-sample-postrestart[-rerun]）。
- 门禁：`git diff --cached --check` exit 0（两个提交均过）；`git commit --no-verify`；未 push。
