"""任务编排引擎 — 按Stage串联工具执行"""

import time
import sys
from pathlib import Path

from orchestrator.stage import Stage
import config_loader


class Orchestrator:
    def __init__(self, project_name: str, profile_name: str = "smoke",
                 device: str = None, environment: str = "staging"):
        self.project_name = project_name
        self.profile_name = profile_name
        self.device = device
        self.environment = environment

        self.config = config_loader.load_config(project_name)
        self.profile = config_loader.load_profile(profile_name)

        self.results = {}
        self.start_time = None

    def print_plan(self):
        """打印执行计划"""
        stages = self.profile.get("stages", [])
        for i, stage_name in enumerate(stages):
            stage_config = self._find_stage_config(stage_name)
            tools = stage_config.get("tools", []) if stage_config else []
            print(f"  Stage {i}: [{stage_name}] -> tools: {tools}")

    def run(self) -> bool:
        """执行流水线，返回是否全部通过"""
        self.start_time = time.time()
        stages = self.profile.get("stages", [])
        all_passed = True

        for i, stage_name in enumerate(stages):
            stage_config = self._find_stage_config(stage_name)
            if stage_config is None:
                print(f"  [SKIP] Stage {i}: {stage_name} (未在 project 中配置)")
                continue

            stage = Stage(
                name=stage_name,
                config=stage_config,
                project_config=self.config,
                index=i,
            )

            print(f"\n{'='*60}")
            print(f"  Stage {i}: {stage_name}")
            print(f"{'='*60}")

            passed = stage.execute()

            self.results[stage_name] = {
                "passed": passed,
                "results": stage.results,
            }

            if not passed:
                all_passed = False
                on_failure = stage_config.get("on_failure", "continue")
                if on_failure == "abort":
                    print(f"\n  [FAIL] Stage {stage_name} failed, pipeline abort")
                    break
                else:
                    print(f"\n  [WARN] Stage {stage_name} failed, continue")

        elapsed = time.time() - self.start_time
        print(f"\n{'='*60}")
        print(f"  Pipeline done | {elapsed:.1f}s | {'[OK] PASS' if all_passed else '[FAIL] FAIL'}")
        print(f"{'='*60}")
        return all_passed

    def _find_stage_config(self, stage_name: str) -> dict:
        for s in self.config.get("stages", []):
            if s.get("stage") == stage_name:
                return s
        return None
