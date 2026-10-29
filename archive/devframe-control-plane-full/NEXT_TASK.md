# Next Task

REVIEW_RUN_ID: docs-sync-after-t3-v1

## 当前任务

**Docs Sync — 同步文档至 v0.1.0-rc / T3 accepted 真实状态**

将 README、QUICKSTART、INSTALL、PROJECT_BOOTSTRAP、CURRENT_STATE、NEXT_TASK、PHASE_LEDGER、RELEASE_CHECKLIST、EVIDENCE_INDEX 等面向用户的文档从早期 G0 Bootstrap 表述更新为当前真实状态。

## 后续方向（非 release blocker）

以下为推荐后续方向，非阻塞项：

1. **release documentation polish** — 文档措辞优化与一致性检查
2. **optional H5 synthetic-only post-release hardening** — 2-pack synthetic CDP pilot
3. **dev-frame-opencode real integration** — 与 dev-frame-opencode 的实际集成（非设计）
4. **paper workflow expansion** — paper_iteration 模板扩展为完整学术写作工作流
5. **T4 multi-conversation sync** — 多目标 conversation 同步管理

## 禁止事项

- 不删除/移动/重命名 evidence 文件
- 不修改 guard 逻辑
- 不默认开启 live CDP
- 不处理真实用户数据、cookie、session、browser profile
