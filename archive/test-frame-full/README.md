# TestFrame — 通用自动化Bug发现体系

基于成熟工具组合的自动化质量保障平台。**不重复造轮子，只做组合、适配、统一入口和报告归因。**

## 覆盖范围

| 领域 | 工具 | 用途 |
|------|------|------|
| Android App 冒烟 | Maestro | YAML声明式，5分钟写测试流 |
| Android App 回归 | Airtest + Poco | 图像+控件双模式 |
| 微信小程序 | miniprogram-automator | 官方唯一方案 |
| H5 / uni-app | Playwright | 三引擎跨浏览器 |
| 后端 API | MeterSphere + Apifox | 测试管理+API设计+Mock |
| 云真机兼容性 | WeTest | 国产设备最全 |
| 崩溃监控 | Sentry + Bugly | 全栈+小程序崩溃 |
| 报告聚合 | Allure | 多框架适配 |
| CI/CD | GitHub Actions + Jenkins | 轻量+灵活 |
| 缺陷归因 | 自研规则引擎 | 透明可解释 |

## 快速开始

```bash
# 1. 环境安装
bash ci/scripts/setup-env.sh

# 2. 配置项目
cp config/projects/app-android.yaml config/projects/my-app.yaml
# 编辑 my-app.yaml 填入实际值

# 3. 运行冒烟测试
python -m cli.main run --project=my-app --profile=smoke

# 4. 查看报告
python -m cli.main report --project=my-app
```

## 项目结构

```
TestFrame/
├── config/          # 配置统一层
├── cli/             # 命令统一层
├── orchestrator/    # 任务编排层
├── evidence/        # 日志证据收集层
├── aggregator/      # 结果聚合层
├── attribution/     # 缺陷归因层
├── ci/              # CI/CD脚本
├── tests/           # 测试用例仓库
├── extensions/      # 三方工具配置
└── examples/        # 集成示例
```

## 文档

- [TOOL_SELECTION.md](TOOL_SELECTION.md) — 工具选型报告
- [ARCHITECTURE.md](ARCHITECTURE.md) — 集成架构设计
- [INTEGRATION_PLAN.md](INTEGRATION_PLAN.md) — 工具接入计划
- [PIPELINE.md](PIPELINE.md) — 测试流水线设计
- [SETUP.md](SETUP.md) — 环境安装说明
- [VERIFY.md](VERIFY.md) — 验收标准

## 核心理念

> **不自研已有工具的能力，只做胶水层：配置统一、命令统一、任务编排、证据收集、结果聚合、缺陷归因、CI调用。**
