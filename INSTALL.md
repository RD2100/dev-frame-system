# Install

## Requirements

- Python >= 3.10
- Git

## One-Command Install

```bash
git clone https://github.com/RD2100/devframe-control-plane.git
cd devframe-control-plane
pip install -e .
```

## Verify

```bash
devframe doctor
```

Expected: `Doctor: 9/9 checks passed`

## Initialize a Project

```bash
devframe init code_project my-project
cd my-project
devframe doctor
devframe run --pipeline PIPELINE.yaml
```

## Context Handoff

```bash
devframe handoff generate
devframe handoff validate HANDOFF.md
devframe handoff transfer --to https://chatgpt.com/c/<id>
devframe handoff bootstrap
```

Transfer 和 bootstrap 默认 dry-run，不实际发送到 GPT。

## Live CDP

live CDP 执行需要单独授权和安全标志，不在默认安装流程中启用。

## Templates

| Template | Purpose |
|----------|---------|
| code_project | Software engineering pipeline |
| paper_iteration | Paper review iteration |
| context_handoff | New conversation bootstrap |
