# Safety Boundaries — {{PROJECT_NAME}}

## 禁止提交

- `.env`, `.env.*`（环境变量）
- `private/`, `workspace/`（私有工作区）
- `evidence_packs/`（证据包）
- `browser_profile/`, `sessions/`, `cookies/`（会话数据）
- `*.docx`, `*.pdf`（文档文件）
- `*.zip`（压缩包）
- `*.log`（日志文件）

## 代码变更边界

- 所有代码变更需要 GPT 授权
- Guard 不可移除（guard_removal_approved: false）
- 证据不可清理（evidence_cleanup_approved: false）
- 生产晋升需独立授权

## 审查要求

- 每次提交前 `git diff --cached` 检查
- 发现违规 → 立即回滚
