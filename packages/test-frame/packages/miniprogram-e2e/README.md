# @testframe/miniprogram-e2e

微信小程序E2E自动化测试通用框架。基于 miniprogram-automator + Jest。

## 快速接入（3步）

### Step 1: 安装依赖
```bash
cd <你的项目>
npm install --save-dev miniprogram-automator jest pixelmatch pngjs
```

### Step 2: 创建E2E目录和配置
```bash
mkdir -p tests/e2e/screenshots/baseline tests/e2e/screenshots/diff
```

复制以下文件到 `tests/e2e/`：
- `config.js` — 修改3行（端口、项目路径、miniprogramRoot）
- `jest.e2e.config.js` — 照搬，不改
- `helpers.js` — 照搬，不改
- `connection.e2e.js` — 照搬，不改

### Step 3: 扫描页面 → 写测试
```bash
# 扫描所有页面的WXML选择器和data字段
node scan.js <项目根目录>
# 报告输出到 tests/e2e/scan-report.json
```

根据扫描报告编写各页面的 `.e2e.js` 测试文件。

## 运行
```bash
# 启动DevTools（先跑这个）
"D:/微信web开发者工具/cli.bat" auto --project "D:/你的项目" --auto-port 9420

# 等待15-30秒

# 跑E2E测试
npx jest --config tests/e2e/jest.e2e.config.js --verbose
```

## 铁律（违反必踩坑）
1. **先读WXML再写选择器** — 不要猜class名
2. **每个test独立reLaunch** — 不共享page变量
3. **用connect()不用launch()** — 连接已打开的DevTools
4. **wx API拦截用mockWxMethod** — 不要用evaluate()注入代理
5. **云函数操作后等数据变化** — 用waitForDataChange，不要tap后立即断言
6. **Jest roots不能加子路径** — roots: ['<rootDir>']

## 4层测试体系
| 优先级 | 文件模式 | 核心技术 |
|--------|---------|---------|
| P0闭环 | 操作→waitForDataChange→断言 | 数据往返验证 |
| P1代理 | mockWxMethod捕获Toast/Modal | 原生弹窗断言 |
| P2截图 | captureScreenshot+compareScreenshot | 像素级视觉回归 |
| P3边界 | test.each()参数化 | DDT边界值覆盖 |
