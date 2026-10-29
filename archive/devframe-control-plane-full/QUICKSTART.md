# Quickstart

## 1. 获取仓库并安装

```bash
git clone https://github.com/RD2100/devframe-control-plane.git
cd devframe-control-plane

# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux / macOS
python -m venv .venv
source .venv/bin/activate

pip install -e .
```

## 2. Doctor 检查

```bash
devframe doctor
```

预期输出: `Doctor: 9/9 checks passed`

## 3. 基于模板初始化项目

```bash
devframe init code_project my-project
```

生成内容：
```
my-project/
  PROJECT_BOOTSTRAP.md
  CURRENT_STATE.yaml
  NEXT_TASK.md
  SAFETY_BOUNDARIES.md
  PIPELINE.yaml
  EVIDENCE_SPEC.yaml
  .gitignore
  .env.example
```

## 4. 运行流水线（dry-run）

```bash
cd my-project
devframe run --pipeline PIPELINE.yaml
```

当前 runner 执行 dry-run：解析流水线、验证结构、打印阶段序列，不改变状态。

## 5. Context Handoff（跨会话交接）

```bash
# 生成交接文档骨架（GPT/Agent 填充实质内容）
devframe handoff generate

# 验证交接文档
devframe handoff validate HANDOFF.md

# 干运行交接传输（文件附件协议，不实际发送）
devframe handoff transfer --to https://chatgpt.com/c/<conversation-id>

# 干运行新对话 bootstrap
devframe handoff bootstrap
```

## live CDP / GPT 提交

live CDP 执行和 GPT 提交默认禁用。需要单独授权并显式指定安全标志后才可启用。普通 quickstart 不涉及 live CDP。
