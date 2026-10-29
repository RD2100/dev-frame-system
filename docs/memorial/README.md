# DevFrame 纪念仓说明（MEMORIAL ONLY）

本仓库（`dev-frame-system`）现作为 **DevFrame 编码治理谱系纪念碑**，不是可运行的新内核，也不再作为日常开发主线。

## 主树

- `main`：扁平化整合快照（原 `packages/` 薄公开面），保留历史语义与文档。
- **请勿**在此仓继续实现运行时；活跃写表面是独立仓 `rd-shadow` 与 `dsh-plugin-suite-by-rd`（本纪念流程不会改动它们）。

## history/* 分支（源仓 tip 快照，未与 Python 根 merge-ort）

| 分支 | 来源 |
|---|---|
| `history/devframe-system-superproject` | `RD2100/devframe-system` @ master |
| `history/agent-acceptance` | `RD2100/agent-acceptance` @ master |
| `history/test-frame` | `RD2100/test-frame` @ master |
| `history/dev-frame-opencode` | `RD2100/dev-frame-opencode` @ master |
| `history/devframe-control-plane` | `RD2100/devframe-control-plane` @ main |
| `history/dsh-devframe-reference` | `RD2100/dsh-devframe` @ `reference/dev-frame-system-dsh` |
| `history/dsh-devframe-feat-20261027` | `RD2100/dsh-devframe` @ `feat/desktop-quality-fixes` |

## archive/*-full/（可选全文，不覆盖 `packages/`）

由 `git subtree add --squash` 抽入的全文树，与薄 `packages/` 并存。未抽入的大仓请直接 checkout 对应 `history/*` 分支浏览。

方案依据：`MEMORIAL_MERGE_PLAN_2026-10-29`（本地分析报告）。合并执行日期：2026-10-29（Asia/Tokyo）。

## 已抽入 main 的 archive/

- `archive/test-frame-full/`
- `archive/devframe-control-plane-full/`
- `archive/dev-frame-opencode-full/`
- `archive/devframe-system-full/`（超仓文档面；子模块目录可能为空 stub）

**未做 subtree（体积过大 / TS 与 Python 根冲突风险）：**

- `agent-acceptance` → 仅 `history/agent-acceptance`
- `dsh-devframe` → 仅 `history/dsh-devframe-reference` 与 `history/dsh-devframe-feat-20261027`

## Push 备注（2026-10-29）

部分 `history/*` 分支在 tip 上额外提交了一次 `memorial: strip .github/workflows…`，因为当前 `gh` OAuth token 缺少 `workflow` scope，无法推送含 Actions workflow 的 ref。源仓本身未改；完整含 workflow 的 tip 仍在已 Archive 的源仓中。
