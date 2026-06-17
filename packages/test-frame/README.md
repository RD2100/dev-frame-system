# TestFrame — 通用自动化测试编排框架

**一句话**：把 Maestro、Playwright、Airtest、MiniProgram-Automator、MeterSphere、WeTest 等各自独立的测试工具，统一成一套可编排、可审计、不可静默通过的自动化测试流水线。

---

## P1 H5 Chromium Smoke and Allure Fallback

`playwright.cli` only proves the Playwright CLI/package is callable. Browser availability is checked separately by:

```powershell
python -m cli.main check --capability playwright.cli,playwright.browser.chromium --required playwright.cli --required playwright.browser.chromium --evidence artifacts\playwright.required.json
```

Repo-local H5 browser smoke is verified by:

```powershell
npx playwright install chromium
npm run test:h5:smoke
```

Allure HTML is a PASS only when `allure generate` exits 0 and `allure-report/index.html` exists. If Allure is unavailable, `python -m cli.main report --project=app-h5 --output artifacts\reports\app-h5` must write `allure-generation.json` with `BLOCKED` instead of claiming HTML was generated.

For CI profiles that require a real HTML report, use:

```powershell
python -m cli.main report --project=app-h5 --output artifacts\reports\app-h5 --require-html
```

With `--require-html`, both `BLOCKED` and `FAILED` Allure generation states exit non-zero.

## P1 H5 Auth Staging Profile Boundaries

H5 auth/staging readiness is split into browser, staging URL, credential env, and storageState layers:

| Capability | PASS condition | Does not prove |
|---|---|---|
| `playwright.cli` | The Playwright CLI/package is callable. | Browser binary availability or H5 E2E success. |
| `playwright.browser.chromium` | Chromium can launch and close through Playwright. | Any project route or login flow passed. |
| `h5.staging.env` | `H5_STAGING_BASE_URL` is present and is a valid `http(s)` URL. | The site is reachable, healthy, or authenticated. |
| `h5.auth.env` | `H5_AUTH_USERNAME` and `H5_AUTH_PASSWORD` are present. | Credentials are correct or login succeeds. |
| `h5.auth.storage_state` | `H5_AUTH_STORAGE_STATE` points to a valid Playwright storageState JSON file. | Cookies/tokens are current, authorized, or accepted by the backend. |

For an explicit H5 auth/staging readiness gate skeleton, use:

```powershell
python -m cli.main check --profile h5.auth.staging --evidence artifacts\h5.auth.staging.json
```

`h5.auth.staging` requires `playwright.cli`, `playwright.browser.chromium`, `h5.staging.env`, `h5.auth.env`, and `h5.auth.storage_state` to PASS. It does not visit the staging site, perform login, or run business H5 E2E. Evidence records only URL structure, env presence, and storageState counts; it must not include passwords, cookies, localStorage values, or URL query values.

For repo-local H5 auth login execution plumbing, use:

```powershell
node scripts\h5-auth-login.mjs --out artifacts\h5-auth\storage-state.json
python -m cli.main check --profile h5.auth.login.local --evidence artifacts\h5.auth.login.local.json
```

`h5.auth.login.local` requires `playwright.cli`, `playwright.browser.chromium`, `h5.auth.login.local`, and `h5.auth.storage_state.generated` to PASS. It only proves Chromium can complete the repo-local fake auth fixture and generate a structurally valid Playwright storageState. It does not prove real staging login, credential validity, backend authorization, business H5 E2E, cookie freshness, or full regression coverage. Generated storageState belongs under `artifacts/` and must not be committed.

For explicit real staging login opt-in, use:

```powershell
python -m cli.main check --profile h5.auth.login.staging.real --evidence artifacts\h5.auth.login.staging.real.json
```

`h5.auth.login.staging.real` requires `H5_REAL_LOGIN=true`, `H5_STAGING_BASE_URL`, `H5_AUTH_USERNAME`, `H5_AUTH_PASSWORD`, and the selector envs `H5_AUTH_USERNAME_SELECTOR`, `H5_AUTH_PASSWORD_SELECTOR`, `H5_AUTH_SUBMIT_SELECTOR`, `H5_AUTH_SUCCESS_SELECTOR`. Without explicit opt-in it must remain `BLOCKED`. Profile PASS proves only that one explicitly enabled staging login generated a structurally valid storageState; it does not prove long-term account validity, complete authorization, business H5 E2E, session freshness, or regression coverage. Generated staging storageState belongs under `artifacts/` and must not be committed.

## P1 Cloud Device Matrix Contract Boundaries

Cloud device compatibility readiness is split into env, local matrix contract, and fake provider layers:

| Capability | PASS condition | Does not prove |
|---|---|---|
| `cloud.device.env` | `CLOUD_DEVICE_PROVIDER`, `CLOUD_DEVICE_TOKEN`, `CLOUD_DEVICE_PROJECT_ID`, and `CLOUD_DEVICE_MATRIX_FILE` are present. | Cloud provider auth, quota, service reachability, or device availability. |
| `cloud.device.matrix.contract` | A local matrix JSON file and fake provider response pass the contract and status mapping. | Any real cloud device job was submitted, executed, or billed. |
| `cloud.device.provider.fake` | The built-in fake provider request/response contract passes. | A real BrowserStack/Firebase/Maestro Cloud integration exists. |

For an explicit cloud-device matrix readiness gate skeleton, use:

```powershell
python -m cli.main check --profile cloud.device.matrix.real --evidence artifacts\cloud.device.matrix.real.json
```

`cloud.device.matrix.real` requires `cloud.device.env` and `cloud.device.matrix.contract` to PASS. It does not call BrowserStack, Firebase Test Lab, Maestro Cloud, or any cloud provider; it does not upload APK/IPA/test packages and must not be reported as real compatibility coverage or cloud-device execution success.

For explicit cloud provider auth readiness, use:

```powershell
python -m cli.main check --profile cloud.device.provider.auth.real --evidence artifacts\cloud.device.provider.auth.real.json
```

`cloud.device.provider.auth.real` requires `cloud.device.env` and `cloud.device.provider.auth` to PASS. `cloud.device.provider.auth` is BLOCKED unless `CLOUD_DEVICE_REAL_AUTH=true` is set and `CLOUD_DEVICE_AUTH_URL` is configured. Profile PASS proves only provider auth readiness; it does not prove device capacity, app upload, matrix job creation, test execution, compatibility coverage, or billing safety.

## P1 Android ADB and Maestro Probe Boundaries

Android automation is split into environment layers:

| Capability | PASS condition | Does not prove |
|---|---|---|
| `android.adb.cli` | `adb version` exits 0. | Any device is connected. |
| `android.adb.devices` | `adb devices -l` reports at least one `device` state target. | App installed, UI smoke, or Maestro flow success. |
| `maestro.cli` | `maestro --version` exits 0. | A flow can run. |
| `maestro.flow.contract` | Minimal Maestro flow executes when CLI, device, and flow are present. | Full Android E2E coverage. |

Required device verification must use `android.adb.devices`, not `android.adb.cli`.

For an explicit real-device gate skeleton, use:

```powershell
python -m cli.main check --profile android.maestro.real --evidence artifacts\android.maestro.real.json
```

`android.maestro.real` requires `android.adb.cli`, `android.adb.devices`, `maestro.cli`, and `maestro.flow.contract` to PASS. On machines without adb, a device, or Maestro, this profile must exit non-zero while baseline preflight remains allowed to pass with optional `BLOCKED` evidence.

## P1 MiniApp DevTools and Automator Probe Boundaries

MiniApp automation is split into runtime layers:

| Capability | PASS condition | Does not prove |
|---|---|---|
| `miniapp.devtools.path` | A configured WeChat DevTools path exists. | The CLI can run. |
| `miniapp.devtools.cli` | The resolved DevTools CLI answers the lightweight help probe. | The automator endpoint is open. |
| `miniapp.automator.sdk` | Node can resolve the configured miniprogram automator package. | DevTools is running. |
| `miniapp.automator.endpoint` | The configured WebSocket endpoint completes the runtime probe handshake. | Full MiniApp UI E2E coverage. |

Required runtime verification must use `miniapp.automator.endpoint`, not `miniapp.devtools.path` or `miniapp.automator.sdk`.

For an explicit MiniApp automator endpoint gate skeleton, use:

```powershell
python -m cli.main check --profile miniapp.automator.real --evidence artifacts\miniapp.automator.real.json
```

`miniapp.automator.real` requires `miniapp.devtools.path`, `miniapp.devtools.cli`, `miniapp.automator.sdk`, and `miniapp.automator.endpoint` to PASS. On machines without WeChat DevTools, the automator package, or a configured endpoint, this profile must exit non-zero while baseline preflight remains allowed to pass with optional `BLOCKED` evidence. Profile PASS proves only the required probe chain, not full MiniApp UI E2E coverage.

## P1 MeterSphere Adapter Contract Boundaries

MeterSphere integration is split into environment, fake contract, and real auth layers:

| Capability | PASS condition | Does not prove |
|---|---|---|
| `metersphere.env` | Required env vars are present. | Real service authentication. |
| `metersphere.fake.contract` | Local fake MeterSphere report payload normalizes through the adapter contract. | A real MeterSphere instance is reachable. |
| `metersphere.real.auth` | Explicit real-auth profile reaches MeterSphere and receives valid auth JSON. | Test plan execution or API regression success. |
| `metersphere.testplan.env` | `METERSPHERE_TEST_PLAN_ID` is present. | The test plan exists, can run, or has results. |

Fake contract PASS must not be reported as real MeterSphere platform integration PASS.

For an explicit MeterSphere test-plan readiness gate skeleton, use:

```powershell
python -m cli.main check --profile metersphere.testplan.real --evidence artifacts\metersphere.testplan.real.json
```

`metersphere.testplan.real` requires `metersphere.env`, `metersphere.real.auth`, and `metersphere.testplan.env` to PASS. It does not execute a test plan. Profile PASS proves only environment, explicit real-auth readiness, and test plan id presence; it must not be reported as API regression or real test-plan execution success.

## 解决什么问题

团队做移动端/小程序/H5 测试时通常会引入多种工具——Android 冒烟用 Maestro，H5 用 Playwright，小程序用微信自动框架，API 用 MeterSphere。问题是：**每个工具的调用方式、返回值格式、失败语义都不一样**。跑完一圈后你拿到的是七份散落的结果，无法统一判断质量是否达标。

TestFrame 做的事情：
- **统一入口**：一条命令触发所有工具的测试
- **统一状态语义**：`passed / failed / skipped / blocked`，所有工具结果归一化
- **质量门禁**：自定义规则（如"冒烟通过率必须 100%，崩溃数必须为 0"），通过才放行
- **不可静默通过**：工具崩了、没装、配置错了不会假装"过了"
- **证据链可审计**：异常带完整调用栈，敏感信息自动脱敏，结果带数据来源标记

---

## 一条命令的执行流程

```
python -m cli.main run --project=fittrack --profile=smoke
         │
         ▼
   Orchestrator.run()
         │
         ├─► Stage "smoke":      _run_tool("pytest_api") / _run_tool("maestro") / ...
         ├─► Stage "regression": _run_tool("playwright") / _run_tool("airtest") / ...
         ├─► Stage "evidence":   收集各工具日志、截图、崩溃堆栈
         ├─► Stage "report":     生成 Allure HTML + Markdown 回归报告
         ├─► Stage "attribution":失败用例自动匹配已知缺陷规则
         └─► Stage "gate":       质量门禁判定 → passed / failed
```

---

## 支持的工具矩阵

| 工具 | 用途 | 接入方式 |
|------|------|---------|
| Maestro | Android 冒烟测试 | YAML 声明式，wrapper 封装 CLI |
| Airtest | Android 图像+控件回归 | wrapper 封装 `airtest run` |
| Playwright | H5 / Web 跨浏览器 | wrapper 封装 Playwright CLI |
| MiniProgram-Automator | 微信小程序 E2E | wrapper 封装 Jest + 微信 IDE |
| MeterSphere | API 接口测试 | wrapper 封装 HTTP API |
| Pytest | Python API 单测/集成 | wrapper 封装 pytest |
| WeTest | 云真机兼容性 | wrapper 封装 API（待真实环境验证） |

---

## 质量门禁

定义在 `config/gates.yaml`，三个预设档位：

| 档位 | 触发时机 | 规则示例 |
|------|---------|---------|
| PR | 代码提交 | smoke_pass_rate ≥ 100%, crash_count = 0 |
| Main | 合并主干 | regression_pass_rate ≥ 95%, critical_bugs = 0 |
| Release | 发版 | compatibility_pass_rate ≥ 90%, crash_free_rate ≥ 99.5% |

**安全设计**：blocked（工具不可用）默认计入失败；配置错误有 warning 不静默跳过；门禁数据来源可审计（`_source` 标记）。

---

## 项目结构

```
TestFrame/
├── cli/                CLI 入口 + 7 个工具 wrapper
│   ├── main.py         命令注册（run / report / attribute）
│   └── wrappers/	     各工具封装（maestro / playwright / airtest / miniapp / ...）
├── orchestrator/       任务编排引擎
│   ├── engine.py	     按 Stage 串联工具执行
│   ├── stage.py	         Stage 执行器（含状态推导、异常安全、重试）
│   └── gate.py	         质量门禁评估器
├── aggregator/         结果聚合
│   ├── collector.py	 收集多工具结果 → Allure + 摘要
│   ├── report.py	     生成 HTML / Markdown 回归报告
│   └── adapters/	     各工具的结果格式适配器
├── evidence/           证据收集（日志/截图/Maestro 输出）
├── attribution/        缺陷归因引擎（规则匹配 → 问题分类）
├── config/             配置中心（项目 / profile / gate / 设备 / 账号）
├── tests/              测试资产
│   ├── test_gate_semantics.py	  门禁语义测试
│   ├── test_stage_status.py	   Stage 状态 + 异常安全测试
│   ├── fittrack/		          FitTrack 场景测试
│   └── h5/			             Playwright H5 测试 + oracle
├── hooks/               CI preflight（pre-commit / pre-push）
└── governance/         治理白名单 + 漂移检测配置
```

---

## 本地验证

```bash
# Python 单元 / 集成测试（165 条）
python -m pytest tests/test_gate_semantics.py tests/test_stage_status.py \
  tests/test_evidence_collector.py tests/test_playwright_adapter.py \
  tests/test_regression_report.py tests/test_config_loader.py \
  tests/test_orchestrator_engine.py tests/test_aggregator_collector.py \
  tests/fittrack/test_models.py -q

# JS 业务 Oracle 测试（26 条）
node tests/h5/support/__tests__/oracles.test.js

# Jest 测试发现验证
npx jest --listTests --config=jest.config.js
```

---

## 核心理念

> **不自研已有工具的能力。TestFrame 是胶水层——把七种工具的输入输出统一起来，加上编排引擎和质量门禁，让流水线不再静默失败。**
