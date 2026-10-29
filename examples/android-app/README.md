# Android App 自动化示例

本示例展示如何使用 Maestro + Airtest 对 Android App 进行冒烟测试和回归测试。

## 前置条件

```bash
# 安装Maestro
curl -fsSL "https://get.maestro.mobile.dev" | bash

# 安装Airtest
pip install airtest pocoui

# ADB连接设备
adb devices
```

## 目录结构

```
examples/android-app/
├── README.md
├── maestro/                     # Maestro冒烟测试
│   ├── login-flow.yaml
│   ├── main-navigation.yaml
│   └── purchase-flow.yaml
├── airtest/                     # Airtest回归测试
│   ├── conftest.py
│   ├── test_login.py
│   ├── test_home.py
│   └── test_order.py
└── config.yaml
```

## 冒烟测试 (Maestro)

### 1. 登录流程 (`maestro/login-flow.yaml`)

```yaml
appId: com.example.app
---
- launchApp
- assertVisible: "欢迎使用"
- takeScreenshot: screenshots/welcome

- tapOn: "登录"
- assertVisible: "手机号登录"

# 输入手机号
- tapOn:
    id: "com.example.app:id/et_phone"
- inputText: "13800138000"

# 获取验证码
- tapOn: "获取验证码"

# 输入验证码
- tapOn:
    id: "com.example.app:id/et_code"
- inputText: "123456"

- tapOn:
    id: "com.example.app:id/btn_login"
- assertVisible: "首页"

- takeScreenshot: screenshots/home
```

### 2. 主导航 (`maestro/main-navigation.yaml`)

```yaml
appId: com.example.app
---
- launchApp
- assertVisible: "首页"

# 切换到"发现"页
- tapOn: "发现"
- assertVisible: "推荐"

# 切换到"购物车"
- tapOn: "购物车"
- assertVisible: "我的购物车"

# 切换到"我的"
- tapOn: "我的"
- assertVisible: "个人中心"
```

### 3. 执行冒烟测试

```bash
# 通过Maestro直接执行
maestro test examples/android-app/maestro/

# 通过TestFrame统一入口
python -m cli.main run --project=android-example --profile=smoke
```

## 回归测试 (Airtest + Poco)

### 1. 配置文件 (`conftest.py`)

```python
import pytest
from airtest.core.api import *
from poco.drivers.android.uiautomation import AndroidUiautomationPoco

@pytest.fixture(scope="session")
def poco():
    """连接设备并返回Poco实例"""
    auto_setup(__file__)
    return AndroidUiautomationPoco()

@pytest.fixture(scope="function")
def screenshot_on_failure(request, poco):
    """失败时自动截图"""
    yield
    if request.node.rep_call.failed:
        snapshot(filename=f"reports/screenshots/{request.node.name}.png")
```

### 2. 登录测试 (`test_login.py`)

```python
import pytest
from airtest.core.api import *

def test_phone_login(poco):
    """手机号+验证码登录"""
    poco(text="登录").click()
    poco("com.example.app:id/et_phone").set_text("13800138000")
    poco(text="获取验证码").click()

    import time; time.sleep(1)
    poco("com.example.app:id/et_code").set_text("123456")
    poco("com.example.app:id/btn_login").click()

    # 断言进入首页
    poco(text="首页").wait_for_appearance(timeout=10)
    assert_exists(Template("home_icon.png"), "未进入首页")

def test_wechat_login(poco):
    """微信登录"""
    poco(text="登录").click()
    poco(text="微信登录").click()

    # 等待微信授权跳转（此功能需配合微信应用）
    poco(text="同意").wait_for_appearance(timeout=30)
    poco(text="同意").click()

    poco(text="首页").wait_for_appearance(timeout=10)

def test_logout(poco):
    """退出登录"""
    # 进入"我的"页面
    poco(text="我的").click()
    poco(text="设置").click()
    poco(text="退出登录").click()
    poco(text="确认").click()

    # 验证回到登录页
    poco(text="登录").wait_for_appearance(timeout=5)
```

### 3. 首页测试 (`test_home.py`)

```python
def test_home_banner_display(poco):
    """首页Banner展示"""
    poco(text="首页").click()
    banner = poco("com.example.app:id/banner")
    assert banner.exists(), "Banner未显示"

def test_home_recommend_list(poco):
    """首页推荐列表"""
    poco(text="首页").click()
    # 滑动查看推荐列表
    poco.scroll(direction="vertical", percent=0.5)
    items = poco("com.example.app:id/item_title")
    assert len(items) > 0, "推荐列表为空"

def test_search_function(poco):
    """搜索功能"""
    poco(text="首页").click()
    poco("com.example.app:id/search_bar").click()
    poco("com.example.app:id/search_input").set_text("测试商品")
    poco("com.example.app:id/search_btn").click()

    # 断言搜索结果
    result_list = poco("com.example.app:id/search_result_list")
    result_list.wait_for_appearance(timeout=5)
```

### 4. 执行回归测试

```bash
# 通过Airtest直接执行
python -m pytest tests/android/airtest/ -v

# 通过TestFrame统一入口
python -m cli.main run --project=android-example --profile=regression
```

## 在CI中集成

### GitHub Actions (简化)

```yaml
- name: Maestro Smoke Test
  run: |
    maestro test examples/android-app/maestro/ --format junit

- name: Airtest Regression
  run: |
    python -m pytest examples/android-app/airtest/ -v --json-report
```

## 注意事项

1. **图像识别稳定性**：优先使用Poco控件模式，图像识别仅兜底游戏/自定义View
2. **设备连接**：确保 `adb devices` 能看到设备
3. **Airtest IDE**：可用Airtest IDE录制脚本，导出后手动优化
4. **截图基准**：图像识别截图需与测试设备分辨率一致
