"""Lightweight goal triage for the cluster coordinator.

`&<target> <goal>` must not spin up token-spending coding agents for a
conversational message like "你好" or "你能做什么". This classifies a goal as
either an actionable **development** task (run the coding workflow) or a
**conversation** message (the coordinator answers directly — no agents, no
tokens).

The classifier is intentionally conservative: it returns ``"conversation"``
only when the goal clearly looks conversational AND carries no development
signal, so a real goal is never silently downgraded into chat. When in doubt it
returns ``"development"`` (the goal runs).
"""
from __future__ import annotations

import re

GOAL_KIND_DEVELOPMENT = "development"
GOAL_KIND_CONVERSATION = "conversation"

# Imperative development verbs (substring match). English entries bias toward
# "development" on partial matches, which is the safe direction (the goal runs).
_DEV_VERBS_EN = (
    "add", "create", "implement", "build", "fix", "refactor", "remove", "delete",
    "rename", "update", "change", "write", "test", "debug", "optimize", "migrate",
    "integrate", "configure", "setup", "install", "generate", "support", "replace",
    "wire", "expose", "render", "parse", "handle", "validate", "format", "lint",
)
_DEV_VERBS_ZH = (
    "实现", "创建", "新建", "添加", "增加", "修复", "修改", "重构", "删除", "移除",
    "重命名", "更新", "改成", "改为", "编写", "写一个", "写个", "测试", "调试",
    "优化", "迁移", "集成", "配置", "安装", "生成", "支持", "替换", "接入", "对接",
    "渲染", "解析", "处理", "校验", "格式化", "排查", "加一个", "加个", "做一个",
    "实现一个", "搭建", "部署", "封装", "抽取", "拆分", "补充", "补一个",
)
# Conversational / small-talk / capability-question signals. Chinese entries are
# specific enough for substring matching; English entries are matched on word
# boundaries so short words like "hi" do not match inside "ship"/"this".
_CONVERSATIONAL_ZH = (
    "你好", "您好", "哈喽", "嗨", "在吗", "在不在", "谢谢", "感谢", "辛苦了",
    "你是谁", "你叫什么", "你能做什么", "能做什么", "你会什么", "怎么用", "如何使用",
    "使用方法", "帮助", "介绍一下", "自我介绍", "你好呀",
)
_CONVERSATIONAL_EN_RE = re.compile(
    r"\b(hi|hello|hey|thanks|thank you|who are you|"
    r"what can you do|what do you do|how do i use|how to use|help)\b",
    re.IGNORECASE,
)

_FILE_RE = re.compile(r"[\w./\\-]+\.[a-z]{1,6}\b", re.IGNORECASE)


def classify_goal(goal: str) -> str:
    """Return ``GOAL_KIND_DEVELOPMENT`` or ``GOAL_KIND_CONVERSATION`` for a goal."""
    text = (goal or "").strip()
    if not text:
        return GOAL_KIND_CONVERSATION
    lower = text.lower()

    has_dev_verb = (
        any(verb in lower for verb in _DEV_VERBS_EN)
        or any(verb in text for verb in _DEV_VERBS_ZH)
    )
    has_path = bool(_FILE_RE.search(text))
    if has_dev_verb or has_path:
        return GOAL_KIND_DEVELOPMENT

    is_conversational = (
        any(pattern in text for pattern in _CONVERSATIONAL_ZH)
        or bool(_CONVERSATIONAL_EN_RE.search(text))
    )
    if is_conversational or len(text) <= 3:
        return GOAL_KIND_CONVERSATION
    return GOAL_KIND_DEVELOPMENT


def coordinator_conversation_reply(goal: str) -> str:
    """A direct, no-token coordinator reply for a conversational goal."""
    return (
        "你好，我是项目主控。我可以接管一个开发目标：规划任务、协调编码智能体执行，"
        "再汇总并复核结果。\n\n"
        "请用一句话给我一个具体的开发目标，例如：\n"
        "· &主控 在 README 增加快速开始章节\n"
        "· &主控 修复登录页的空指针报错\n"
        "· &主控 给 utils 添加一个日期格式化函数并补测试\n\n"
        "目标发出后，你可以在这里看到「主控 → 智能体」的派发与执行过程，"
        "并点开任一智能体查看它的详细执行。"
    )
