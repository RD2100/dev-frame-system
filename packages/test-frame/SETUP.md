# TestFrame 环境安装说明 (SETUP.md)

> 本文档列出所有需要人工安装或授权的步骤，**不要假装已经完成**。

---

## 一、基础环境

### 1.1 Python 3.10+

```bash
# 验证
python --version  # ≥ 3.10
```

未安装 → https://python.org/downloads/

### 1.2 Node.js 18+

```bash
# 验证
node --version  # ≥ 18
```

未安装 → https://nodejs.org/

### 1.3 Docker

```bash
# 验证
docker --version
```

需要Docker来运行MeterSphere。未安装 → https://docker.com/

### 1.4 Android SDK Platform Tools (ADB)

```bash
# 验证
adb --version
```

未安装 → https://developer.android.com/tools/releases/platform-tools

### 1.5 一键安装脚本

```bash
bash ci/scripts/setup-env.sh
```

---

## 二、各工具安装与授权

### 2.1 Maestro（Android冒烟测试）

**安装**：
```bash
curl -fsSL "https://get.maestro.mobile.dev" | bash
# 或 macOS
brew install maestro
```

**验证**：
```bash
maestro --version
```

**说明**：开源免费，不需要账户。

---

### 2.2 Airtest + Poco（Android回归测试）

**安装**：
```bash
pip install airtest pocoui
```

**验证**：
```python
python -c "import airtest; from airtest.core.api import *; print('OK')"
```

**说明**：开源免费，不需要账户。可选的Airtest IDE下载：https://airtest.netease.com/

---

### 2.3 Playwright（H5/uni-app测试）

**安装**：
```bash
npm init playwright@latest
# 安装浏览器
npx playwright install
```

**验证**：
```bash
npx playwright --version
```

**说明**：开源免费，不需要账户。

---

### 2.4 微信开发者工具 + miniprogram-automator

**人工步骤**：

1. **下载安装**：https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html
2. **登录**：使用微信扫描二维码登录
3. **开启自动化端口**：
   - 设置 → 安全设置 → 开启"服务端口"
   - 默认端口 9420
4. **记录CLI路径**：
   - Windows: `C:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat`
   - macOS: `/Applications/wechatwebdevtools.app/Contents/MacOS/cli`

**安装 npm 包**：
```bash
npm install miniprogram-automator jest --save-dev
```

**验证**：
```bash
# 启动开发者工具（自动化模式）
"$WECHAT_DEVTOOL_PATH" auto --port 9420 --open /path/to/miniprogram
```

**说明**：微信开发者工具超过500MB，无Docker镜像，需图形界面。

---

### 2.5 MeterSphere

**人工步骤**：

1. **Docker部署**（推荐）：
   ```bash
   docker run -d -p 8081:8081 \
     -v /opt/metersphere/data:/opt/metersphere/data \
     --name metersphere \
     metersphere/metersphere-allin-one:latest
   ```
   或使用SaaS版：https://metersphere.io/

2. **获取API Key**：
   - 登录 → 个人信息 → API Keys → 生成新Key
   - 设置环境变量：`export MS_API_KEY="your-key"`

3. **创建测试项目** → 导入API定义（Swagger/OpenAPI）

**验证**：
```bash
curl http://localhost:8081
# 默认账号: admin / metersphere
```

**说明**：自托管需4C8G以上服务器。开源免费。

---

### 2.6 Apifox

**人工步骤**：

1. **注册**：https://apifox.com/ → 微信/邮箱注册
2. **创建团队和项目**
3. **获取Mock地址**：项目设置 → Mock 服务 → 获取URL
4. **获取CLI**（可选）：
   ```bash
   npm install -g apifox-cli
   ```

**验证**：
- 浏览器打开 Mock URL，应返回Mock数据

**说明**：SaaS免费版有限制，私有化部署需付费。核心代码闭源。

---

### 2.7 WeTest（云真机）

**人工步骤**：

1. **注册**：https://wetest.qq.com/
2. **实名认证**（必需）
3. **获取API Key和Secret**：
   - 控制台 → 账号设置 → API密钥
4. **设置环境变量**：
   ```bash
   export WETEST_API_KEY="your-key"
   export WETEST_API_SECRET="your-secret"
   ```

**验证**：
```bash
# 登录控制台，手动创建一次兼容性测试
# 确认设备能成功连接并出报告
```

**说明**：按使用量计费，需预充值。免费额度极少。

⚠ **当前状态：API待验证** — 需要WeTest账户环境验证API的可用性。

---

### 2.8 Sentry

**选项A: SaaS**（推荐快速接入）

1. **注册**：https://sentry.io/ → GitHub/Google登录
2. **创建项目** → 选择平台（Android/iOS/Python等）
3. **获取DSN**：项目设置 → Client Keys (DSN)
4. **设置环境变量**：`export SENTRY_DSN="https://xxx@sentry.io/xxx"`

**选项B: Self-hosted**（数据安全要求高）

```bash
git clone https://github.com/getsentry/self-hosted.git
cd self-hosted
./install.sh
```

**验证**：
```bash
# SDK集成后触发一次测试崩溃，确认在Sentry Dashboard可见
```

**说明**：SaaS免费额度5K errors/月。Self-hosted免费无限量但需维护。

---

### 2.9 Bugly（崩溃监控）

**人工步骤**：

1. **注册**：https://bugly.qq.com/ → QQ/微信登录
2. **创建产品** → 获取 App ID 和 App Key
3. **设置环境变量**：
   ```bash
   export BUGLY_ANDROID_APP_ID="your-app-id"
   export BUGLY_ANDROID_APP_KEY="your-app-key"
   export BUGLY_MINIAPP_APP_ID="your-miniapp-id"
   ```

**验证**：
```bash
# SDK集成后触发一次崩溃，确认在Bugly控制台可见
```

**说明**：完全免费。国内访问速度快，原生支持微信小程序。

---

### 2.10 Allure（报告）

**安装**：
```bash
# macOS
brew install allure

# Linux
sudo apt install allure

# 通用（需Java）
npm install -g allure-commandline
```

**验证**：
```bash
allure --version
```

**说明**：开源免费。社区版无历史趋势，Allure TestOps需付费。

---

## 三、环境变量汇总

复制 `.env.template` 为 `.env` 并填入实际值：

```bash
# TestFrame 环境变量

# Android
export ANDROID_HOME=/path/to/android-sdk

# 微信开发者工具
export WECHAT_DEVTOOL_PATH="/path/to/wechat-devtools/cli"

# MeterSphere
export MS_API_KEY="your-api-key"
export MS_ACCESS_KEY="your-access-key"

# WeTest
export WETEST_API_KEY="your-api-key"
export WETEST_API_SECRET="your-api-secret"

# Sentry
export SENTRY_DSN="https://xxx@sentry.io/xxx"
export SENTRY_AUTH_TOKEN="your-auth-token"

# Bugly
export BUGLY_ANDROID_APP_ID="your-app-id"
export BUGLY_ANDROID_APP_KEY="your-app-key"
export BUGLY_MINIAPP_APP_ID="your-miniapp-app-id"

# 测试账号
export TEST_USER_PASSWORD="test_password"
export TEST_USER_TOKEN="test_token"
```

---

## 四、安装检查清单

| # | 工具 | 安装完成 | 授权完成 | 环境变量 | 验证通过 |
|---|------|---------|---------|---------|---------|
| 1 | Python 3.10+ | ☐ | — | — | ☐ |
| 2 | Node.js 18+ | ☐ | — | — | ☐ |
| 3 | Docker | ☐ | — | — | ☐ |
| 4 | ADB | ☐ | — | — | ☐ |
| 5 | Maestro | ☐ | — | — | ☐ |
| 6 | Airtest+Poco | ☐ | — | — | ☐ |
| 7 | Playwright | ☐ | — | — | ☐ |
| 8 | 微信开发者工具 | ☐ | ☐ 扫码登录 | ☐ | ☐ |
| 9 | MeterSphere | ☐ | ☐ API Key | ☐ | ☐ |
| 10 | Apifox | ☐ | ☐ 注册+项目 | ☐ | ☐ |
| 11 | WeTest | ☐ | ☐ 实名+充值 | ☐ | ☐ |
| 12 | Sentry | ☐ | ☐ DSN | ☐ | ☐ |
| 13 | Bugly | ☐ | ☐ App ID | ☐ | ☐ |
| 14 | Allure CLI | ☐ | — | — | ☐ |

---

## 变更审计

| 日期 | 变更人 | 变更内容 |
|------|--------|---------|
| 2026-05-21 | RD | 初始创建：14个工具的安装和授权步骤说明 |
