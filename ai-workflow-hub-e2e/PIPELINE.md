# TestFrame 测试流水线设计 (PIPELINE.md)

> 生成日期：2026-05-21 | 版本：v1.0 | 决策人：RD

---

## 一、流水线总览

```
                      [Git Push / PR / Merge]
                              │
                              ▼
                    ┌──────────────────┐
                    │   CI/CD Trigger   │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Stage 0: 环境检查  │ (30s)
                    │  - Python/Node/ADB │
                    │  - 设备连接检测      │
                    │  - 配置校验          │
                    └────────┬─────────┘
                             │ ❌ fail → abort
                    ┌────────▼─────────┐
                    │ Stage 1: 静态检查   │ (2min)
                    │  - lint             │
                    │  - type check       │
                    │  - 敏感信息检查      │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Stage 2: 冒烟测试   │ (5-10min)
                    │  - Maestro(Android) │
                    │  - Playwright(H5)   │
                    │  - API冒烟(MeterS.) │
                    │  - 小程序冒烟        │
                    └────────┬─────────┘
                             │ ❌ fail → abort + 快速通知
                    ┌────────▼─────────┐
                    │ Stage 3: 核心回归   │ (15-30min, 并行)
                    │  - Airtest(Android) │
                    │  - Playwright(H5全量)│
                    │  - API全量(MeterS.) │
                    │  - 小程序核心路径    │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Stage 4: 兼容性     │ (30-60min, 可选/定时)
                    │  - WeTest云真机     │
                    │  - 多机型并行        │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Stage 5: 证据收集   │ (2min)
                    │  - 截图/视频/logcat │
                    │  - 崩溃日志(Sentry) │
                    │  - 网络HAR导出      │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Stage 6: 报告聚合   │ (3min)
                    │  - 多源结果聚合     │
                    │  - Allure报告生成   │
                    │  - 报告发布/归档    │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Stage 7: 缺陷归因   │ (1min)
                    │  - 规则引擎匹配     │
                    │  - 根因分析报告      │
                    │  - 建议修复方向      │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Stage 8: 质量门禁   │ (30s)
                    │  - 通过率 ≥ 阈值    │
                    │  - 崩溃率 ≤ 阈值    │
                    │  - 性能基线检查     │
                    │  → PASS / FAIL      │
                    └────────┬─────────┘
                             │
                    ┌────────┼────────┐
                    │                 │
              [PASS: 自动合并]   [FAIL: 阻断+告警]
                    │                 │
                    ▼                 ▼
            ┌──────────┐    ┌──────────────┐
            │ 部署通知   │    │ Sentry 告警    │
            │ Allure报告 │    │ IM 通知        │
            └──────────┘    │ 归因报告       │
                            └──────────────┘
```

---

## 二、触发策略

### 2.1 事件触发映射

| 触发事件 | 执行Stage | 用途 |
|---------|----------|------|
| **PR 创建** | Stage 0+1+2（冒烟） | 快速反馈，5-10分钟内出结果 |
| **PR merge → main** | Stage 0+1+2+3（冒烟+回归） | 全面检查，15-30分钟 |
| **Release Tag** | Stage 0+1+2+3+4+5+6+7+8（全量） | 发版前完整验证 |
| **定时（每日凌晨）** | Stage 0+3+4+5+6+7+8（回归+兼容性） | 每日质量巡检 |
| **手动触发** | 可指定任意Stage | 灵活组合 |

### 2.2 GitHub Actions 触发配置

```yaml
# PR 触发：仅冒烟
name: PR Smoke Test
on:
  pull_request:
    types: [opened, synchronize, reopened]
    branches: [main, develop]

# Main 分支合并：冒烟+回归
name: Main Regression
on:
  push:
    branches: [main]

# Release Tag：全量
name: Release Full Test
on:
  push:
    tags: ['v*']

# 定时：每日凌晨3点
name: Daily Quality Check
on:
  schedule:
    - cron: '0 3 * * *'
```

### 2.3 Jenkins 触发配置

```groovy
// 多分支流水线自动触发
triggers {
    // PR 触发
    pullRequest {
        cron('H/5 * * * *')
        // 匹配各Stage对应的分支策略
    }
    // 定时触发
    cron('H 3 * * *')
}
```

---

## 三、各Stage详细设计

### Stage 0: 环境检查（30s）

```
入口: 每次流水线启动
目标: 确保执行环境就绪
失败: ABORT（阻断后续所有Stage）
```

| 检查项 | 命令 | 通过标准 |
|--------|------|---------|
| Python版本 | `python --version` | ≥ 3.10 |
| Node.js版本 | `node --version` | ≥ 18 |
| ADB可用性 | `adb devices` | 至少1台设备/模拟器在线 |
| Maestro CLI | `maestro --version` | 命令可执行 |
| 配置文件完整 | `python -m cli.main check --project=xxx` | 所有必需配置项存在 |
| 设备连接 | `adb -s emulator-5554 shell getprop ro.product.model` | 设备响应 |

**实现** (`ci/scripts/setup-env.sh`):
```bash
#!/bin/bash
set -e
echo "🚀 [Stage 0] 环境检查..."

check_command() {
    if command -v $1 &> /dev/null; then
        echo "  ✅ $1: $(command -v $1)"
    else
        echo "  ❌ $1: 未安装"
        exit 1
    fi
}

check_command python
check_command node
check_command adb
check_command maestro

# 检查Python版本
python -c "import sys; assert sys.version_info >= (3, 10), 'Python too old'"

# 检查设备
DEVICE_COUNT=$(adb devices | grep -v "List" | grep "device$" | wc -l)
if [ "$DEVICE_COUNT" -eq 0 ]; then
    echo "  ❌ 无可用Android设备"
    exit 1
fi
echo "  ✅ 可用设备: $DEVICE_COUNT 台"

echo "✅ [Stage 0] 环境检查通过"
```

---

### Stage 1: 静态检查（2min）

```
入口: Stage 0 通过
目标: 代码质量门禁
失败: ABORT
```

| 检查项 | 工具 | 通过标准 |
|--------|------|---------|
| Android Lint | `./gradlew lint` | 无error级别问题 |
| Python类型检查 | `mypy` | 0 error |
| 敏感信息检查 | `git-secrets` | 无hardcoded secrets |
| 配置文件校验 | `yamllint` | 0 error |
| 依赖安全检查 | `pip-audit` / `npm audit` | 无critical漏洞 |

---

### Stage 2: 冒烟测试（5-10min）

```
入口: Stage 1 通过（PR场景Stage 0结束后直接进）
目标: 核心用户路径快速验证
失败: ABORT（PR阻断）+ 快速通知
策略: 各端并行执行
```

**并行策略**：

```
Stage 2: 冒烟测试
├── [并行] Android冒烟 (Maestro, ~3min)
│   ├── login-flow.yaml
│   ├── main-navigation.yaml
│   └── core-purchase.yaml
├── [并行] H5冒烟 (Playwright, ~2min)
│   ├── home.spec.ts
│   ├── login.spec.ts
│   └── checkout.spec.ts
├── [并行] API冒烟 (MeterSphere, ~2min)
│   └── smoke-test-plan (10个核心接口)
└── [并行] 小程序冒烟 (miniprogram-automator, ~3min)
    ├── login.test.js
    └── home.test.js
```

**覆盖范围**：
- Android：登录→首页→核心功能入口→购买（3-5个核心路径）
- H5：首页加载→登录→核心页面渲染（3-5个核心路径）
- API：认证→核心CRUD→健康检查（10个核心接口）
- 小程序：登录→首页→核心功能（2-3个核心路径）

**输出**：
- 各工具原始结果文件
- 截图/视频证据

---

### Stage 3: 核心回归（15-30min）

```
入口: Stage 2 通过（Main分支/Release Tag/定时触发）
目标: 核心功能全面回归
失败: CONTINUE（不阻断，收集完整报告）
策略: 各端并行 + 端内并行
```

**并行策略**：

```
Stage 3: 核心回归
├── [并行] Android 回归 (Airtest+Poco, ~15min)
│   ├── test_login.py (多种登录方式)
│   ├── test_home.py (首页所有模块)
│   ├── test_cart.py (购物车全流程)
│   ├── test_order.py (下单→支付→取消)
│   ├── test_profile.py (个人中心)
│   └── test_settings.py (设置页面)
├── [并行] H5 全量 (Playwright, ~10min)
│   ├── 全页面渲染验证
│   ├── 全功能路径验证
│   └── 跨浏览器 (Chrome+Firefox+WebKit)
├── [并行] API 全量 (MeterSphere, ~10min)
│   └── full-regression-plan (全量接口)
└── [并行] 小程序核心 (miniprogram-automator, ~10min)
    ├── login.test.js
    ├── home.test.js
    ├── order.test.js
    └── profile.test.js
```

**输出**：
- 各工具完整测试结果
- 全量证据包

---

### Stage 4: 兼容性测试（30-60min，可选）

```
入口: Release Tag / 定时触发
目标: 多机型兼容性验证
失败: CONTINUE
触发条件: 仅 Release Tag 或每日定时
```

**并行策略**：

```
Stage 4: 兼容性测试
├── WeTest 云真机 (并行20台设备, ~30min)
│   ├── 华为 Mate 60
│   ├── 小米 14
│   ├── OPPO Reno 11
│   ├── vivo X100
│   ├── ... (top20 机型)
│   └── 自动遍历+截图对比
├── Playwright 跨浏览器 (已包含在Stage 3)
│   └── Chromium + Firefox + WebKit
└── 小程序兼容性 (WeTest, ~20min)
    ├── iOS 微信
    ├── Android 微信
    └── 页面遍历
```

---

### Stage 5: 证据收集（2min）

```
入口: 前面各Stage完成后执行（无论成功/失败）
目标: 汇总所有证据
失败: CONTINUE（不影响主流程）
```

**收集内容**：
- 各工具截图和视频
- Android logcat（每个设备一份）
- Playwright Trace文件
- 网络请求HAR
- 崩溃堆栈（logcat中提取+Sentry/Bugly API拉取）
- 性能指标（CPU/内存/启动时间）

**输出**：
`reports/{project}/{date}/{build_id}/evidence.json`

```json
{
  "build_id": "abc123",
  "project": "my-android-app",
  "timestamp": "2026-05-21T03:00:00Z",
  "evidences": [
    {
      "type": "screenshot",
      "stage": "smoke",
      "tool": "maestro",
      "path": "screenshots/login_step1.png",
      "test": "登录流程",
      "timestamp": "2026-05-21T03:01:23Z"
    },
    {
      "type": "logcat",
      "stage": "regression",
      "tool": "airtest",
      "device": "emulator-5554",
      "path": "logcat/device_emulator-5554.log"
    },
    {
      "type": "crash",
      "stage": "regression",
      "source": "sentry",
      "issue_id": "CRASH-1234",
      "stack_trace": "..."
    }
  ]
}
```

---

### Stage 6: 报告聚合（3min）

```
入口: Stage 5 完成
目标: 多源结果 → 统一Allure报告
失败: CONTINUE（但标记报告不完整）
```

**处理流程**：

```
[Maestro JUnit XML] ──┐
[Airtest log JSON] ───┤
[Playwright JSON] ────┤
[MiniApp Jest JSON] ──┤
[MeterSphere API] ────┤
[WeTest API] ─────────┤
[Sentry Issues] ──────┤
[Bugly Crashes] ──────┤
                      ▼
            [结果适配器层]
              │
              ▼
            [Allure结果JSON]
              │
              ▼
            [allure generate]
              │
              ▼
        [Allure HTML Report]
              │
              ├──→ 归档到 reports/
              ├──→ 发布到托管服务器
              └──→ 发送链接到IM通知
```

---

### Stage 7: 缺陷归因（1min）

```
入口: Stage 6 报告聚合完成
目标: 对每个失败用例进行自动根因分析
失败: CONTINUE
```

**处理流程**：

```
[失败用例列表] → [AttributionEngine.attribute()]
        │
        ▼
[规则匹配]
├── 匹配成功 → 输出 {根因, 模块, 严重级别, 修复建议}
└── 未匹配   → 输出 {根因: "未知", 建议: "人工分析"}
        │
        ▼
[归因报告 Markdown]
        │
        ▼
[附加到 Allure 报告 / 发送到 IM]
```

---

### Stage 8: 质量门禁（30s）

```
入口: Stage 6+7 完成
目标: 基于指标判断是否通过质量门禁
输出: PASS（允许合并/上线）或 FAIL（阻断）
```

**门禁规则** (`config/gates/default.yaml`):

```yaml
gates:
  # PR 门禁（宽松）
  pr:
    smoke_pass_rate:
      min: 100            # 冒烟必须100%通过
    crash_free:
      min: 100            # 不能有新崩溃
    lint_errors:
      max: 0

  # Main 合并门禁（标准）
  main:
    regression_pass_rate:
      min: 95             # 回归≥95%
    smoke_pass_rate:
      min: 100
    crash_count:
      max: 0
    critical_bugs:
      max: 0

  # 发版门禁（严格）
  release:
    regression_pass_rate:
      min: 98             # 回归≥98%
    compatibility_pass_rate:
      min: 90             # 兼容性≥90%
    crash_free:
      min: 99.5           # 崩溃率<0.5%
    performance_regression:
      max: 0              # 无性能回退
    security_critical:
      max: 0              # 无严重安全问题
```

**判断逻辑**：

```python
def evaluate_gate(gate_type: str, metrics: dict) -> tuple[bool, str]:
    """
    返回 (是否通过, 原因描述)
    """
    rules = load_gate_config(gate_type)
    failures = []
    for metric, rule in rules.items():
        actual = metrics.get(metric)
        if actual is None:
            failures.append(f"{metric}: 无数据")
        elif 'min' in rule and actual < rule['min']:
            failures.append(f"{metric}: {actual} < {rule['min']}")
        elif 'max' in rule and actual > rule['max']:
            failures.append(f"{metric}: {actual} > {rule['max']}")

    passed = len(failures) == 0
    reason = "; ".join(failures) if failures else "所有指标达标"
    return passed, reason
```

---

## 四、通知策略

| 事件 | 渠道 | 内容 |
|------|------|------|
| Pipeline 启动 | IM（企业微信/钉钉/飞书） | 项目名/分支/触发人/预计耗时 |
| Stage 2 冒烟失败 | IM + Sentry Alert | 失败用例/截图/日志 |
| Pipeline 完成 | IM + Email | 通过率/耗时/报告链接 |
| 质量门禁 FAIL | IM + Sentry + Email | 未达标指标/归因报告/修复建议 |
| 新崩溃发现 | Sentry Alert + IM | 崩溃堆栈/影响版本/设备/用户数 |
| 每日巡检报告 | Email | 昨日质量趋势/新增问题/修复进度 |

---

## 五、时间预算

| Stage | PR场景 | Main合并 | Release发版 | 每日定时 |
|-------|--------|---------|-------------|---------|
| 0 环境检查 | ✅ 30s | ✅ 30s | ✅ 30s | ✅ 30s |
| 1 静态检查 | ✅ 2min | ✅ 2min | ✅ 2min | — |
| 2 冒烟测试 | ✅ 5-10min | ✅ 5-10min | ✅ 5-10min | — |
| 3 核心回归 | — | ✅ 15-30min | ✅ 15-30min | ✅ 15-30min |
| 4 兼容性 | — | — | ✅ 30-60min | ✅ 30-60min |
| 5 证据收集 | ✅ 1min | ✅ 2min | ✅ 2min | ✅ 2min |
| 6 报告聚合 | ✅ 3min | ✅ 3min | ✅ 3min | ✅ 3min |
| 7 缺陷归因 | ✅ 1min | ✅ 1min | ✅ 1min | ✅ 1min |
| 8 质量门禁 | ✅ 30s | ✅ 30s | ✅ 30s | ✅ 30s |
| **总计** | **~10-15min** | **~25-45min** | **~55-105min** | **~50-95min** |

---

## 六、并行度设计

```
最大化并行：
├── Stage 0-1: 串行（环境→检查）
├── Stage 2-3: 端间并行（Android ∥ H5 ∥ API ∥ 小程序）
├── Stage 4: 设备间并行（20台云真机同时执行）
├── Stage 5-6-7-8: 串行（依赖前序结果）
```

**GitHub Actions 矩阵示例**：

```yaml
jobs:
  # 端间并行
  android-smoke:
    runs-on: ubuntu-latest
    steps: [...]

  h5-smoke:
    runs-on: ubuntu-latest
    steps: [...]

  api-smoke:
    runs-on: ubuntu-latest
    steps: [...]

  # 汇聚
  aggregate:
    needs: [android-smoke, h5-smoke, api-smoke]
    runs-on: ubuntu-latest
    steps:
      - name: Collect Results
        run: python -m cli.main report --project=xxx
```

---

## 七、故障恢复

| 故障类型 | 恢复策略 |
|---------|---------|
| 设备连接断开 | 重试2次，仍失败则跳过该设备 |
| 单个测试用例超时 | 标记timeout，继续下一用例 |
| Allure报告生成失败 | 使用上次成功缓存，标记不完整 |
| 第三方服务（WeTest/Sentry）不可用 | 超时跳过，不阻断流水线 |
| CI构建机资源不足 | 降级串行执行，发送资源告警 |
| 网络中断 | 重试+指数退避，最多3次 |

---

## 八、监控大屏（可选）

```
┌─────────────────────────────────────────────────────┐
│              TestFrame 质量监控大屏                    │
├──────────────┬──────────────┬──────────────┬────────┤
│  今日执行次数  │   平均通过率   │   新崩溃数     │  门禁状态 │
│     23       │    96.5%     │      0        │  ✅ PASS │
├──────────────┴──────────────┴──────────────┴────────┤
│                                                       │
│  通过率趋势 (30天)                                     │
│  ████████▌███████████████▌██████████          98%    │
│                                                       │
│  项目质量状态                                         │
│  ├─ Android App    🟢 98.2%  0崩溃                  │
│  ├─ 微信小程序      🟢 97.1%  0崩溃                  │
│  ├─ H5             🟡 94.3%  1已知问题               │
│  └─ 后端API        🟢 99.8%  0错误                   │
│                                                       │
│  最近失败 Top 5                                       │
│  1. 支付页面-微信支付超时 (3次) → [归因报告]           │
│  2. 搜索-空结果页显示异常 (1次) → [归因报告]           │
│                                                       │
└─────────────────────────────────────────────────────┘
```

---

## 变更审计

| 日期 | 变更人 | 变更内容 |
|------|--------|---------|
| 2026-05-21 | RD | 初始创建：8 Stage流水线+触发策略+门禁规则+并行设计 |
