"""生成项目上下文交接文档。

交接文档作者模型 (T3):
- 生成器提供结构（模板骨架）。
- 拥有完整项目上下文的 GPT/Agent 填充实质内容。
- 生成的文件是骨架，必须在转交到新对话之前，由拥有完整会话上下文的 GPT 审核并补充。
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parent.parent


def generate_handoff(target: str = "new-conversation") -> str:
    """生成 HANDOFF.md 骨架。必须在转交前由拥有完整上下文的 GPT 审核补充。"""

    lines = []
    lines.append("")
    lines.append("# HANDOFF — DevFrame Control Plane")
    lines.append("")
    lines.append("> 生成骨架 — 必须由拥有完整上下文的 GPT 审核并补充")
    lines.append(f"> 生成时间: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append(f"> 目标: {target}")
    lines.append("")
    lines.append("## 重要 — 交接文档作者模型")
    lines.append("")
    lines.append("本模板提供结构。实质内容必须由拥有完整项目上下文的 GPT/Agent 编写。")
    lines.append("在转交到新对话之前：")
    lines.append("")
    lines.append("1. 拥有完整会话上下文的 GPT 必须填写以下全部章节")
    lines.append("2. 作者 GPT 必须包含：项目定位、架构、已完成阶段、当前状态、安全边界、经验教训、下一步计划")
    lines.append("3. `{{占位符}}` 必须替换为实际内容")
    lines.append("4. 生成的 HANDOFF.md 应达到 10,000+ 字符的自包含上下文")
    lines.append("5. 转交 Agent 必须以 .md 文件附件形式上传 HANDOFF.md（非内联文本粘贴）")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. 项目定位")
    lines.append("{{项目定位}}")
    lines.append("")
    lines.append("## 2. 架构")
    lines.append("{{架构}}")
    lines.append("")
    lines.append("## 3. 已完成工作")
    lines.append("{{已完成阶段}}")
    lines.append("")
    lines.append("## 4. 当前状态")
    lines.append("{{当前状态}}")
    lines.append("")
    lines.append("## 5. 安全边界")
    lines.append("{{安全边界}}")
    lines.append("")
    lines.append("## 6. 关键决策与经验教训")
    lines.append("{{经验教训}}")
    lines.append("")
    lines.append("## 7. 下一步计划")
    lines.append("{{下一步}}")
    lines.append("")
    lines.append("## 8. 期望回复格式")
    lines.append("")
    lines.append("overall_judgment: accepted | blocked | review_unverified")
    lines.append("handoff_understood: yes | no")
    lines.append("project_identity_understood: yes | no")
    lines.append("architecture_understood: yes | no")
    lines.append("completed_phases_understood: yes | no")
    lines.append("current_state_understood: yes | no")
    lines.append("safety_boundaries_understood: yes | no")
    lines.append("next_steps_understood: yes | no")
    lines.append("ready_for_next_authorization: yes | no")
    lines.append("rationale: 简述")
    lines.append("")
    lines.append("## 9. 转交协议（Agent 执行）")
    lines.append("")
    lines.append("转交 Agent 必须：")
    lines.append("1. 以 .md 文件附件形式上传 HANDOFF.md（非内联文本粘贴）")
    lines.append("2. 附带简要引导提示，要求新对话阅读该文件")
    lines.append("3. 捕获回复并验证 handoff_understood=yes")
    lines.append("4. 若 handoff_verified=false，必须 fail-closed")
    lines.append("")

    return "\n".join(lines)


def save_handoff(output_path: str | Path, target: str = "new-conversation") -> Path:
    content = generate_handoff(target)
    path = Path(output_path)
    path.write_text(content, encoding="utf-8")
    return path
