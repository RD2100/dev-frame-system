"""LangGraph 工作流定义 — OpenCode-only 编码闭环 (7 节点).

节点: plan_auditor -> human_gate -> execute -> test -> reviewer -> fix/final
路由: plan_auditor 阻塞 -> final; plan_auditor clean/human_required -> human_gate;
      execute/fix 产生终态 -> final；test passes -> reviewer；
      reviewer pass -> final；reviewer block -> final (blocked)；
      test fails & rounds < max -> fix

M3: 决策文件驱动的可干预 pipeline。
- decisions/human-gate.json: pending/approved/rejected
- decisions/fix-before-round-{N}.json: continue/pending/abort/skip
- decisions/fix-control.json: mode=auto|supervised, pause_before_next_fix

M4-B1: plan_auditor_node 入口 — 确定性 plan scope 校验，在 human_gate 之前阻塞或提审不合理的 scope。
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from ..schemas import WorkflowState
from ..nodes.plan_auditor import plan_auditor_node
from ..nodes.executor import executor_node
from ..nodes.tester import tester_node
from ..nodes.fixer import fixer_node
from ..nodes.reviewer import reviewer_node
from ..nodes.human_gate import human_gate_node
from ..nodes.finalizer import finalizer_node

# M3: decision file helpers (shared module, no circular imports)
from ..run_decisions import (
    Decision, FixControl,
    _read_decision, _read_fix_control,
    SIDE_EFFECT_NODES, TERMINAL_STATUSES,
)


def create_coding_graph(checkpointer: MemorySaver | None = None) -> StateGraph:
    """创建编码工作流状态图 (带 checkpointer).

    状态机结构:

    start
      |
    human_gate_node         [入口 — 接收 TaskSpec]
    execute_node             [调用 OpenCode 执行代码修改]
      |-- terminal -> final_node
      |-- continue -> test_node [每个 fix 轮后重新执行]
      |
    (test route)
      |-- passed -> final_node
      |-- fail + round < max -> fix_node -> test_node
      |-- fail + round >= max -> final_node
    """

    graph = StateGraph(WorkflowState)

    # 添加节点 (M4-B1: plan_auditor 为入口, 在 human_gate 之前)
    graph.add_node("plan_auditor_node", _wrap(plan_auditor_node))
    graph.add_node("human_gate_node", _wrap(human_gate_node))
    graph.add_node("execute_node", _wrap_with_guard(executor_node, "execute_node"))
    graph.add_node("test_node", _wrap(tester_node))
    graph.add_node("reviewer_node", _wrap(reviewer_node))
    graph.add_node("fix_node", _wrap_with_guard(fixer_node, "fix_node"))
    graph.add_node("final_node", _wrap(finalizer_node))

    # 入口: plan_auditor
    graph.set_entry_point("plan_auditor_node")

    # plan_auditor -> human_gate (clean/human_required) 或 final (blocked)
    graph.add_conditional_edges(
        "plan_auditor_node",
        _plan_auditor_route,
        {
            "human_gate_node": "human_gate_node",
            "final_node": "final_node",
        },
    )

    # human_gate -> execute (或 END 如果需要人工)
    graph.add_conditional_edges(
        "human_gate_node",
        _human_gate_route,
        {
            "execute_node": "execute_node",
            "final_node": "final_node",
            "__end__": END,
        },
    )

    # execute -> test/final
    graph.add_conditional_edges(
        "execute_node",
        _side_effect_route,
        {
            "test_node": "test_node",
            "final_node": "final_node",
        },
    )

    # test -> reviewer (passes) or fix (fails)
    graph.add_conditional_edges(
        "test_node",
        _test_route,
        {
            "reviewer_node": "reviewer_node",
            "fix_node": "fix_node",
            "final_node": "final_node",
            "__end__": END,
        },
    )

    # reviewer -> final
    graph.add_conditional_edges(
        "reviewer_node",
        _reviewer_route,
        {
            "final_node": "final_node",
        },
    )

    # fix -> test/final
    graph.add_conditional_edges(
        "fix_node",
        _side_effect_route,
        {
            "test_node": "test_node",
            "final_node": "final_node",
        },
    )

    # final -> END
    graph.add_edge("final_node", END)

    return graph


def compile_graph(thread_id: str) -> Any:
    """编译带 MemorySaver checkpointer 的图（单进程内存模式，不跨进程持久化）.

    Args:
        thread_id: run_id，映射为 LangGraph thread_id
    """
    checkpointer = MemorySaver()
    graph = create_coding_graph(checkpointer)
    return graph.compile(checkpointer=checkpointer)


def _s(state: dict[str, Any] | Any) -> dict[str, Any]:
    """安全解包 state: WorkflowState -> dict."""
    if hasattr(state, "model_dump"):
        return state.model_dump()
    if isinstance(state, dict):
        return state
    return {}


def _plan_auditor_route(state: dict[str, Any] | Any) -> str:
    """plan_auditor 后路由: blocked -> final; clean/human_required -> human_gate."""
    s = _s(state)
    if s.get("status") == "blocked":
        return "final_node"
    return "human_gate_node"


def _human_gate_route(state: dict[str, Any] | Any) -> str:
    """human_gate 后路由: rejected/blocked -> final;
    human_required -> 查决策文件 (approved->execute, rejected->final, pending->END);
    否则 -> execute."""
    s = _s(state)

    # P0: rejected/blocked 不得进入 execute_node
    if s.get("status") in ("blocked", "rejected"):
        return "final_node"

    if s.get("human_required", False) or s.get("status") == "human_required":
        d = _read_decision(s.get("run_dir", ""), "human-gate")
        if not d.valid:
            return "__end__"      # 损坏 JSON → 暂停
        if d.status == "approved":
            return "execute_node"
        if d.status == "rejected":
            return "final_node"
        # pending 或文件不存在 → 暂停
        return "__end__"

    return "execute_node"


def _test_route(state: dict[str, Any] | Any) -> str:
    """test 后路由: pass -> reviewer; fail + round < max -> 查决策 -> fix/final/END."""
    s = _s(state)
    test_passed = s.get("test_exit_code", -1) == 0
    if test_passed:
        return "reviewer_node"

    fix_round = s.get("fix_round", 0)
    max_fix_rounds = s.get("max_fix_rounds", 3)
    if fix_round >= max_fix_rounds:
        return "final_node"

    next_round = fix_round + 1
    run_dir = s.get("run_dir", "")

    control = _read_fix_control(run_dir)
    if not control.valid:
        return "__end__"

    d = _read_decision(run_dir, f"fix-before-round-{next_round}")
    if not d.valid:
        return "__end__"

    if d.status in ("abort", "skip"):
        return "final_node"
    if d.status == "pending":
        return "__end__"

    if control.mode == "supervised" and not d.exists:
        return "__end__"
    if control.pause_before_next_fix and not d.exists:
        return "__end__"

    return "fix_node"


def _reviewer_route(state: dict[str, Any] | Any) -> str:
    """reviewer 后路由: 总是进入 final_node (reviewer 内部设置 blocked 状态)."""
    return "final_node"


def _side_effect_route(state: dict[str, Any] | Any) -> str:
    """Route after executor/fixer: terminal statuses skip more side effects."""
    s = _s(state)
    if s.get("human_required", False):
        return "final_node"
    if s.get("status") in ("failed", "blocked", "human_required", "rejected"):
        return "final_node"
    return "test_node"


def _wrap(fn):
    """Wrap node function — 兼容 dict / WorkflowState / Pydantic model."""
    def wrapped(state: dict[str, Any] | WorkflowState | Any) -> dict[str, Any]:
        if hasattr(state, "model_dump"):
            state_dict = state.model_dump()
        elif isinstance(state, dict):
            state_dict = state
        else:
            state_dict = dict(state) if state else {}
        result = fn(state_dict)
        # 先更新非 backend_calls 字段，再合并 backend_calls
        bc = result.pop("backend_calls", None)
        state_dict.update(result)
        if bc:
            state_dict.setdefault("backend_calls", {}).update(bc)
        return state_dict
    return wrapped


def _wrap_with_guard(fn, node_name: str):
    """Wrap 副作用节点 (execute_node, fix_node).

    execute_node: 恢复时已执行则跳过，避免重复调用 OpenCode。
    fix_node: 按轮次允许重复: fix_node:1, fix_node:2, ...
    """

    def guarded(state: dict[str, Any] | WorkflowState | Any) -> dict[str, Any]:
        if hasattr(state, "model_dump"):
            state_dict = state.model_dump()
        elif isinstance(state, dict):
            state_dict = state
        else:
            state_dict = dict(state) if state else {}

        executed = set(state_dict.get("executed_nodes", []))
        side_effect = set(state_dict.get("side_effect_nodes", ["execute_node", "fix_node"]))
        next_round = 0

        if node_name not in side_effect:
            pass
        elif node_name == "fix_node":
            next_round = state_dict.get("fix_round", 0) + 1
            round_key = f"{node_name}:{next_round}"
            if round_key in executed:
                state_dict.setdefault("execution_log", "")
                state_dict["execution_log"] += f"\n[SKIPPED] {round_key} already executed (resumed from checkpoint)\n"
                return state_dict
        elif node_name in executed:
            state_dict.setdefault("execution_log", "")
            state_dict["execution_log"] += f"\n[SKIPPED] {node_name} already executed (resumed from checkpoint)\n"
            return state_dict

        # 正常执行
        result = fn(state_dict)
        bc = result.pop("backend_calls", None)
        state_dict.update(result)
        if bc:
            state_dict.setdefault("backend_calls", {}).update(bc)

        # 标记已执行
        executed_list = list(state_dict.get("executed_nodes", []))
        if node_name == "fix_node":
            mark = f"{node_name}:{next_round}"
        else:
            mark = node_name
        if mark not in executed_list:
            executed_list.append(mark)
        state_dict["executed_nodes"] = executed_list

        return state_dict

    return guarded
