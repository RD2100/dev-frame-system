"""模型配置 — OpenCode-only 模型选择.

简化: 只按 risk 返回 OpenCode 模型名，可被 OPENCODE_MODEL_OVERRIDE 覆盖。
"""

from __future__ import annotations

import os


def get_model_for_risk(risk: str) -> str:
    """根据风险等级返回 OpenCode 模型名.

    risk=high   -> deepseek/deepseek-v4-pro
    risk=medium -> deepseek/deepseek-v3
    risk=low    -> deepseek/deepseek-v3

    可通过环境变量 OPENCODE_MODEL_OVERRIDE 覆盖。
    """
    override = os.environ.get("OPENCODE_MODEL_OVERRIDE", "")
    if override:
        return override

    if risk == "high":
        return "deepseek/deepseek-v4-pro"
    return "deepseek/deepseek-v3"
