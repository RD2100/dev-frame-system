---
description: 2026-09-04 提议中的 DevFrame 跨组 QA 证据。
---

# DevFrame QA 证据 — 2026-09-04

[English](devframe-qa-2026-09-04.md) | 中文

## 结论

在已测试的原生 Team、Goal 和 DevFrame 路径上，本 worktree 达到 `slice_green`，但没有达到 `qa_accepted`、`main_integrated` 或 `release_green`。候选实现仍受构建、包、事件目录和已发布 Profile 快照阻断。

本报告记录一份固定 worktree 的证据，不授权合并、推送、发布或真实模型消费。QA 文件可以在复核后仅做本地提交；父线程的恢复快照仍保留在 `stash@{0}`。

## 证据快照

| 字段 | 记录值 |
| --- | --- |
| 候选 worktree | `C:\Users\25313\.codex\worktrees\9af0\dsh-devframe` |
| 源基线 | 分离的 `HEAD`，提交为 `4e84901e6471b79ec0338099867ebb4606d12bb5` |
| 候选输入 | 应用父线程提供的 `stash@{0}`，没有删除 stash |
| 记录时间 | 2026-09-04 16:09–16:17（Asia/Tokyo） |
| 平台 | Windows `win32`、Node `v24.19.0`、pnpm `11.19.0` |
| 存储和模型 | JSONL session persistence 和无 key 的 mock model 行为；没有真实 API key 或消费 |
| worktree 修改 | 候选实现文件仍未暂存；QA 文件只做本地提交；没有推送或部署 |

候选输入包含集成、权限、Controller、Reliability 以及 profile/manifest 组负责的改动。QA 只新增组合回归、配对后的交接文档、本报告和 testing Agent Note。

## 已执行回归

重点候选回归通过了 15 个测试文件和 102 个测试，其中包含新的[跨组组合测试](../../packages/experimental/agent-team/tests/devframe-qa-composition.spec.ts)。该测试挂载真实的 Context、JSONL persistence、Goal service、Team service 和 Team tools，然后检查 task/Goal 绑定、真实 dispatcher mutation、精确 result identity 以及持久化的 `goal/change` 和 `team/task` 事件。

```powershell
pnpm.cmd exec vitest run packages/experimental/devframe/tests packages/experimental/agent-team/tests packages/experimental/tool-agent-team/tests packages/experimental/agent-team-profile/tests
```

该计数包含既有的[原生 Team 和 tool-Team 回归](../../packages/experimental/agent-team/tests/team.spec.ts)，也包含新的 role、recovery、composition 和 controller 切片。测试运行器只输出了既有的 `vite-tsconfig-paths` 弃用提示。

`pnpm.cmd run verify-scoped-events` 通过，并报告 `packages/core/scope/src/scoped-events.generated.ts` 已是最新。

快照基础设施烟测命令 `pnpm.cmd exec vitest run --config vitest.snapshot.config.ts snapshots/session/headless.snapshot.ts -t "gives every composition and header class exactly one pin"` 通过了 1 个语料结构测试，跳过 81 个测试。它只验证既有的 recorded-session 语料，不构成 DevFrame 功能证据。

## 验收映射

验收依据仍以[测试与验收](../testAndAcceptance.zh.md)为准。以下条目是局部证据，不是完整的 `AT*` 通过结论。

| 验收用例 | 本 worktree 中的证据 | 结果 |
| --- | --- | --- |
| `AT1-01` / `R1.1` | [role-denial.spec.ts](../../packages/experimental/tool-agent-team/tests/role-denial.spec.ts) 通过真实 dispatcher 检查继承工具限制、Team 局部 mutation 以及后置 allow listener。 | 局部证据；文件、shell、workflow、Goal 覆盖和完整 assembled Profile 尚未具备。 |
| `AT1-02` / `R1.1` | [cold-role-recovery.spec.ts](../../packages/experimental/agent-team/tests/cold-role-recovery.spec.ts) 持久化 reviewer descriptor，释放 child，冷恢复后再次执行受限工具探针。 | 局部证据；持久化 role-policy 恢复和缺少 role 时拒绝尚未具备。 |
| `AT1-09` / `R1.5` | [goal-binding.spec.ts](../../packages/experimental/devframe/tests/goal-binding.spec.ts) 检查精确的 Goal A/B identity；新的组合测试增加真实 Team task 和 JSONL 事件路径。 | 局部证据；连续 native restart、budget consumption 和 late-result delivery 尚未具备。 |
| `AT1-10` / `R1.6` | Goal-binding 测试覆盖 human authorization、create/disarm 顺序、persistence failure 和显式 resume identity。 | 局部证据；完整 command journey 和 result/evidence view 尚未具备。 |
| `AT4-03` / `R4.2` | [stop.spec.ts](../../packages/experimental/devframe/tests/reliability/stop.spec.ts) 覆盖 owned child-process tree。 | 局部证据；项目级 writer ownership 和完整 stop 验收用例仍未验证。 |
| 其余 `AT*` 用例 | 本 worktree 没有完整 filesystem、multi-project、memory、live-model 或 version-recovery 矩阵的可复现证据。 | `not_run` 或 `blocked`；不做交付声明。 |

按照验收依据，局部子用例不能把完整用例提升为 `passed`，必需用例被阻断也会阻止对应交付声明。

## 快照决定

仓库的 recorded-session 快照通道通过已发布的 `dsh` Profile 启动。现有 `team-snapshot.patch.yml` 启用原生 `agent-team` 和 `tool-agent-team`，但没有加载 DevFrame 包、role policy 或 Goal-binding controller。`snapshots/` 下没有已提交的 DevFrame 快照场景。

因此 QA 没有创建 JSONL、prompt、schema 或 protocol 快照产物。新增快照需要修改 Profile、manifest 和总体装配，这些不属于本组范围；在已发布组合存在之前，现有集成测试是正确的回归证据。

## 阻断检查

| 检查 | 结果 | 阻断事实 |
| --- | --- | --- |
| 本次修复前的 `pnpm.cmd run test:docs` | 15 个门禁中 2 个失败 | 中文交接文件缺少双语配对，连续元数据行被解析为一个换行段落。 |
| `pnpm.cmd run build:lib:host` | 失败 | `packages/experimental/devframe/tests/reliability/stop.spec.ts:73,83,89,90` 的 mock 缺少必需的 `SubprocessOutcome.exitCode`。 |
| `pnpm.cmd run hygiene` | 15 个门禁中 6 个失败 | 候选 DevFrame 包的 `files` allowlist 不满足约束；README 缺少省略 invariant companion 的原因；仓库构建产物和 `vendor/loader/lib/index.js` 缺失；一个既有 ACP Profile 的根元数据无效。 |
| `pnpm.cmd run typecheck` | 编译前失败 | 仓库脚本调用 `npm`，当前 PowerShell 命令环境无法找到它。 |
| DevFrame 功能快照 | 未运行 | 没有已发布的 Profile 场景加载 DevFrame 包，记录快照会扩大 Profile/manifest 范围。 |

构建和 hygiene 失败指向 QA 以外负责的候选前置条件；本组没有修改实现、事件、持久化、包或 Profile 文件。

## 必要后续动作

1. 为 reliability 测试 mock 补齐当前 `SubprocessOutcome` 字段，然后重新运行 `build:lib:host`。
1. 修正 DevFrame 包的 `files` 列表，并在 README 中补充省略 invariant companion 的必需说明。
1. 解决权威事件目录和冷恢复 role restoration 阻断，然后在记录 DevFrame session 快照前增加已发布的 Profile 组合。
1. 生成所需的 peer build outputs，修复 ACP Loader metadata，然后重新运行失败的 hygiene 门禁。
1. 在这些改动完成后对同一候选运行完全相同的 QA 命令；验收表只能加入该次运行的证据。

## Reviewer Index

- QA 测试改动：`packages/experimental/agent-team/tests/devframe-qa-composition.spec.ts`。
- 文档改动：`docs/working/handoff-2026-09-03.md`、`docs/working/handoff-2026-09-03.zh.md`、本双语报告，以及 `.agents/notes/proposed/testing/2026-09-04-devframe-cross-group-qa-evidence.md` 的双语 testing note。
- 复核的关键路径：Team task tool dispatch、native Goal create/disarm/resume、JSONL event inspection、role-denial recovery 和 owned-process stopping。
- 生成产物：没有新增已提交的 snapshot JSONL、prompt、schema、protocol 或 build output。
- 复核重点：其他组修复候选时，保留局部状态、阻断责任、精确测试范围和不创建快照的决定。

## Dev Note

这是针对记录基线下分离候选的工作证据报告，不是验收批准。现有候选改动仍未暂存，本报告不把它们宣称为 QA 负责的实现。
