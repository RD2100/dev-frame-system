# Agent Note: 快照场景级平台期望变体

Status: proposed

[English](2026-09-06-snapshot-platform-expectation-variants.md) | 中文

## Problem

`minimal-preset` web 快照场景在 Windows 宿主上以 `unknown tool "bash"` 失败（lib 模式快照运行 2 处）。shipped minimal preset 有意按平台门控持久 shell——`persistent-bash` 在 `win32` 关闭、其 `persistent-pwsh` 双胞胎在其余平台关闭（preset 自述即设计意图："the persistent shell (`bash` on POSIX, `pwsh` on win32)"）——而该场景的 authored 语料按 POSIX 语义录制，其 pinned 的 `tool-schemas.expected.json` 期待一张 `bash` 工具卡。组合面与期望面随宿主平台漂移，而语料——重放比对的唯一事实源——没有任何办法表达"这个维度按平台不同"。证据：`.agents/devframe/p22/shipped-profile-defects.md` 缺陷二（B 族）。

## Proposal

在快照场景 manifest 新增场景级平台期望配置字段：`snapshot.yml` 根级可选 `expectations.variants` 映射，平台键为 `win32` 与 `posix`，类别为 pinned 侧车 `system-prompt` 与 `tool-schemas`：

```yaml
expectations:
  variants:
    win32:
      - tool-schemas
```

- `parseSnapshotManifest` 对该字段 fail-loud 校验：仅 `header.pin: true` 的 manifest 可声明，平台键与类别成员都是封闭词表，声明必须非空且不重复，未知字段按解析器既有规则拒绝。未声明该字段的 manifest 行为与此前完全一致。
- 新解析缝 `resolveExpectationPath`（packages/test-support/session-snapshot/src/expectations.ts）解析读取宿主应比对哪个已提交期望文件：当前平台族声明了变体→选基础侧车同目录的 `<stem>.<win32|posix>.expected.<ext>`；其余一切情况→选基础文件；声明了变体而文件缺失→throw，消息含场景目录与变体文件名。
- web 通道的 pinned 比较（及其 refresh 回写）在 apps/web/tests/scaffold.ts 消费该解析器，`assertFixtureInventory` 自动放行声明的变体文件，场景 spec 无需任何清单改动。

缺陷的总控裁定是参数化期望面，不碰 preset/bundle 平台互斥——互斥是有意设计。参考实现及其用例在分支 `p/snapplat`；`snapshots/` 下共享语料零改动，minimal-preset 的数据挂接（yaml 两行加 `tool-schemas.win32.expected.json`）归语料 owner。

## Key design

- **双向清单闭环。** 声明⇒已提交：`assertFixtureInventory` 要求每个声明的变体文件在**所有**宿主平台都存在，不只是当前读取宿主。存在⇒已声明：磁盘上出现未被任何 manifest 声明的变体文件按清单失配拒绝（孤儿拒绝）。两侧都无法静默腐烂。
- **平台显式注入。** `resolveExpectationPath` 以参数接收读取宿主的 `process.platform`；解析器内部不读全局，win32 与 posix 两侧行为可在任一宿主用例钉住（posix 回落行为已在 win32 开发机上断言）。
- **现阶段单一消费通道。** 目前仅 web 通道消费该字段（pin 比较与 refresh 回写）。非 web 场景声明 `expectations` 能通过解析但无消费者，因此过渡纪律：headless/sdk/acp 的 suite 接线落地前，不得在 web 之外的场景声明。

## Alternatives considered

**取消 preset 的平台门控，让每个宿主同时挂两种 shell。** 这为满足一个测试语料而改变 shipped preset 对所有平台、所有 profile 的语义，且该门控是有意的产品设计。总控裁定拒绝；期望面才是可参数化的一侧。

**Windows 宿主跳过该场景。** 平台 skip 标记能让两处失败闭嘴，但完全放弃 Windows 覆盖，并把未来的组合漂移藏进已知失败清单。参数化期望面让两个平台各自对着自己的已提交语料被断言。

**在每个场景 spec 里写平台分支。** 在 `apps/web/tests/*.snapshot.ts` 硬编码 `process.platform` 条件会把平台知识散进各 spec 文件，并绕过清单守卫的权威；manifest 声明让每个场景只有一个声明式 owner，守卫恰好放行声明的文件。

## Acceptance criteria

- `parseSnapshotManifest` 仅在 pinned header 上接受 `expectations`，拒绝未知字段、未知平台键、未知或重复类别、空声明；未声明该字段的 manifest 解析结果与此前逐字节一致（session-snapshot corpus 门原样通过）。
- `resolveExpectationPath` 为当前平台族选择声明的变体文件，其余情况回落基础文件；声明的变体文件缺失时 throw 并含场景目录与变体文件名；win32 与 posix 两臂由单测以精确错误消息钉住，夹具全部建于临时目录。
- `assertFixtureInventory` 无需 spec 改动即放行声明的变体文件、要求其在所有宿主存在、拒绝未声明的变体文件。
- 参考分支通过 session-snapshot 包 vitest 套件、包级 `tsc -b`、仓库根 `pnpm run build` 与 corpus 门。

## Risks

- headless/sdk/acp 的 suite 通道尚未消费 `expectations`；"web 之外不得声明"的纪律是接线波落地前的过渡守卫，过早声明会静默无效。
- corpus 门不校验变体文件；web 侧保护仅来自 `assertFixtureInventory`。
- 子级侧车变体（`system-prompt.<n>.expected.md`）不支持；需要按子级平台变体的场景需要机制扩展。
- refresh 回写走解析后的路径，win32 宿主只会刷新 win32 变体文件；基础（posix）文件需要 posix 宿主或人工维护。
- `session.jsonl` 脚本侧变体与内联快照消费通道缺失；两者归 B 族机制扩展波。
- 平台词表是封闭集（`win32` | `posix`）；新增平台家族需要同时扩展解析器词表与映射缝。
