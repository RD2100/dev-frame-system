# TestFrame 验收标准 (VERIFY.md)

> 每个集成模块的验收标准和验证命令。

---

## Phase 0: 环境基础

- [ ] Python 3.10+ 可用
- [ ] Node.js 18+ 可用
- [ ] Docker 可用（MeterSphere需要）
- [ ] ADB 可用（Android测试需要）

```bash
python --version
node --version
docker --version
adb --version
```

---

## Phase 1: 胶水框架

- [ ] CLI入口可执行
- [ ] 配置加载正确（合并defaults+project+profile）
- [ ] 配置校验返回错误列表
- [ ] 支持 --dry-run 打印执行计划

```bash
# 验证CLI
python -m cli.main --help

# 验证配置加载
python -m cli.main check --project=app-android

# 验证dry-run
python -m cli.main run --project=app-android --profile=smoke --dry-run
```

---

## Phase 2: Maestro 冒烟测试

- [ ] Maestro CLI已安装
- [ ] 能执行登录YAML流
- [ ] 结果能转为统一JSON
- [ ] 截图自动收集

```bash
# 验证Maestro安装
maestro --version

# 执行测试流
maestro test tests/android/maestro/login-flow.yaml --format junit

# 通过TestFrame执行
python -m cli.main run --project=app-android --profile=smoke
```

---

## Phase 3: Airtest + Poco 回归测试

- [ ] Airtest能连接Android设备/模拟器
- [ ] Poco能识别UI控件
- [ ] 能执行Python测试脚本
- [ ] 结果能转为统一JSON

```bash
# 验证Airtest安装
python -c "import airtest; print('OK')"

# 验证设备连接
python -c "from airtest.core.api import connect_device; connect_device('Android:///'); print('Device OK')"

# 通过TestFrame执行
python -m cli.main run --project=app-android --profile=regression
```

---

## Phase 4: Playwright (H5/uni-app)

- [ ] Playwright已安装
- [ ] 能在3个浏览器引擎执行测试
- [ ] 移动端视口模拟正常
- [ ] JSON结果被适配器转换

```bash
# 验证安装
npx playwright --version

# 运行测试
npx playwright test tests/h5/playwright/

# 通过TestFrame
python -m cli.main run --project=h5-example --profile=smoke
```

---

## Phase 5: 微信小程序自动化

- [ ] 微信开发者工具能通过自动化模式启动
- [ ] miniprogram-automator能连接小程序运行时
- [ ] 能执行页面跳转、元素点击、数据读写
- [ ] Jest结果被适配器转换

```bash
# 启动开发者工具
"$WECHAT_DEVTOOL_PATH" auto --port 9420 --open /path/to/miniprogram

# 执行测试
npx jest tests/miniapp/specs/ --json

# 通过TestFrame
python -m cli.main run --project=app-miniapp --profile=smoke
```

---

## Phase 6: MeterSphere 接口测试

- [ ] MeterSphere部署成功
- [ ] 可创建测试计划并通过API触发
- [ ] API结果能被适配器转换

```bash
# 验证部署
curl http://localhost:8081

# 验证API
curl -X GET "http://localhost:8081/api/project/list" \
  -H "X-Api-Key: ${MS_API_KEY}"

# 通过TestFrame
python -m cli.main run --project=app-api --profile=smoke
```

---

## Phase 7: 云真机 (WeTest)

- [ ] WeTest API Key可用
- [ ] 能通过API上传APK
- [ ] 能获取测试结果

```bash
# 手动在WeTest控制台创建一次兼容性测试
# 确认设备连接、APK上传、报告生成正常

# 验证API（需要WeTest环境）
python -c "from cli.wrappers.wetest import run; print('API accessible')"
```

---

## Phase 8: 崩溃监控 (Sentry + Bugly)

- [ ] Sentry能接收崩溃上报
- [ ] Bugly能接收移动端崩溃
- [ ] 胶水层能通过API查询崩溃数据

```bash
# Sentry: 触发测试崩溃，确认Dashboard可见
# Bugly: 触发测试崩溃，确认Dashboard可见

# 验证API查询
python -c "from cli.wrappers.sentry import fetch_issues; print('OK')"
```

---

## Phase 9: 报告聚合 (Allure)

- [ ] Allure CLI已安装
- [ ] `allure generate` 能生成HTML报告
- [ ] 报告包含多工具来源的测试结果
- [ ] 截图/视频作为附件嵌入报告

```bash
# 验证安装
allure --version

# 生成报告
python -m cli.main report --project=app-android

# 查看报告
allure serve reports/allure-results/
```

---

## Phase 10: CI/CD

- [ ] GitHub Actions workflow能完整执行
- [ ] Jenkins Pipeline能完整执行
- [ ] 失败时自动通知

```bash
# GitHub Actions: 创建PR触发workflow
# Jenkins: 手动触发Pipeline

# 本地模拟
bash ci/scripts/run-tests.sh app-android smoke
```

---

## Phase 11: 缺陷归因

- [ ] 规则引擎能加载所有yaml规则文件
- [ ] 已知错误模式能被正确匹配
- [ ] 未匹配的回退到"人工分析"
- [ ] 归因报告格式完整

```bash
# 验证规则加载
python -c "
from attribution.engine import AttributionEngine
engine = AttributionEngine()
print(f'Loaded {len(engine.rules)} rules')
"

# 验证归因
python -m cli.main attribute --project=app-android
```

---

## 整体验收

```bash
# 端到端验证
python -m cli.main run --project=app-android --profile=smoke --dry-run
python -m cli.main check --project=app-android
python -m cli.main check --project=app-miniapp
python -m cli.main check --project=app-api
bash ci/scripts/setup-env.sh

# 无错误输出 = 胶水层集成正确
echo "✅ 所有胶水模块验证通过"
```

---

## 变更审计

| 日期 | 变更人 | 变更内容 |
|------|--------|---------|
| 2026-05-21 | RD | 初始创建：11个Phase验收标准+验证命令 |
