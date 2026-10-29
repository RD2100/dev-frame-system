# H5/uni-app 自动化示例

本示例展示如何使用 Playwright 对 H5 和 uni-app 应用进行自动化测试。

## 前置条件

```bash
npm init playwright@latest
```

## 目录结构

```
examples/h5-uni-app/
├── README.md
├── playwright.config.ts
└── tests/
    ├── home.spec.ts
    ├── login.spec.ts
    └── checkout.spec.ts
```

## Playwright 配置

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  retries: 1,
  use: {
    baseURL: process.env.BASE_URL || 'https://h5.example.com',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'mobile-chrome', use: { ...devices['Pixel 5'] } },
    { name: 'mobile-safari', use: { ...devices['iPhone 14'] } },
  ],
});
```

## 测试示例

### 首页测试

```typescript
import { test, expect } from '@playwright/test';

test('首页加载成功', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/Example App/);
  await expect(page.locator('.hero-banner')).toBeVisible();
});

test('首页导航跳转', async ({ page }) => {
  await page.goto('/');

  // 点击"商品"标签
  await page.locator('nav').getByText('商品').click();
  await expect(page).toHaveURL(/\/products/);

  // 点击"我的"标签
  await page.locator('nav').getByText('我的').click();
  await expect(page).toHaveURL(/\/profile/);
});
```

### 登录测试

```typescript
test('手机号登录', async ({ page }) => {
  await page.goto('/login');

  await page.locator('#phone-input').fill('13800138000');
  await page.locator('.get-code-btn').click();

  // 等待验证码输入框出现
  await page.locator('#code-input').waitFor({ state: 'visible' });
  await page.locator('#code-input').fill('123456');

  await page.locator('#login-btn').click();

  // 断言跳转到首页
  await page.waitForURL('/home');
  await expect(page.locator('.user-avatar')).toBeVisible();
});

test('微信JS-SDK模拟', async ({ page }) => {
  // Mock wx JS-SDK
  await page.route('**/jweixin-1.6.0.js', route => {
    route.fulfill({
      contentType: 'application/javascript',
      body: `
        window.wx = {
          config: () => {},
          ready: (cb) => cb(),
          checkJsApi: () => {},
        };
      `
    });
  });

  await page.goto('/wechat-pay');
  // 测试微信支付页面渲染
  await expect(page.locator('.pay-amount')).toContainText('¥');
});
```

### 支付流程测试（网络Mock）

```typescript
test('完整下单支付流程', async ({ page }) => {
  // Mock 后端API
  await page.route('**/api/order/create', route => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: { orderId: 'test_order_123' } })
    });
  });

  await page.route('**/api/order/pay', route => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: { status: 'paid' } })
    });
  });

  await page.goto('/products/detail/1');
  await page.locator('.buy-now').click();
  await page.waitForURL('/order/confirm');

  await page.locator('.submit-order').click();
  await page.waitForURL('/order/result');

  await expect(page.locator('.result-title')).toContainText('支付成功');
});
```

### 移动端测试（触控模拟）

```typescript
test('移动端商品滑动浏览', async ({ page }) => {
  // 使用移动端设备配置
  await page.setViewportSize({ width: 375, height: 812 });

  await page.goto('/products');

  // 模拟上滑
  await page.mouse.wheel(0, 500);
  await page.waitForTimeout(500);
  await page.mouse.wheel(0, 500);

  // 断言加载了更多商品
  const items = page.locator('.product-card');
  await expect(await items.count()).toBeGreaterThan(5);
});
```

## 在CI中执行

```bash
# 所有浏览器
npx playwright test

# 仅移动端
npx playwright test --project=mobile-chrome --project=mobile-safari

# 生成HTML报告
npx playwright show-report

# 通过TestFrame
python -m cli.main run --project=h5-example --profile=smoke
```
