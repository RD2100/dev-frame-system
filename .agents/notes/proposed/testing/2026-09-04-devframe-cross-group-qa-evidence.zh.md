# Agent Note: DevFrame 跨组 QA 证据范围

Status: proposed

[English](2026-09-04-devframe-cross-group-qa-evidence.md) | 中文

## Problem

DevFrame 候选实现组合了原生 Team、Goal、session persistence、role policy 和进程停止等多个组的工作。局部测试可以通过，但固定 Profile、生成的事件目录、构建产物或 session 快照路径仍可能不可用。

## Proposal

针对一份固定候选记录 QA 证据，并写明精确命令、存储模式、模型权限、验收 ID 和已知阻断。跨组回归使用真实 Context、JSONL persistence、native Goal、Team tools 和 owned subprocess。局部验收子用例只记录为局部证据；在同一候选上运行所有必需路径之前，完整用例保持未完成。

在已发布的 `dsh` Profile 加载 DevFrame 包且快照工具能够重建 model-visible input 之前，不新增 recorded-session fixture。Profile、manifest、事件目录、persistence 和运行时实现的修复仍由所属组负责。

## Alternatives considered

**把重点测试的绿色结果当作验收。** 这样会把冷恢复、Profile、事件目录和交付证据的缺失隐藏在通过的 helper 或局部组合之后。报告把 `slice_green` 和 `qa_accepted` 分开记录。

**通过临时 Profile patch 记录功能快照。** 这样会产生不能代表已发布 application entrypoint 的产物，并把 QA 扩展到 Profile 和总体装配责任。快照决定延后到已发布组合存在之后。

**在 QA worktree 修复所有阻断。** 这样会覆盖其他组的实现和 persistence 决策，使证据对象无法明确。报告列出精确责任方，并保持这些文件不变。

## Acceptance criteria

固定候选具备可复现的重点回归命令、双语证据报告、Reviewer Index，以及从每个局部结果到权威验收用例的清晰映射。报告列出所有失败或不可用的前置条件，不做完整交付或发布声明。

## Risks

重点测试使用 mock model 行为和一次性存储，因此不能证明 provider usefulness、multi-project isolation、live-model 行为或全部 restart 路径。绿色的快照基础设施烟测只证明既有语料结构。Profile、事件、persistence、构建和包阻断在所属组关闭并由 QA 重新验证固定候选之前，仍与发布有关。
