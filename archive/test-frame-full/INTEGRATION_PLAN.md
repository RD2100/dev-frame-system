# TestFrame 工具接入计划 (INTEGRATION_PLAN.md)

> 生成日期：2026-05-21 | 版本：v1.0 | 决策人：RD

---

## 一、接入顺序（按依赖关系）

```
Phase 0: 环境基础 (Python + Node.js + Docker)
    ↓
Phase 1: 胶水框架 (CLI + Config + Orchestrator)
    ↓
Phase 2: Android (Maestro → Airtest+Poco)
    ↓
Phase 3: H5 (Playwright)
    ↓
Phase 4: 微信小程序 (miniprogram-automator)
    ↓
Phase 5: 接口测试 + Mock (MeterSphere + Apifox)
    ↓
Phase 6: 云真机 (WeTest)
    ↓
Phase 7: 崩溃监控 (Sentry + Bugly)
    ↓
Phase 8: 报告聚合 (Allure)
    ↓
Phase 9: CI/CD (GitHub Actions + Jenkins)
    ↓
Phase 10: 缺陷归因 (自研规则引擎)
```

---

## 二、各工具接入详解

### Phase 0: 环境基础

**前置条件**：
```bash
# Python 3.10+
python --version

# Node.js 18+
node --version

# Docker (MeterSphere需要)
docker --version

# ADB (Android测试需要)
adb --version
```

**一键安装脚本** (`ci/scripts/setup-env.sh`)：
```bash
#!/bin/bash
# 检查并安装基础环境
echo ">>> 检查 Python..."
python3 --version || echo "请安装 Python 3.10+"

echo ">>> 检查 Node.js..."
node --version || echo "请安装 Node.js 18+"

echo ">>> 检查 ADB..."
adb --version || echo "请安装 Android SDK Platform Tools"

echo ">>> 安装 Python 依赖..."
pip install -r requirements.txt

echo ">>> 安装 Node.js 依赖..."
npm install
```

---

### Phase 1: 胶水框架搭建

**产出**：CLI骨架 + Config加载 + Orchestrator引擎

**实现步骤**：

1. **创建项目骨架**
```bash
mkdir -p config/projects config/tools config/profiles
mkdir -p cli/commands cli/wrappers
mkdir -p orchestrator
mkdir -p evidence/formatters evidence/storage
mkdir -p aggregator/adapters
mkdir -p attribution/rules attribution/output
mkdir -p ci/github-actions ci/jenkins ci/scripts
mkdir -p tests/android/maestro tests/android/airtest
mkdir -p tests/miniapp/specs tests/h5/playwright tests/api
mkdir -p extensions/sentry extensions/bugly extensions/allure
mkdir -p examples/android-app examples/wechat-miniapp examples/api-mock
mkdir -p reports backup docs/decisions docs/conventions
```

2. **Config加载模块** (`config/loader.py`):
```python
import yaml
import os

def load_config(project_name: str) -> dict:
    """加载项目配置，合并 defaults + project + profile"""
    base = _load_yaml("config/defaults.yaml")
    project = _load_yaml(f"config/projects/{project_name}.yaml")
    return _deep_merge(base, project)

def _load_yaml(path: str) -> dict:
    with open(path, 'r') as f:
        return yaml.safe_load(f)
```

3. **CLI入口** (`cli/main.py`):
```python
import click

@click.group()
def cli():
    """TestFrame - 通用自动化Bug发现体系"""
    pass

@cli.command()
@click.option('--project', required=True)
@click.option('--profile', default='smoke')
def run(project, profile):
    """执行测试"""
    from orchestrator.engine import Orchestrator
    Orch = Orchestrator(project, profile)
    Orch.run()

@cli.command()
@click.option('--project', required=True)
def report(project):
    """生成报告"""
    from aggregator.collector import collect_and_generate
    collect_and_generate(project)

if __name__ == '__main__':
    cli()
```

**验收标准**：
- [ ] `python -m cli.main --help` 输出帮助信息
- [ ] `python -m cli.main run --project=demo --profile=smoke` 不报配置加载错误
- [ ] 配置文件合并逻辑正确

---

### Phase 2: Android (Maestro + Airtest)

#### 2a. Maestro 冒烟测试接入

**安装**：
```bash
# macOS/Linux
curl -fsSL "https://get.maestro.mobile.dev" | bash

# 或通过包管理器
brew install maestro  # macOS
```

**接入步骤**：
1. 在 `tests/android/maestro/` 编写YAML测试流
2. 封装命令 `cli/wrappers/maestro.py`
3. 编写结果适配器 `aggregator/adapters/maestro_adapter.py`

**Maestro YAML示例** (`tests/android/maestro/login-flow.yaml`):
```yaml
appId: com.example.app
---
- launchApp
- assertVisible: "欢迎"
- tapOn: "登录"
- assertVisible: "手机号登录"
- inputText: "13800138000"
- tapOn: "获取验证码"
- inputText: "123456"
- tapOn: "登录"
- assertVisible: "首页"
```

**命令封装** (`cli/wrappers/maestro.py`):
```python
import subprocess
import os

def run_maestro(project_config: dict) -> dict:
    """执行Maestro冒烟测试"""
    flow_dir = project_config.get("maestro_flows", "tests/android/maestro/")
    flows = _find_flows(flow_dir)

    results = {"passed": [], "failed": [], "tool": "maestro"}
    for flow in flows:
        cmd = ["maestro", "test", flow, "--format", "junit"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            results["passed"].append(flow)
        else:
            results["failed"].append(flow)

    return results
```

**结果适配** (`aggregator/adapters/maestro_adapter.py`):
```python
def adapt_maestro_junit(junit_xml_path: str) -> list[dict]:
    """Maestro JUnit XML → 统一TestResult格式"""
    import xml.etree.ElementTree as ET
    tree = ET.parse(junit_xml_path)
    results = []
    for tc in tree.findall(".//testcase"):
        failure = tc.find("failure")
        results.append({
            "test_name": tc.get("name"),
            "status": "failed" if failure is not None else "passed",
            "tool": "maestro",
            "duration_ms": float(tc.get("time", 0)) * 1000,
            "error": {"message": failure.get("message")} if failure is not None else None
        })
    return results
```

#### 2b. Airtest + Poco 回归测试接入

**安装**：
```bash
pip install airtest pocoui
```

**接入步骤**：
1. 在 `tests/android/airtest/` 编写Python测试用例
2. 封装命令 `cli/wrappers/airtest.py`
3. 编写结果适配器 `aggregator/adapters/airtest_adapter.py`

**Airtest用例示例** (`tests/android/airtest/test_login.py`):
```python
from airtest.core.api import *
from poco.drivers.android.uiautomation import AndroidUiautomationPoco

poco = AndroidUiautomationPoco()

def test_login():
    poco("登录").click()
    poco("手机号").set_text("13800138000")
    poco("获取验证码").click()
    poco("验证码").set_text("123456")
    poco("登录按钮").click()
    assert_exists(Template("home_page.png"), "进入首页")
```

**命令封装** (`cli/wrappers/airtest.py`):
```python
def run_airtest(project_config: dict) -> dict:
    """执行Airtest回归测试"""
    test_dir = project_config.get("airtest_dir", "tests/android/airtest/")
    cmd = ["airtest", "run", test_dir,
           "--device", project_config.get("device", "Android:///"),
           "--log", "reports/airtest_log/"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return parse_airtest_output(r)
```

**验收标准**：
- [ ] Maestro能成功执行一个YAML测试流
- [ ] Airtest能连接Android设备/模拟器
- [ ] 两者结果都能转为统一JSON格式
- [ ] 截图/视频自动收集到reports目录

---

### Phase 3: Playwright (H5/uni-app)

**安装**：
```bash
npm init playwright@latest
# 或
npx playwright install
```

**接入步骤**：
1. 在 `tests/h5/playwright/` 编写测试
2. 封装命令 `cli/wrappers/playwright.py`
3. 配置移动端视口模拟

**Playwright配置** (`config/tools/playwright.yaml`):
```yaml
playwright:
  browsers: [chromium, firefox, webkit]
  devices:
    - "iPhone 14"
    - "Pixel 5"
  base_url: "https://h5.example.com"
  timeout: 30000
  screenshot: "on_failure"
  trace: "on_first_retry"
```

**命令封装** (`cli/wrappers/playwright.py`):
```python
def run_playwright(project_config: dict) -> dict:
    cmd = ["npx", "playwright", "test",
           "--config", "config/tools/playwright.yaml",
           "--reporter=json"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(r.stdout)
```

**验收标准**：
- [ ] Playwright能在3个浏览器引擎中执行测试
- [ ] 移动端视口模拟正常
- [ ] Trace录制可回放
- [ ] JSON结果被适配器正确转换

---

### Phase 4: miniprogram-automator (微信小程序)

**安装**：
```bash
# 安装微信开发者工具（手动）
# 下载：https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html

npm install miniprogram-automator --save-dev
```

**接入步骤**：
1. 微信开发者工具设置 → 安全设置 → 开启服务端口
2. 启动开发者工具（自动化模式）：
   ```bash
   /path/to/cli --auto --port 9420 --open /path/to/project
   ```
3. 编写测试 `tests/miniapp/specs/`
4. 封装启动脚本 `cli/wrappers/miniapp.py`

**启动脚本** (`cli/wrappers/miniapp.py`):
```python
def start_devtool(project_path: str, port: int = 9420):
    """启动微信开发者工具（自动化模式）"""
    devtool_path = os.environ.get("WECHAT_DEVTOOL_PATH",
                                   r"C:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat")
    subprocess.Popen([
        devtool_path, "auto", "--port", str(port),
        "--open", project_path
    ])
    time.sleep(5)  # 等待启动

def run_miniapp(project_config: dict) -> dict:
    """执行小程序自动化测试"""
    start_devtool(project_config["miniapp_path"])
    cmd = ["npx", "jest", "tests/miniapp/specs/", "--json"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(r.stdout)
```

**测试示例** (`tests/miniapp/specs/login.test.js`):
```javascript
const automator = require('miniprogram-automator');

describe('Login Flow', () => {
  let miniProgram;

  beforeAll(async () => {
    miniProgram = await automator.launch({
      projectPath: 'path/to/miniprogram'
    });
  });

  it('should login with phone', async () => {
    const page = await miniProgram.currentPage();
    await page.waitFor('#login-btn');
    await page.callMethod('goToLogin');
    await page.waitFor('.phone-input');
    // ...
  });

  afterAll(async () => {
    await miniProgram.close();
  });
});
```

**验收标准**：
- [ ] 微信开发者工具能通过自动化模式启动
- [ ] miniprogram-automator能连接到小程序运行时
- [ ] 能执行页面跳转、元素点击、数据读写
- [ ] Jest测试结果被适配器正确转换

---

### Phase 5: MeterSphere + Apifox (接口测试 + Mock)

#### 5a. MeterSphere 接口测试接入

**安装**（Docker部署）：
```bash
docker run -d -p 8081:8081 \
  -v /opt/metersphere/data:/opt/metersphere/data \
  --name metersphere metersphere/metersphere-allin-one
```

**接入步骤**：
1. 部署MeterSphere → 创建项目 → 导入API定义（Swagger/OpenAPI）
2. 创建测试场景 → 导出为JSON → 存入 `tests/api/metersphere/`
3. 封装API触发 `cli/wrappers/metersphere.py`

**API触发方式**：
```python
def run_metersphere(project_config: dict) -> dict:
    """通过MeterSphere API触发接口测试计划"""
    import requests
    config = project_config["metersphere"]
    resp = requests.post(
        f"{config['base_url']}/api/test/plan/run",
        headers={"X-Api-Key": config["api_key"]},
        json={"plan_id": config["test_plan_id"]}
    )
    return resp.json()
```

#### 5b. Apifox Mock接入

**接入步骤**：
1. 在Apifox中定义API → 开启Mock服务
2. 获取Mock Server URL（`https://mock.apifox.com/m1/xxx`）
3. 配置到项目配置文件

```yaml
# config/tools/apifox.yaml
apifox:
  mock_server: "https://mock.apifox.com/m1/1234567-default"
  project_id: "xxx"
  # Apifox CLI工具
  cli_path: "apifox-cli"
```

**验收标准**：
- [ ] MeterSphere部署成功，可创建测试计划
- [ ] MeterSphere API可被外部脚本触发执行
- [ ] Apifox Mock Server可用
- [ ] 接口测试结果能被适配器转换

---

### Phase 6: WeTest 云真机接入

**接入步骤**：
1. 注册WeTest账号：https://wetest.qq.com/
2. 获取API Key和Secret
3. 配置到 `config/tools/wetest.yaml`
4. 封装 `cli/wrappers/wetest.py`

**配置文件** (`config/tools/wetest.yaml`):
```yaml
wetest:
  api_key: "${WETEST_API_KEY}"
  api_secret: "${WETEST_API_SECRET}"
  device_pool: "top20_androids"
  app_package: "com.example.app"
```

**API封装**：
```python
def run_wetest(project_config: dict) -> dict:
    """上传APK到WeTest，触发兼容性测试"""
    config = project_config["wetest"]
    # 1. 上传APK
    upload_resp = _api_upload(config, project_config["apk_path"])
    # 2. 创建测试任务
    task_resp = _api_create_task(config, upload_resp["file_id"])
    # 3. 轮询结果
    results = _poll_results(config, task_resp["task_id"])
    return _format_wetest_results(results)
```

**验收标准**：
- [ ] WeTest API Key可用
- [ ] 能通过API上传APK并创建测试任务
- [ ] 能获取测试结果报告

---

### Phase 7: Sentry + Bugly 崩溃监控接入

#### 7a. Sentry 接入

**安装**（Self-hosted）：
```bash
# 或使用SaaS：https://sentry.io/
git clone https://github.com/getsentry/self-hosted.git
cd self-hosted
./install.sh
```

**App端集成**（Android示例）：
```gradle
// build.gradle
implementation 'io.sentry:sentry-android:7.0.0'
```

```xml
<!-- AndroidManifest.xml -->
<meta-data android:name="io.sentry.dsn" android:value="${SENTRY_DSN}" />
```

**配置** (`config/tools/sentry.yaml`):
```yaml
sentry:
  dsn: "${SENTRY_DSN}"
  environment: "staging"
  traces_sample_rate: 1.0
  profiles_sample_rate: 1.0
```

**胶水层**：通过Sentry REST API查询崩溃数据，聚合到报告。
```python
def fetch_sentry_issues(project_config: dict, build_id: str) -> list[dict]:
    """从Sentry API获取指定版本的崩溃数据"""
    import requests
    config = project_config["sentry"]
    resp = requests.get(
        f"{config['base_url']}/api/0/projects/{config['org']}/{config['project']}/issues/",
        headers={"Authorization": f"Bearer {config['auth_token']}"},
        params={"query": f"release:{build_id}"}
    )
    return resp.json()
```

#### 7b. Bugly 接入

**App端集成**（Android）：
```gradle
implementation 'com.tencent.bugly:crashreport:latest.release'
```

```java
// Application.onCreate()
Bugly.init(getApplicationContext(), "YOUR_APP_ID", true);
```

**小程序端集成**（原生支持）：
```javascript
// app.js
const bugly = requirePlugin('bugly')
bugly.init({ appId: 'YOUR_APP_ID' })
```

**配置** (`config/tools/bugly.yaml`):
```yaml
bugly:
  android_app_id: "${BUGLY_ANDROID_APP_ID}"
  miniapp_app_id: "${BUGLY_MINIAPP_APP_ID}"
```

**验收标准**：
- [ ] Sentry能接收到崩溃上报
- [ ] Bugly能接收到移动端崩溃和小程序崩溃
- [ ] 胶水层能通过API查询崩溃数据

---

### Phase 8: Allure 报告聚合接入

**安装**：
```bash
# macOS
brew install allure

# Linux
sudo apt install allure

# 或通过npm
npm install -g allure-commandline
```

**接入步骤**：
1. 安装Allure CLI
2. 实现 `aggregator/allure_writer.py`：将统一JSON写入 `allure-results/`
3. 实现 `cli/wrappers/allure.py`：生成HTML报告

**Allure Writer** (`aggregator/allure_writer.py`):
```python
import json
import uuid

def write_allure_results(test_results: list[dict], output_dir: str):
    """将统一TestResult写入Allure格式"""
    import os
    os.makedirs(output_dir, exist_ok=True)
    for result in test_results:
        allure_result = {
            "name": result["test_name"],
            "status": result["status"],
            "start": result.get("start_time"),
            "stop": result.get("stop_time"),
            "stage": "finished",
            "labels": [
                {"name": "tool", "value": result["tool"]},
                {"name": "stage", "value": result.get("stage")},
            ],
            "attachments": _build_attachments(result),
            "statusDetails": _build_status_details(result),
        }
        fname = f"{uuid.uuid4()}-result.json"
        with open(os.path.join(output_dir, fname), 'w') as f:
            json.dump(allure_result, f)

def generate_report(allure_results_dir: str, output_dir: str):
    cmd = ["allure", "generate", allure_results_dir, "-o", output_dir, "--clean"]
    subprocess.run(cmd)

def serve_report(allure_results_dir: str, port: int = 8080):
    cmd = ["allure", "serve", allure_results_dir, "-p", str(port)]
    subprocess.run(cmd)
```

**验收标准**：
- [ ] `allure generate` 能生成HTML报告
- [ ] 报告包含多工具来源的测试结果
- [ ] 截图/视频作为附件嵌入报告

---

### Phase 9: CI/CD (GitHub Actions + Jenkins)

#### 9a. GitHub Actions

**Workflow示例** (`ci/github-actions/android-smoke.yml`):
```yaml
name: Android Smoke Test
on:
  pull_request:
    paths: ['android/**']
  push:
    branches: [main]

jobs:
  smoke-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Setup environment
        run: bash ci/scripts/setup-env.sh

      - name: Start Android Emulator
        uses: reactivecircus/android-emulator-runner@v2
        with:
          api-level: 33
          script: echo "Emulator started"

      - name: Run Maestro Smoke Tests
        run: |
          python -m cli.main run --project=android-app --profile=smoke

      - name: Generate Allure Report
        if: always()
        run: |
          python -m cli.main report --project=android-app

      - name: Upload Report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-report
          path: reports/
```

#### 9b. Jenkins

**Jenkinsfile示例** (`ci/jenkins/Jenkinsfile-android`):
```groovy
pipeline {
    agent { label 'android' }
    environment {
        ANDROID_HOME = '/opt/android-sdk'
    }
    stages {
        stage('Setup') {
            steps {
                sh 'bash ci/scripts/setup-env.sh'
            }
        }
        stage('Smoke Test') {
            steps {
                sh 'python -m cli.main run --project=android-app --profile=smoke'
            }
        }
        stage('Regression Test') {
            when { expression { env.BRANCH_NAME == 'main' } }
            steps {
                sh 'python -m cli.main run --project=android-app --profile=regression'
            }
        }
        stage('Report') {
            steps {
                sh 'python -m cli.main report --project=android-app'
                allure includeProperties: false,
                       results: [[path: 'allure-results']]
            }
        }
    }
    post {
        failure {
            // 通知Sentry/IM
            sh 'python -m cli.main watch --project=android-app --build-id=${BUILD_ID}'
        }
    }
}
```

**验收标准**：
- [ ] GitHub Actions workflow能完整执行测试流程
- [ ] Jenkins Pipeline能完整执行测试流程
- [ ] 测试结果自动生成Allure报告
- [ ] 失败时自动通知

---

### Phase 10: 缺陷归因规则引擎

**实现** (`attribution/engine.py`):
```python
import yaml
import re

class AttributionEngine:
    def __init__(self, rules_dir="attribution/rules/"):
        self.rules = self._load_rules(rules_dir)

    def _load_rules(self, rules_dir: str) -> list:
        rules = []
        for f in os.listdir(rules_dir):
            if f.endswith('.yaml'):
                with open(os.path.join(rules_dir, f)) as f:
                    rules.extend(yaml.safe_load(f)["rules"])
        return rules

    def attribute(self, test_result: dict) -> dict:
        """对单个失败用例进行归因"""
        error_msg = test_result.get("error", {}).get("message", "")
        stack_trace = test_result.get("error", {}).get("stack_trace", "")

        for rule in self.rules:
            text_to_search = " ".join([
                stack_trace if "stacktrace" in rule.get("source", []) else "",
                error_msg if "error_message" in rule.get("source", []) else "",
            ])
            if re.search(rule["pattern"], text_to_search, re.IGNORECASE):
                return {
                    "test_name": test_result["test_name"],
                    "matched_rule": rule["id"],
                    **rule["attribution"]
                }

        return {
            "test_name": test_result["test_name"],
            "matched_rule": None,
            "root_cause": "未匹配已知规则",
            "severity": "P3",
            "suggestion": "人工分析"
        }

    def generate_report(self, attributed_results: list[dict]) -> str:
        """生成归因报告Markdown"""
        lines = ["# 缺陷归因报告", ""]
        for r in attributed_results:
            lines.append(f"## {r['test_name']}")
            lines.append(f"- **根因**: {r.get('root_cause', '未知')}")
            lines.append(f"- **严重程度**: {r.get('severity', 'P3')}")
            lines.append(f"- **建议修复**: {r.get('suggestion', '人工分析')}")
            lines.append("")
        return "\n".join(lines)
```

**验收标准**：
- [ ] 规则引擎能加载所有yaml规则文件
- [ ] 已知错误模式（NullPointer/Timeout/OOM）能被正确匹配
- [ ] 未匹配的错误返回"人工分析"建议
- [ ] 归因报告格式完整

---

## 三、接入检查清单

| # | 工具 | 安装完成 | 配置完成 | 命令封装 | 证据收集 | 结果适配 | CI集成 |
|---|------|---------|---------|---------|---------|---------|--------|
| 1 | Python 3.10+ | ☐ | ☐ | — | — | — | — |
| 2 | Node.js 18+ | ☐ | ☐ | — | — | — | — |
| 3 | Docker | ☐ | ☐ | — | — | — | — |
| 4 | ADB | ☐ | ☐ | — | — | — | — |
| 5 | Maestro CLI | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 6 | Airtest + Poco | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 7 | Playwright | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 8 | 微信开发者工具 | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 9 | MeterSphere | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 10 | Apifox | ☐ | ☐ | ☐ | — | — | — |
| 11 | WeTest | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 12 | Sentry | ☐ | ☐ | ☐ | ☐ | ☐ | — |
| 13 | Bugly | ☐ | ☐ | ☐ | ☐ | ☐ | — |
| 14 | Allure CLI | ☐ | ☐ | ☐ | — | ☐ | ☐ |
| 15 | GitHub Actions | ☐ | ☐ | — | — | — | ☐ |
| 16 | Jenkins | ☐ | ☐ | — | — | — | ☐ |
| 17 | 归因规则引擎 | — | ☐ | — | — | — | ☐ |

---

## 四、风险与缓解

| 风险 | 影响 | 缓解 | 状态 |
|------|------|------|------|
| 微信开发者工具无Docker镜像 | CI环境搭建困难 | 专用构建机预装开发者工具 | ⚠待处理 |
| WeTest API不稳定 | 云真机自动化受阻 | 先手动验证API可用性，再写封装 | ⚠待处理 |
| MeterSphere自托管资源消耗大 | 小团队部署困难 | 先用SaaS版本或轻量替代 | ⚠待处理 |
| Airtest图像识别在不同设备表现不一 | flaky test | 优先Poco控件模式 | ⚠待处理 |

---

## 变更审计

| 日期 | 变更人 | 变更内容 |
|------|--------|---------|
| 2026-05-21 | RD | 初始创建：10个Phase接入计划+检查清单 |
