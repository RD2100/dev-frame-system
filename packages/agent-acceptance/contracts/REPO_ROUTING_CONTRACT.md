# REPO_ROUTING_CONTRACT

## 规则

1. 每个任务必须声明 primary_repo 和 repos 路径边界
2. Agent 不得修改 blocked 路径
3. 跨仓任务必须在 evidence pack 中记录每个仓库的 git_tree_sha
4. GPT accepted 绑定所有涉及仓库的代码状态

## 验收

- submission_target_validator.py 检查 schema
- 路径越界 → pre-push gate 阻断
- 缺仓库 git_tree_sha → evidence pack rejected
