# Agent Note：工作区期望的平台变体

Status: implemented

[English](2026-09-06-workspace-expectation-platform-variants.md) | 中文

## 问题

Keyless 录制会话回放把每个场景与单一 POSIX 录制的期望集比较。在 win32 上三个 shell-hook 场景的会话回放本身干净，却在工作区比较处失败：POSIX 侧车记录了只有 POSIX hook 语义才会产生的 `.posttool-blocked` / `.stop_fired` 标记文件，而 win32 宿主的录制会话早已如实携带 `sh: not recognized` 结果——工作区期望目录完全没有变体路径，headless 运行器的 final workspace 检查也无条件读 base 目录。

## 决策

session-snapshot 包新增最小平台变体缝。场景 manifest 可声明 `sessionVariants.win32`（会话夹具）与 `expectations.variants.win32`（指名哪些钉定侧车有平台变体）；manifest 解析为白名单严格式，未知键 fail-loud，声明的变体文件必须存在。共享解析器 `resolveWorkspaceExpectedDir`（与既有 expectation-path 解析器并列）选择平台目录；`suite.ts` 与 headless 运行器的 final workspace 检查都经它路由。corpus 门新增 presence、marker、成对存在性规则与非法用例覆盖，包测试钉住解析器与严格 manifest 行为（+12 例）。三个 hook 场景交付收割的 `session.win32.jsonl` 夹具与手作的 `workspace.win32.expected/` 目录（取自真实回放失败的 actual 侧）；base 夹具零 diff。

## 落选替代

**跨平台归一标记名。** 标记是平台 hook 语义的真实工作区效果；假装一致会伪造场景要证明的工作区证据。

**按平台复制整套场景。** 为一个期望目录变化复制整个场景目录，会让未来每个平台问题都翻倍维护；解析器让一个场景携带声明式变体即可。

**refresh 期间自动收割工作区变体。** 收割写的是宿主恰好产出的内容；win32 工作区变体取自真实回放失败的手作，正是为了让提交的期望陈述"被接受的平台差异"，而非最后一次运行碰巧的产物。

## 后果

- 三个 hook 场景在 win32 端到端转绿——session、stdout/stderr、workspace——base 夹具零触碰。
- 声明但缺失的变体文件在 manifest 加载时 fail-loud，变体面不会静默腐坏。
- 两条发现在波外登记：acp pin 侧车收割管线没有变体写路径（image-compaction 的平台措辞漂移需夹具车道裁决）；code-runtime 栈轨迹内嵌录制树绝对路径，`both-mode-turn`/`ptc-turn` 在任何非录制树回放必红。
