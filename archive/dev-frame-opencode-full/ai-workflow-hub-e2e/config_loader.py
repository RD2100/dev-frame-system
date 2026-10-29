"""配置加载模块 — 读取和合并YAML配置文件"""

import os
import yaml

CONFIG_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")


def load_config(project_name: str) -> dict:
    """加载项目完整配置 = defaults + project + tools + profile"""
    config = _load_yaml(os.path.join(CONFIG_ROOT, "defaults.yaml"))
    _deep_merge(config, _load_yaml(os.path.join(CONFIG_ROOT, "projects", f"{project_name}.yaml")))

    # Load tool configs (merge into project overrides)
    tool_dir = os.path.join(CONFIG_ROOT, "tools")
    for f in os.listdir(tool_dir):
        if f.endswith(".yaml"):
            tool_name = f.replace(".yaml", "")
            tool_cfg = _load_yaml(os.path.join(tool_dir, f))
            # Unwrap if tool file has a top-level key matching its filename
            inner = tool_cfg.get(tool_name, tool_cfg)
            if tool_name in config and isinstance(config.get(tool_name), dict):
                _deep_merge(config[tool_name], inner)
            else:
                config[tool_name] = inner

    # 加载设备配置
    config["_devices"] = _load_yaml(os.path.join(CONFIG_ROOT, "devices.yaml"))

    # 加载账号
    config["_accounts"] = _load_yaml(os.path.join(CONFIG_ROOT, "accounts.yaml"))

    return config


def load_profile(profile_name: str) -> dict:
    """加载执行策略配置"""
    return _load_yaml(os.path.join(CONFIG_ROOT, "profiles", f"{profile_name}.yaml"))


def validate_config(config: dict) -> list[str]:
    """校验配置完整性，返回错误列表"""
    errors = []
    if "project" not in config:
        errors.append("缺少 project 配置块")
    if "stages" not in config:
        errors.append("缺少 stages 配置块")
    if "report" not in config:
        errors.append("缺少 report 配置块")
    return errors


def _load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # 环境变量替换
    content = _expand_env_vars(content)
    return yaml.safe_load(content) or {}


def _expand_env_vars(content: str) -> str:
    import re
    pattern = r"\$\{([^}]+)\}"
    def _replace(match):
        var = match.group(1)
        return os.environ.get(var, match.group(0))
    return re.sub(pattern, _replace, content)


def _deep_merge(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
