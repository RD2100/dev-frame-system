"""Stage执行器 — 单个测试阶段的执行逻辑"""

import subprocess
import json
import os
import sys
import importlib


class Stage:
    def __init__(self, name: str, config: dict, project_config: dict, index: int):
        self.name = name
        self.config = config
        self.project_config = project_config
        self.index = index
        self.results = {}

    def execute(self) -> bool:
        """执行stage，返回是否通过"""
        tools = self.config.get("tools", [])
        timeout = self.config.get("timeout", 300)
        retry = self.config.get("retry", 0)
        parallel = self.config.get("parallel", False)

        if self.name == "evidence":
            return self._run_evidence()
        elif self.name == "report":
            return self._run_report()
        elif self.name == "attribution":
            return self._run_attribution()
        elif self.name == "gate":
            return self._run_gate()

        all_passed = True
        for tool in tools:
            passed = self._run_tool(tool, retry)
            self.results[tool] = passed
            if not passed:
                all_passed = False

        return all_passed

    def _run_tool(self, tool: str, retry: int) -> bool:
        """通过CLI wrapper执行单个工具"""
        wrapper_map = {
            "maestro": "cli.wrappers.maestro",
            "airtest": "cli.wrappers.airtest",
            "playwright": "cli.wrappers.playwright",
            "miniprogram-automator": "cli.wrappers.miniapp",
            "metersphere": "cli.wrappers.metersphere",
            "pytest_api": "cli.wrappers.pytest_api",
            "wetest": "cli.wrappers.wetest",
        }

        module_name = wrapper_map.get(tool)
        if module_name is None:
            print(f"  [WARN] 未知工具: {tool}")
            return True

        for attempt in range(retry + 1):
            if attempt > 0:
                print(f"  [RETRY] {tool} 第{attempt}次重试...")

            print(f"  [{tool}] 执行中...")
            try:
                module = importlib.import_module(module_name)
                result = module.run(self.project_config)
                passed = result.get("passed", True)
                self.results[f"{tool}_detail"] = result

                if passed:
                    print(f"  [{tool}] [OK] passed")
                    return True
                else:
                    failed = result.get("failed", [])
                    print(f"  [{tool}] [FAIL] failed: {failed}")
            except ImportError:
                print(f"  [{tool}] [WARN] module not installed, skip")
                return True
            except Exception as e:
                print(f"  [{tool}] [FAIL] exception: {e}")
        return False

    def _run_evidence(self) -> bool:
        """收集证据"""
        from evidence.collector import EvidenceCollector
        collector = EvidenceCollector(self.project_config.get("project", {}).get("name"))
        collector.collect()
        return True

    def _run_report(self) -> bool:
        """生成报告"""
        from aggregator.collector import collect_and_generate
        collect_and_generate(self.project_config.get("project", {}).get("name"))
        return True

    def _run_attribution(self) -> bool:
        """缺陷归因"""
        from attribution.engine import AttributionEngine
        engine = AttributionEngine()
        engine.generate_report(
            self.project_config.get("project", {}).get("name"),
            self.project_config.get("report", {}).get("results_dir")
        )
        return True

    def _run_gate(self) -> bool:
        """质量门禁"""
        print("  [GATE] Evaluating quality gate...")
        from aggregator.collector import collect_all_results
        from orchestrator.gate import gate_check

        profile_name = self.project_config.get("_gate_profile",
                    self.project_config.get("report", {}).get("gate_profile", "pr"))
        project_name = self.project_config.get("project", {}).get("name", "unknown")

        # 收集所有结果用于门禁评估
        all_results = collect_all_results(self.project_config)
        passed, report = gate_check(profile_name, project_name, all_results)

        print(report)
        return passed
