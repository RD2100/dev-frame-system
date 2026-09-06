# Agent Note：agent-evidence 证据日志生产者（生产源）

Status: implemented

[English](2026-09-06-agent-evidence-journal-producer.md) | 中文

## 问题

[完成准入 seam](2026-09-06-goal-completion-admission-seam.zh.md) 与 [/goal-complete 宿主命令](2026-09-06-command-goal-binding-host-command-surface.zh.md) 消费折叠进 devframe 投影的 `devframe/verification` 与 `devframe/review` 证据，但没有生产源发射这些记录：测试即唯一生产者，真实宿主在完成命令处只能收到 `NO_VERIFICATION_TEXT` / `NO_REVIEW_TEXT`。S4 工具面计划把生产接线推迟，at105 拒绝矩阵记录把残余明文留给了本切片。

## 决策

两个 plain class 落地 `agent-evidence`。`CheckRunner` 在诚实契约下以真实子进程执行必需检查配置的命令：存储命令先做精确等价复核，结果映射为四态，输出逐字捕获，配置顺序确定，失败检查如实记失败——绝不为了找一次通过而重跑。`AgentEvidenceJournal` 以组合持有的 `DevFrameSessionJournal` 与评审门构造——构造即接线 `EvidenceReviewGate`，未接线即构造失败（p05harden 裁定）。在宿主的"验证完成/审查完成"时刻，其两个 record 方法加载配置的检查存储、执行检查、聚合，并经会话日志唯一的 schema 校验追加路径落账，devframe 投影随之折叠，`/goal-complete` 读到真实证据。包导出两个类及其结果类型；不注册 Context merge，devframe 包零 diff，台账三表零 diff。

## 落选替代

**以 Context merge 服务替代 plain class。** 在组合接线尚未落地时，merge 会为波次级 seam 花费公共 catalog 面；plain class 把构造依赖显式留给组合点。

**绕开 `DevFrameSessionJournal` 追加事件。** 该 journal 是唯一 schema 校验的追加路径；第二写入面会破坏投影折叠并重复校验。

**在 runner 内重试失败检查。** 重试是诚实契约的反面：记录必须陈述配置命令的真实结果。

**现在落地组合接线。** 谁构造生产者、`ctx.sessions.flush` 时机与 live 角色权威属 S4 工具面切片。

## 后果

- 宿主获得准入证据链的真实生产者；无证据错误仅在确实没有证据时可达。
- 组合接线、有界输出捕获、600s 默认之外的 `timeoutMs` 注入点、台账镜像 journal 证据仍是工具面切片工作。
- 设计测试矩阵的 findings 重复 id 拒绝缺具名用例；该路径由 pass+blocking findings 用例与 devframe events 套件双锚定，已记为欠账。
