# Minimal Paper Workflow Example

> 本目录为示例说明，不包含真实论文内容。

## 场景

一篇学术论文的迭代审查流程：

1. **Drafting** — 完成当前轮草稿
2. **Review Request** — 提交摘要和结构给 GPT 审查
3. **Review Received** — 记录审查反馈
4. **Revision** — 根据反馈修改
5. **Accepted / Rejected** — 最终决定

## 对应模板

`templates/paper_iteration/`

## 关键文件

- `PAPER_PROFILE.yaml` — 论文元信息和版本历史
- `PAPER_STATE.yaml` — 迭代状态追踪
- `PAPER_REVIEW_SPEC.md` — 审查维度和流程

## 隐私说明

所有论文草稿内容保留在 `workspace/`（gitignored），不进入版本控制。

## 使用方式（未来）

```bash
python -m control_plane init --template paper_iteration my-paper
cd my-paper
# 编辑 PAPER_PROFILE.yaml 设置论文元信息
# 草稿放入 workspace/ 目录
python -m control_plane review --round 1
```
