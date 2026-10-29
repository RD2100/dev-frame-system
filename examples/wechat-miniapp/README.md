# 微信小程序自动化示例

本示例展示如何使用 miniprogram-automator 对微信小程序进行E2E自动化测试。

## 前置条件

1. 安装 Node.js 18+
2. 安装微信开发者工具 [下载](https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html)
3. 开启开发者工具的"安全设置 → 服务端口"
4. 安装依赖: `npm install miniprogram-automator jest --save-dev`

## 目录结构

```
examples/wechat-miniapp/
├── README.md
├── package.json
├── jest.config.js
└── specs/
    ├── login.test.js
    ├── home.test.js
    └── order.test.js
```

## 测试示例

### 1. 登录测试 (`specs/login.test.js`)

```javascript
const automator = require('miniprogram-automator');

describe('小程序登录流程', () => {
  let miniProgram;
  let page;

  beforeAll(async () => {
    // 启动小程序（自动化模式）
    miniProgram = await automator.launch({
      projectPath: process.env.MINIPROGRAM_PATH || './miniprogram',
      cliPath: process.env.WECHAT_DEVTOOL_PATH,
    });
  });

  beforeEach(async () => {
    page = await miniProgram.currentPage();
  });

  it('应该显示登录按钮', async () => {
    const loginBtn = await page.$('#login-btn');
    expect(loginBtn).toBeTruthy();
  });

  it('手机号登录流程', async () => {
    // 点击登录按钮
    const loginBtn = await page.$('#login-btn');
    await loginBtn.tap();

    // 等待登录页面渲染
    await page.waitFor(1000);
    const phonePage = await miniProgram.currentPage();

    // 输入手机号
    const phoneInput = await phonePage.$('.phone-input input');
    await phoneInput.input('13800138000');

    // 点击获取验证码
    const codeBtn = await phonePage.$('.get-code-btn');
    await codeBtn.tap();

    // 输入验证码
    const codeInput = await phonePage.$('.code-input input');
    await codeInput.input('123456');

    // 点击登录
    const submitBtn = await phonePage.$('.submit-btn');
    await submitBtn.tap();

    // 等待跳转到首页
    await miniProgram.waitFor(2000);
    const homePage = await miniProgram.currentPage();
    expect(homePage.path).toBe('pages/home/home');
  });

  it('微信授权登录', async () => {
    // Mock wx.login
    await miniProgram.mockWxMethod('login', { code: 'mock_auth_code' });
    await miniProgram.mockWxMethod('getUserInfo', {
      userInfo: {
        nickName: 'TestUser',
        avatarUrl: 'https://example.com/avatar.png'
      }
    });

    const loginBtn = await page.$('#wechat-login-btn');
    await loginBtn.tap();

    await miniProgram.waitFor(2000);
    const homePage = await miniProgram.currentPage();
    expect(homePage.path).toBe('pages/home/home');
  });

  afterAll(async () => {
    await miniProgram.close();
  });
});
```

### 2. 首页测试 (`specs/home.test.js`)

```javascript
describe('小程序首页', () => {
  let miniProgram;

  beforeAll(async () => {
    miniProgram = await automator.launch({
      projectPath: process.env.MINIPROGRAM_PATH || './miniprogram',
    });
    // 直接导航到首页
    await miniProgram.navigateTo('/pages/home/home');
  });

  it('首页Banner轮播', async () => {
    const page = await miniProgram.currentPage();
    const swiper = await page.$('.banner-swiper');
    expect(swiper).toBeTruthy();
  });

  it('首页商品列表加载', async () => {
    const page = await miniProgram.currentPage();
    // 等待数据加载
    await page.waitFor(2000);
    const items = await page.$$('.product-item');
    expect(items.length).toBeGreaterThan(0);
  });

  afterAll(async () => {
    await miniProgram.close();
  });
});
```

### 3. 订单测试 (`specs/order.test.js`)

```javascript
describe('小程序下单流程', () => {
  let miniProgram;

  beforeAll(async () => {
    miniProgram = await automator.launch({
      projectPath: process.env.MINIPROGRAM_PATH,
    });

    // Mock wx.requestPayment 避免真实支付
    await miniProgram.mockWxMethod('requestPayment', {
      errMsg: 'requestPayment:ok'
    });

    // Mock 后端API
    await miniProgram.mockWxMethod('request', (args) => {
      if (args.url.includes('/api/order/create')) {
        return { data: { orderId: 'test_order_123', status: 'created' } };
      }
      if (args.url.includes('/api/order/pay')) {
        return { data: { status: 'paid', payTime: new Date().toISOString() } };
      }
    });
  });

  it('创建订单', async () => {
    // 跳转到商品详情
    await miniProgram.navigateTo('/pages/product/detail?id=test_product_1');
    await miniProgram.waitFor(1000);

    const page = await miniProgram.currentPage();

    // 点击立即购买
    const buyBtn = await page.$('.buy-now-btn');
    await buyBtn.tap();

    // 确认订单页
    await miniProgram.waitFor(1000);
    const orderPage = await miniProgram.currentPage();
    expect(orderPage.path).toBe('pages/order/confirm');

    // 提交订单
    const submitBtn = await orderPage.$('.submit-order-btn');
    await submitBtn.tap();

    await miniProgram.waitFor(2000);
    const resultPage = await miniProgram.currentPage();
    expect(resultPage.path).toBe('pages/order/result');
  });

  afterAll(async () => {
    await miniProgram.close();
  });
});
```

## Jest配置 (`jest.config.js`)

```javascript
module.exports = {
  testEnvironment: 'node',
  testMatch: ['**/specs/**/*.test.js'],
  testTimeout: 60000,
  verbose: true,
  reporters: [
    'default',
    ['jest-allure', { outputDir: 'reports/allure-results' }]
  ]
};
```

## CI集成说明

微信小程序自动化CI环境需要：
1. **专用构建机**：预装微信开发者工具（无Docker镜像）
2. **GUI环境**：开发者工具需要图形界面（Linux需Xvfb）
3. **启动方式**：`cli --auto --port 9420 --open /path/to/project`

```bash
# CI启动脚本示例
#!/bin/bash
# 启动虚拟显示（Linux CI环境）
export DISPLAY=:99
Xvfb :99 -screen 0 1024x768x16 &

# 启动微信开发者工具
"$WECHAT_DEVTOOL_PATH" auto --port 9420 --open ./miniprogram &
sleep 10

# 执行测试
npx jest tests/miniapp/specs/ --json

# 清理
kill %1
```
