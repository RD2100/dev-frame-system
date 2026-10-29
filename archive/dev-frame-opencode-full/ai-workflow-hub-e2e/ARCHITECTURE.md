# TestFrame 集成架构设计 (ARCHITECTURE.md)

> 生成日期：2026-05-21 | 版本：v1.0 | 决策人：RD

---

## 一、架构总览

```
                          GitHub Actions / Jenkins (CI/CD 门禁)
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
              ┌─────▼─────┐        ┌─────▼─────┐        ┌─────▼─────┐
              │  代码提交   │        │  定时触发   │        │  手动触发   │
              └─────┬─────┘        └─────┬─────┘        └─────┬─────┘
                    │                     │                     │
                    └─────────────────────┼─────────────────────┘
                                          │
                    ┌─────────────────────▼─────────────────────┐
                    │         TestFrame CLI (命令统一入口)         │
                    │     tf run --profile=android_smoke          │
                    └─────────────────────┬─────────────────────┘
                                          │
                    ┌─────────────────────▼─────────────────────┐
                    │         任务编排层 (Orchestrator)            │
                    │   Stage 0: 环境检查 → Stage 1: 冒烟测试      │
                    │   → Stage 2: 回归测试 → Stage 3: 报告聚合    │
                    └───┬───────┬───────┬───────┬───────┬───────┘
                        │       │       │       │       │
        ┌───────────────┤       │       │       │       ├───────────────┐
        │               │       │       │       │       │               │
   ┌────▼────┐    ┌─────▼──┐ ┌──▼───┐ ┌─▼────┐ ┌▼──────┐    ┌────▼────┐
   │Maestro  │    │Airtest │ │mini- │ │Play- │ │Meter- │    │WeTest   │
   │Android  │    │+ Poco  │ │prog- │ │wright│ │Sphere │    │云真机    │
   │冒烟测试  │    │回归测试 │ │ram   │ │H5测试│ │API测试│    │兼容性    │
   │         │    │        │ │autom │ │      │ │       │    │         │
   └────┬────┘    └────┬───┘ └──┬───┘ └──┬───┘ └──┬────┘    └────┬────┘
        │              │        │        │        │              │
        └──────────────┼────────┼────────┼────────┼──────────────┘
                       │        │        │        │
                  ┌────▼────────▼────────▼────────▼────────────┐
                  │          日志和证据收集层 (Evidence)           │
                  │  截图 / 视频 / logcat / 网络日志 / 堆栈      │
                  └─────────────────────┬─────────────────────┘
                                        │
                  ┌─────────────────────▼─────────────────────┐
                  │          结果聚合层 (Allure Reporter)        │
                  │  多源测试结果 → 统一Allure报告               │
                  └─────────────────────┬─────────────────────┘
                                        │
                  ┌─────────────────────▼─────────────────────┐
                  │        缺陷归因规则引擎 (Attribution)         │
                  │  失败用例 → 规则匹配 → 根因分析 → 建议修复    │
                  └─────────────────────┬─────────────────────┘
                                        │
                  ┌─────────────────────▼─────────────────────┐
                  │             质量门禁 (Gate)                  │
                  │  通过率阈值 / 崩溃率 / 性能基线 → Pass/Fail  │
                  └───────────────────────────────────────────┘
                                        │
                          ┌─────────────┼─────────────┐
                          │             │             │
                    ┌─────▼─────┐ ┌────▼────┐ ┌─────▼─────┐
                    │  Allure   │ │ Sentry  │ │ MeterSphere│
                    │  报告页    │ │ 告警    │ │ 测试面板   │
                    └───────────┘ └─────────┘ └───────────┘
```

---

## 二、胶水层模块设计（7层）

### 2.1 配置统一层 (`config/`)

**职责**：统一管理所有工具的环境、设备、账号、超时等配置。

```
config/
├── defaults.yaml          # 全局默认配置
├── projects/              # 按项目分
│   ├── app-android.yaml   # Android App项目
│   ├── app-miniapp.yaml   # 微信小程序项目
│   └── app-api.yaml       # 后端API项目
├── devices.yaml           # 设备池配置
├── accounts.yaml          # 测试账号池
├── tools/                 # 各工具专属配置
│   ├── maestro.yaml       # Maestro环境
│   ├── airtest.yaml       # Airtest连接
│   ├── playwright.yaml    # 浏览器配置
│   ├── metersphere.yaml   # MeterSphere API地址
│   ├── wetest.yaml        # WeTest API Key
│   ├── sentry.yaml        # Sentry DSN
│   └── bugly.yaml         # Bugly AppID
└── profiles/              # 执行策略配置
    ├── smoke.yaml         # 冒烟测试
    ├── regression.yaml    # 全量回归
    └── compatibility.yaml # 兼容性测试
```

**配置示例** (`projects/app-android.yaml`):

```yaml
project:
  name: "my-android-app"
  package: "com.example.app"
  apk_path: "./build/app.apk"

stages:
  - stage: smoke
    tools: [maestro]
    timeout: 300
    retry: 1
  - stage: regression
    tools: [airtest]
    timeout: 1800
    retry: 2
  - stage: compatibility
    tools: [wetest]
    timeout: 3600
    retry: 0

devices:
  smoke: ["emulator-5554"]
  regression: ["emulator-5554", "emulator-5556"]
  compatibility: [wetest_pool: "top20_androids"]

report:
  format: allure
  path: "./reports/"
  retention: 30
```

---

### 2.2 命令统一层 (`cli/`)

**职责**：提供统一CLI入口，封装各工具的启动命令。

```bash
# 统一命令格式
tf run --project=my-android-app --profile=smoke
tf run --project=my-android-app --profile=regression --device=emulator-5554
tf run --project=my-miniapp --profile=smoke
tf run --project=my-api --profile=full --env=staging
tf report --project=my-android-app --date=2026-05-21
tf watch --project=my-android-app --build-id=1234
```

**实现方式**：Python Click/argparse → 读取配置 → 编排调度

```
cli/
├── __init__.py
├── main.py           # 主入口 (click)
├── commands/
│   ├── run.py        # tf run 命令
│   ├── report.py     # tf report 命令
│   └── watch.py      # tf watch 命令
└── wrappers/         # 各工具CLI封装
    ├── maestro.py    # 封装 maestro test
    ├── airtest.py    # 封装 airtest run
    ├── playwright.py # 封装 playwright test / npx playwright test
    ├── miniapp.py    # 封装 node miniprogram-automator
    ├── metersphere.py # 封装 ms-cli / curl
    ├── wetest.py     # 封装 WeTest API
    └── allure.py     # 封装 allure generate
```

---

### 2.3 任务编排层 (`orchestrator/`)

**职责**：按配置的stage顺序，串联执行各工具，处理依赖和失败重试。

```
orchestrator/
├── __init__.py
├── engine.py          # 核心编排引擎
├── stage.py           # Stage定义
├── context.py         # 执行上下文（设备状态、变量传递）
├── scheduler.py       # 并行/串行调度
└── hooks.py           # 生命周期钩子
```

**编排流程**：

```
env_check → smoke → [on_fail: abort]
         → regression → [on_fail: retry 2x]
         → compatibility → [on_fail: continue]
         → report_aggregate
         → attribution
         → gate_check
```

---

### 2.4 日志和证据收集层 (`evidence/`)

**职责**：统一收集各工具的日志、截图、视频、设备日志，关联到测试用例。

```
evidence/
├── __init__.py
├── collector.py       # 证据收集器
├── formatters/
│   ├── logcat.py      # Android logcat 采集
│   ├── screenshot.py  # 截图采集
│   ├── video.py       # 录屏采集
│   ├── network.py     # HAR/网络日志
│   └── crash.py       # 崩溃堆栈提取
└── storage/
    ├── local.py       # 本地存储
    └── upload.py      # 上传到MeterSphere/Sentry
```

**证据目录结构**：

```
reports/{project}/{date}/{build_id}/
├── maestro/
│   ├── screenshots/
│   └── videos/
├── airtest/
│   ├── screenshots/
│   ├── log/
│   └── airtest_report.html
├── playwright/
│   ├── traces/
│   └── screenshots/
├── logcat/
│   └── device_emulator-5554.log
└── evidence.json      # 证据索引
```

---

### 2.5 结果聚合层 (`aggregator/`)

**职责**：将各工具的测试结果转换为统一格式，聚合到Allure报告。

```
aggregator/
├── __init__.py
├── collector.py          # 结果收集
├── adapters/
│   ├── maestro_adapter.py    # Maestro JUnit XML → 统一格式
│   ├── airtest_adapter.py    # Airtest log → 统一格式
│   ├── playwright_adapter.py # Playwright JSON → 统一格式
│   ├── miniapp_adapter.py    # Jest结果 → 统一格式
│   └── metersphere_adapter.py # MeterSphere API → 统一格式
└── allure_writer.py      # 写入Allure结果JSON
```

**统一结果格式**：

```json
{
  "test_name": "登录流程-手机号登录",
  "status": "failed",
  "stage": "regression",
  "tool": "airtest",
  "duration_ms": 12340,
  "error": {
    "message": "LoginButton not found",
    "stack_trace": "...",
    "screenshot": "reports/.../screenshots/step_3.png"
  },
  "metadata": {
    "device": "emulator-5554",
    "app_version": "1.2.3"
  }
}
```

---

### 2.6 缺陷归因规则层 (`attribution/`)

**职责**：基于规则匹配失败结果，自动推断根因。

```
attribution/
├── __init__.py
├── engine.py             # 规则引擎
├── rules/
│   ├── android_crash.yaml    # Android崩溃归因规则
│   ├── api_error.yaml        # API错误归因规则
│   ├── ui_timeout.yaml       # UI超时归因规则
│   └── network_error.yaml    # 网络错误归因规则
└── output/
    └── attribution_report.md # 归因报告生成
```

**规则示例** (`android_crash.yaml`)：

```yaml
rules:
  - id: "crash-null-pointer"
    pattern: "NullPointerException"
    source: ["logcat", "stacktrace"]
    attribution:
      root_cause: "空指针异常"
      likely_module: "栈顶类所在模块"
      severity: "P0"
      suggestion: "检查对象初始化，添加null安全保护"

  - id: "crash-oom"
    pattern: "OutOfMemoryError"
    source: ["logcat", "stacktrace"]
    attribution:
      root_cause: "内存溢出"
      likely_module: "当前Activity/Fragment"
      severity: "P0"
      suggestion: "检查图片加载/大对象回收/内存泄漏"

  - id: "ui-timeout"
    pattern: ".*timeout.*|.*not found.*"
    source: ["error_message"]
    attribution:
      root_cause: "UI元素超时或未找到"
      likely_module: "对应页面"
      severity: "P1"
      suggestion: "检查元素ID/文本是否变更，增加等待时间或重试"
```

---

### 2.7 CI/CD 调用脚本 (`ci/`)

**职责**：封装在GitHub Actions和Jenkins中调用TestFrame的脚本。

```
ci/
├── github-actions/
│   ├── android-smoke.yml
│   ├── android-regression.yml
│   ├── miniapp-test.yml
│   └── api-test.yml
├── jenkins/
│   ├── Jenkinsfile-android
│   ├── Jenkinsfile-miniapp
│   └── Jenkinsfile-api
└── scripts/
    ├── setup-env.sh       # 一键环境安装
    ├── run-tests.sh       # 测试启动脚本
    └── collect-results.sh # 结果收集脚本
```

---

## 三、项目目录总结构

```
TestFrame/
├── TOOL_SELECTION.md       # 工具选型报告
├── ARCHITECTURE.md         # 此文件：集成架构设计
├── INTEGRATION_PLAN.md     # 工具接入计划
├── PIPELINE.md             # 测试流水线设计
├── SETUP.md                # 环境安装说明
├── VERIFY.md               # 验收标准
├── README.md               # 项目说明
│
├── config/                 # 配置统一层
│   ├── defaults.yaml
│   ├── projects/
│   ├── devices.yaml
│   ├── accounts.yaml
│   ├── tools/
│   └── profiles/
│
├── cli/                    # 命令统一层
│   ├── main.py
│   ├── commands/
│   └── wrappers/
│
├── orchestrator/           # 任务编排层
│   ├── engine.py
│   ├── stage.py
│   └── scheduler.py
│
├── evidence/               # 日志证据收集层
│   ├── collector.py
│   ├── formatters/
│   └── storage/
│
├── aggregator/             # 结果聚合层
│   ├── collector.py
│   ├── adapters/
│   └── allure_writer.py
│
├── attribution/            # 缺陷归因层
│   ├── engine.py
│   └── rules/
│
├── ci/                     # CI/CD 脚本
│   ├── github-actions/
│   ├── jenkins/
│   └── scripts/
│
├── tests/                  # 测试用例仓库
│   ├── android/
│   │   ├── maestro/        # Maestro冒烟测试YAML
│   │   └── airtest/        # Airtest回归测试Python
│   ├── miniapp/
│   │   └── specs/          # miniprogram-automator测试
│   ├── h5/
│   │   └── playwright/     # Playwright测试
│   └── api/
│       ├── metersphere/    # MeterSphere导出用例
│       └── postman/        # 备用Postman Collection
│
├── extensions/             # 三方工具配置/扩展
│   ├── sentry/
│   │   └── sentry.properties
│   ├── bugly/
│   │   └── bugly-config.json
│   └── allure/
│       └── categories.json
│
├── examples/               # 集成示例
│   ├── android-app/
│   ├── wechat-miniapp/
│   ├── api-mock/
│   └── h5-uni-app/
│
├── reports/                # 报告输出（gitignore）
│   └── .gitkeep
│
├── backup/                 # 备份目录
├── docs/                   # 过程文档
│   ├── decisions/          # 架构决策记录
│   └── conventions/        # 编码规范
│
├── requirements.txt        # Python依赖
├── pyproject.toml          # 项目元数据
└── .gitignore
```

---

## 四、工具与胶水层交互关系

| 工具 | 配置层 | 命令封装 | 证据收集 | 结果适配 | CI调用 |
|------|--------|---------|---------|---------|--------|
| **Maestro** | `tools/maestro.yaml` | `wrappers/maestro.py` | 截图/视频 | `maestro_adapter.py` (JUnit XML) | `ci/scripts/` |
| **Airtest+Poco** | `tools/airtest.yaml` | `wrappers/airtest.py` | 截图/log/录屏 | `airtest_adapter.py` (log→JSON) | `ci/scripts/` |
| **miniprogram-automator** | `tools/miniapp.yaml` | `wrappers/miniapp.py` | 截图/console | `miniapp_adapter.py` (Jest) | `ci/scripts/` |
| **Playwright** | `tools/playwright.yaml` | `wrappers/playwright.py` | Trace/截图 | `playwright_adapter.py` (JSON) | `ci/scripts/` |
| **MeterSphere** | `tools/metersphere.yaml` | `wrappers/metersphere.py` | API响应+日志 | `metersphere_adapter.py` (API) | `ci/scripts/` |
| **WeTest** | `tools/wetest.yaml` | `wrappers/wetest.py` | 图/视频/日志 | `wetest_adapter.py` (API) | `ci/scripts/` |
| **Sentry** | `tools/sentry.yaml` | — (被动采集) | 崩溃堆栈 | `sentry_adapter.py` (API) | — |
| **Bugly** | `tools/bugly.yaml` | — (被动采集) | 崩溃堆栈 | `bugly_adapter.py` (API) | — |
| **Allure** | — | `wrappers/allure.py` | — | `allure_writer.py` (写入) | — |

---

## 五、数据流

```
[各工具执行] → [原始结果] → [Adapter转换] → [统一JSON] → [Allure Writer]
                                                              │
                                              ┌────────────────┘
                                              ▼
                                    [Allure Report HTML]
                                              │
                          ┌───────────────────┼───────────────────┐
                          ▼                   ▼                   ▼
                  [JIRA/TAPD缺陷]      [Sentry告警]        [MeterSphere面板]
```

**证据流**：

```
[截图/视频/logcat] → [按照 "{project}/{date}/{build_id}/{tool}/" 归档]
        │
        ▼
[evidence.json 索引] → [上传到 MeterSphere / 本地保留]
        │
        ▼
[Allure附件引用]
```

---

## 六、扩缩容设计

### 水平扩展
- **Android并行测试**：多设备通过ADB多实例，编排层支持并行stage
- **H5并行测试**：Playwright内置多worker并行
- **API并行测试**：MeterSphere分布式执行节点

### 工具替换
- 胶水层抽象工具接口，替换工具时只需实现新Adapter
- 例如：Appium替换Airtest → 只写 `appium_adapter.py`，不改编排层

### 项目扩展
- 新项目只需加 `config/projects/new-project.yaml` + `tests/new-project/`
- 胶水层零代码修改

---

## 变更审计

| 日期 | 变更人 | 变更内容 |
|------|--------|---------|
| 2026-05-21 | RD | 初始创建：7层胶水架构+工具交互关系+目录结构 |
