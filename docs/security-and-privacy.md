# 安全与隐私

## 核心原则

Control Plane 本身不存储、不传输、不处理用户私有数据。所有真实数据保留在用户的本地工作区。

## 数据分类

| 类别 | 存储位置 | 版本控制 | 示例 |
|------|----------|----------|------|
| 公开 | 仓库根目录 | 是 | 代码、文档、模板、Schema |
| 私有 | `private/` 或 `workspace/` | 否 (.gitignore) | API key、论文草稿、用户数据 |
| 证据 | `evidence_packs/` | 否 (.gitignore) | ZIP 包、capture 文件、审查结果 |
| 会话 | `sessions/`、`browser_profile/` | 否 (.gitignore) | Cookie、CDP profile |

## 模板安全

- `templates/` 只含占位符
- `.env.example` 只含字段名
- 无硬编码密钥、URL、token

## 提交前检查

```bash
git diff --cached --name-only  # 检查暂存文件
grep -r "sk-" . --include="*.py" --include="*.yaml" --include="*.json"  # 检查 API key
```

## 违规响应

- 发现敏感文件已暂存 → `git reset HEAD <file>` 取消暂存
- 发现敏感文件已提交 → 轮换密钥，重写历史
- 发现 `.env` 包含真实值 → 立即删除，轮换密钥
