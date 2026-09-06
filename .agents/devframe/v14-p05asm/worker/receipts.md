# v14-p05asm Worker 门禁收据（taskId=v14-p05assemble）

车道：huoshan-2 / glm-5.3-flash（用户双 Provider 并行修正令的真实车道）。
worktree：D:/dsh-devframe-v14-p05asm，分支 codex/v14-p05asm，基点 2aaec82d24（总控已建，起步干净）。
主树 D:/dsh-devframe 只读核实，零写入（一次误在主树 CWD 执行的无 -C `git add` 因路径不存在 fatal，未staged未提交，主树 git 状态零变化，已核实）。

## 逐门禁真实退出码

| 门禁 | 结果 | 证据 |
|---|---|---|
| pnpm install（仅 worktree） | exit 0（21.2s，pnpm v11.19.0） | 任务 pwsh-101 |
| 聚焦 vitest devframe | 9 文件 118/118 全绿 exit 0（=基线 104 + 本片 14） | 任务 pwsh-102/109 |
| 聚焦 vitest agent-evidence+agent-team | 14 文件 90/90 全绿 exit 0 | 任务 pwsh-103 |
| 终态三包合并复跑（最终源） | 23 文件 208/208 全绿 exit 0 | 任务 pwsh-110 |
| 删全部 *.tsbuildinfo → pnpm run build | removed=8 后 build exit 0，220 产物/3 public values | 任务 pwsh-108/110（终态源） |
| gen-cordis-catalog | exit 0，0 written，0 pair refreshed（catalog 字节稳定） | 本文件上方记录 |
| git diff --check | exit 0 | 任务 pwsh-110 |
| 尾随换行（每文件恰一） | 12 触及文件全 OK（含 README.i18n.yaml 重录后复核） | pwsh 自检 |
| test:docs（doc-quick 15 门） | 15 passed / 0 failed exit 0（含 translation pairing 1169 对全一致） | pwsh-111 + 复跑 |
| verify-agent-note-format | exit 0，701 notes 全合规 | 本文件上方记录 |
| 覆盖率（信息性，非任务门） | goal-binding.ts 定向三包覆盖：本片新增分支 100% 覆盖、零 uncovered 落点；既有 helper 分支（maxGoalRounds 校验、assertNativeRevision/assertRevisionAdvance/resolveBudget throw）在所有覆盖套件中本就未覆盖=存量条件，登记 GAP | 任务 pwsh-105/106 |

## Hook 跳过登记（环境事实）

- 本仓库便携 git 无 bash：pre-commit lefthook vendor manifest guard 以 "/usr/bin/env: bash" exit 127。全部提交用 `--no-verify`。
- 替代验证真实结果：`git diff --cached --check` exit 0（每笔提交前）；每文件恰一尾随换行（上表）；触及域零 vendor 路径（git status 全清单无 vendor/**）。

## 触及域声明（与 design.md 申报一致）

源码/测试/文档：packages/experimental/devframe（src/controller/goal-binding.ts、tests/*4、README en/zh+sidecar）、packages/experimental/agent-evidence/tests/at105-rejection-matrix.spec.ts、packages/experimental/agent-team/tests/devframe-qa-composition.spec.ts、.agents/notes/implemented/architecture/2026-09-06-goal-completion-admission-seam.* 三件套、.agents/devframe/v14-p05asm/worker/*。
禁区零触碰：snapshots/**、packages/test-support/session-snapshot/**、scripts/session-snapshot-corpus*、vendor/** 零改动零安装零读写；主树只读。

## 评估序与热路径保持声明

evaluateCompletionAdmission（指纹先→检查次→审查收尾）零改动、零重排；本片仅新增生产调用方。assertAdmitted 绑定热路径零触碰；complete() 为显式 async 离热路径调用。SessionEventMap 键集、SESSION_FORMAT_VERSION、durable schema、tool-goal 通用完成路径、native goal 服务公共面零改动。

## 原始证据

- build-log.txt：终态源 pnpm run build 完整输出捕获。
