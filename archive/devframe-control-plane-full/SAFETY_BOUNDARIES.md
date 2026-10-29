# Safety Boundaries

REVIEW_RUN_ID: g0-bootstrap-skeleton-v1-20260605

## 禁止提交的文件类型

以下内容**绝对禁止**进入版本控制：

| 类别 | 示例 | 说明 |
|------|------|------|
| 环境变量 | `.env`, `.env.*`, `.env.local` | 可能含 API key |
| 密钥证书 | `*.pem`, `*.key`, `*.crt` | 私钥材料 |
| 浏览器数据 | `browser_profile/`, `chrome-cdp-profile/` | Cookie / session |
| 会话数据 | `sessions/`, `cookies/` | 用户会话 |
| 私有工作区 | `private/`, `workspace/` | 用户私有文件 |
| 证据包 | `evidence_packs/` | 可能含用户数据 |
| 文档文件 | `*.docx`, `*.pdf` | 可能含真实论文 |
| 压缩包 | `*.zip` | 可能含用户 evidence |
| 日志文件 | `*.log` | 可能泄露路径 |
| IDE 配置 | `.vscode/`, `.idea/` | 个人偏好 |

## .gitignore 覆盖

以上类别已全部加入 `.gitignore`。

## 模板安全

- `templates/` 下的文件只含占位符，不含真实值
- `examples/` 下的 README 只含说明文字，不含可执行代码
- `.env.example` 只含字段名和占位符

## 审查要求

- 每次提交前检查 `git diff --cached` 确认无敏感文件
- CI 应运行 `control_plane doctor --safety-check`
- 发现违规 → 立即回滚，不推送
