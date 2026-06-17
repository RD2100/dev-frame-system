"""Shell 执行器 — 安全执行 .aiworkflow.yaml 中声明的命令."""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from .config_loader import get_execution_policy

SHELL_META_TOKENS = ("&&", "||", ";", "|", "&", ">", "<", "`", "$(", "\n", "\r")
ALLOWED_PYTEST_VALUELESS_FLAGS = {
    "-q",
    "-v",
    "-s",
    "-x",
    "--disable-warnings",
}
ALLOWED_PYTEST_VALUE_PREFIXES = (
    "--maxfail=",
    "--tb=",
)
STATIC_TOOL_WRITE_FLAGS = {
    "--fix",
    "--unsafe-fixes",
    "--output-file",
    "--install-types",
    "--non-interactive",
}


def _is_safe_pytest_target(target: str, cwd: str) -> bool:
    if not target or target.startswith("@"):
        return False

    path_text = target.split("::", 1)[0]
    if not path_text:
        return False

    target_path = Path(path_text)
    if target_path.is_absolute() or ".." in target_path.parts:
        return False
    if not target_path.parts or target_path.parts[0].lower() not in {"tests", "test"}:
        return False

    root = Path(cwd).resolve()
    resolved_target = (root / target_path).resolve(strict=False)
    try:
        resolved_target.relative_to(root)
    except ValueError:
        return False
    return True


def _pytest_args_are_allowed(pytest_args: list[str], cwd: str) -> tuple[bool, str]:
    for arg in pytest_args:
        if not arg:
            return False, "empty pytest argument is not allowed"
        if arg.startswith("-"):
            if arg in ALLOWED_PYTEST_VALUELESS_FLAGS:
                continue
            if any(arg.startswith(prefix) for prefix in ALLOWED_PYTEST_VALUE_PREFIXES):
                continue
            return False, f"pytest option is not allowlisted: {arg}"
        if not _is_safe_pytest_target(arg, cwd):
            return False, f"pytest target must be a relative tests/ path inside project: {arg}"
    return True, ""


def _unittest_args_are_allowed(unittest_args: list[str], cwd: str) -> tuple[bool, str]:
    if len(unittest_args) != 2 or unittest_args[0] != "discover":
        return False, "unittest command must use discover tests/"
    if not _is_safe_pytest_target(unittest_args[1], cwd):
        return False, "unittest discovery target must be a relative tests/ path inside project"
    return True, ""


def _static_tool_args_are_allowed(args: list[str]) -> tuple[bool, str]:
    for arg in args:
        lowered = arg.lower()
        if lowered in STATIC_TOOL_WRITE_FLAGS:
            return False, f"static analysis write flag is not allowed: {arg}"
        if lowered.startswith("--output-file="):
            return False, f"static analysis write flag is not allowed: {arg}"
    return True, ""


def _is_allowed_argv(command_args: list[str], cwd: str) -> tuple[bool, str]:
    if not command_args:
        return False, "empty argv"

    exe = Path(str(command_args[0]).strip("\"'")).name.lower()
    args = [str(arg).strip("\"'") for arg in command_args[1:]]
    lower_args = [arg.lower() for arg in args]

    if exe in {"python", "python.exe", "py"}:
        if "-c" in lower_args:
            return False, "python inline execution is not allowed"
        if "-m" in lower_args:
            idx = lower_args.index("-m")
            if idx + 1 < len(lower_args) and lower_args[idx + 1] in {
                "pytest", "unittest", "compileall", "py_compile", "json.tool",
            }:
                if lower_args[idx + 1] == "pytest":
                    return _pytest_args_are_allowed(args[idx + 2:], cwd)
                if lower_args[idx + 1] == "unittest":
                    return _unittest_args_are_allowed(args[idx + 2:], cwd)
                return True, ""
        return False, "python command must use -m pytest|unittest|compileall|py_compile|json.tool"

    if exe in {"pytest", "pytest.exe"}:
        return _pytest_args_are_allowed(args, cwd)

    if exe in {"ruff", "ruff.exe", "mypy", "mypy.exe"}:
        return _static_tool_args_are_allowed(args)

    if exe in {"node", "node.exe"}:
        if "-e" in lower_args or "--eval" in lower_args:
            return False, "node eval execution is not allowed"
        if lower_args[:1] == ["--test"]:
            return True, ""
        return False, "node command must use --test"

    if exe in {"npm", "npm.cmd"}:
        if lower_args == ["test"]:
            return True, ""
        if len(lower_args) >= 2 and lower_args[0] == "run" and lower_args[1] in {
            "test", "lint", "typecheck",
        }:
            return True, ""
        return False, "npm command must be test or run test|lint|typecheck"

    if exe in {"gradlew", "gradlew.bat"}:
        if tuple(lower_args) in {("lint",), ("test",)}:
            return True, ""
        return False, "gradlew command must be lint or test"

    if exe == "echo":
        return True, ""

    if exe in {"git", "git.exe"}:
        if lower_args[:1] and lower_args[0] in {
            "status", "diff", "rev-parse", "ls-tree", "show", "log", "submodule",
        }:
            return True, ""
        return False, "git command must be read-only"

    return False, f"command executable is not allowlisted: {exe}"


def is_command_allowed(command: str, project_commands: dict[str, str]) -> bool:
    """检查命令是否在项目配置的 commands 中声明."""
    # 检查是否是声明的命令之一
    for cmd_value in project_commands.values():
        if cmd_value and cmd_value.strip() == command.strip():
            return True
    return False


def is_shell_safe(command: str) -> tuple[bool, str]:
    """检查命令是否匹配 forbidden_shell_patterns.

    Returns:
        (is_safe, reason)
    """
    for token in SHELL_META_TOKENS:
        if token in command:
            return False, f"shell operator is not allowed: {token!r}"

    policy = get_execution_policy()
    forbidden = policy.get("forbidden_shell_patterns", [])

    cmd_lower = command.lower()
    for pattern in forbidden:
        if pattern.startswith("regex:"):
            try:
                if re.search(pattern[6:], command, re.IGNORECASE):
                    return False, f"命令匹配禁止模式: '{pattern}'"
            except re.error:
                pass
        elif pattern.lower() in cmd_lower:
            return False, f"命令匹配禁止模式: '{pattern}'"

    return True, ""


def run_command(
    command: str,
    cwd: str,
    timeout: int | None = None,
    output_file: str | None = None,
) -> tuple[int, str, str]:
    """安全执行命令.

    Args:
        command: 要执行的命令
        cwd: 工作目录
        timeout: 超时秒数
        output_file: 可选，将输出同时写入文件

    Returns:
        (exit_code, stdout, stderr)
    """
    if not command or not command.strip():
        return -1, "", "ERROR: 空命令，不允许执行"

    safe, reason = is_shell_safe(command)
    if not safe:
        return -1, "", f"BLOCKED: {reason}"

    if timeout is None:
        policy = get_execution_policy()
        timeout = policy.get("command_timeout_seconds", 600)

    try:
        try:
            cmd_args = shlex.split(command, posix=True)
        except ValueError:
            return -1, "", "BLOCKED: command could not be parsed as argv"
        allowed, argv_reason = _is_allowed_argv(cmd_args, cwd)
        if not allowed:
            return -1, "", f"BLOCKED: {argv_reason}"
        if Path(str(cmd_args[0]).strip("\"'")).name.lower() == "echo":
            return 0, " ".join(str(arg) for arg in cmd_args[1:]), ""

        result = subprocess.run(
            cmd_args,
            shell=False,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        stdout = result.stdout
        stderr = result.stderr
        exit_code = result.returncode

        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            content = f"# Command: {command}\n# Exit Code: {exit_code}\n# CWD: {cwd}\n\n## STDOUT\n{stdout}\n\n## STDERR\n{stderr}\n"
            output_path.write_text(content, encoding="utf-8")

        return exit_code, stdout, stderr

    except subprocess.TimeoutExpired:
        msg = f"TIMEOUT: 命令超时 ({timeout}s): {command}"
        if output_file:
            Path(output_file).write_text(msg, encoding="utf-8")
        return 124, "", msg
    except Exception as e:
        msg = f"ERROR: 命令执行异常: {e}"
        if output_file:
            Path(output_file).write_text(msg, encoding="utf-8")
        return 1, "", msg


def run_project_commands(
    commands: dict[str, str],
    cwd: str,
    run_dir: str,
    command_names: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """按顺序执行项目命令.

    Args:
        commands: .aiworkflow.yaml 中的 commands 节
        cwd: 项目工作目录
        run_dir: 运行目录（用于保存输出）
        command_names: 要执行的命令名称列表，默认执行所有非空命令

    Returns:
        {command_name: {exit_code, stdout, stderr, output_file}}
    """
    results = {}

    default_names = ["lint", "typecheck", "unit_test", "integration_test", "build"]
    if command_names:
        to_run = command_names
    elif any(name.startswith("verify_") for name in commands):
        to_run = list(commands.keys())
    else:
        to_run = default_names

    for cmd_name in to_run:
        cmd_value = commands.get(cmd_name, "")
        if not cmd_value or "TODO" in str(cmd_value).upper():
            results[cmd_name] = {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"SKIPPED: 命令未配置或为 TODO: '{cmd_name}'",
                "output_file": "",
            }
            continue

        # 安全检查
        safe, reason = is_shell_safe(cmd_value)
        if not safe:
            results[cmd_name] = {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"BLOCKED: {reason}",
                "output_file": "",
            }
            continue

        output_file = str(Path(run_dir) / f"{cmd_name}-output.log")
        exit_code, stdout, stderr = run_command(
            cmd_value, cwd=cwd, output_file=output_file
        )
        results[cmd_name] = {
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "output_file": output_file,
        }

    return results
