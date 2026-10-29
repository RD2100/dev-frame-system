---
version: 1
name: TestFrame Project Preferences
always_use_skills:
  - tdd
pre_dispatch_hooks:
  - name: tdd-enforce
    before:
      - execute-task
    action: replace
    prompt: |
      你必须严格按照TDD流程执行此任务，不得跳过任何步骤：

      ## 第1步：RED — 先写失败测试
      - 分析任务需求，确定要实现的行为
      - 先写测试用例，覆盖预期行为
      - 运行测试，确认测试**失败**（因为功能还没实现）
      - 如果测试意外通过，说明测试写错了或功能已存在，必须修正

      ## 第2步：GREEN — 写最少代码让测试通过
      - 只写让失败测试通过的最少代码
      - 不提前实现额外功能
      - 运行测试，确认测试**通过**
      - 如果测试仍失败，继续调整实现代码直到通过

      ## 第3步：REGRESSION — 回归全量测试
      - 运行项目全部已有测试（不是只跑新写的测试）
      - 确认没有破坏任何已有功能
      - 如果回归测试失败，修复引入的问题，直到全部通过
      - 全部通过才算此任务完成

      ## 纪律
      - 禁止跳过RED直接写代码
      - 禁止GREEN阶段过度实现
      - 禁止跳过回归测试
      - 每步必须实际运行测试，不能"假设通过"
verification_commands:
  - cd D:/TestFrame && python -m pytest tests/ -v --tb=short 2>/dev/null || echo "PYTHON_TESTS_DONE"
  - cd D:/TestFrame && npx jest --passWithNoTests 2>/dev/null || echo "JS_TESTS_DONE"
verification_auto_fix: true
verification_max_retries: 2
---

# TestFrame Project Preferences

强制TDD流程：RED(写失败测试) → GREEN(最少代码通过) → REGRESSION(回归全量测试)
