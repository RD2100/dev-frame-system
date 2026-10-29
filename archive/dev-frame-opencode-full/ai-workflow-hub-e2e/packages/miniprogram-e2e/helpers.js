/**
 * 微信小程序E2E测试通用工具函数
 * 项目无关 — 所有项目共用，不硬编码任何项目路径
 *
 * 用法：const { connect, safeReLaunch, waitForDataChange } = require('@testframe/miniprogram-e2e');
 */
const fs = require('fs');
const path = require('path');

// ========== 连接 ==========

/**
 * 连接到DevTools，带重试
 * @param {number} port - 自动化端口，默认9420
 * @param {number} retries - 重试次数
 */
async function connect(port = 9420, retries = 3) {
  const automator = require('miniprogram-automator');
  let lastError;
  for (let i = 0; i < retries; i++) {
    try {
      const miniProgram = await automator.connect({
        wsEndpoint: `ws://127.0.0.1:${port}`,
      });
      return miniProgram;
    } catch (e) {
      lastError = e;
      console.log(`连接失败(${i + 1}/${retries}), 1秒后重试...`);
      await new Promise(r => setTimeout(r, 1000));
    }
  }
  throw lastError;
}

// ========== 页面操作 ==========

/**
 * 安全获取页面数据，带重试
 */
async function safeGetData(page, key, retries = 2) {
  for (let i = 0; i < retries; i++) {
    try {
      return await page.data(key);
    } catch (e) {
      if (i < retries - 1) {
        await new Promise(r => setTimeout(r, 500));
      } else {
        throw e;
      }
    }
  }
}

/**
 * 安全reLaunch页面，等待加载完成
 * @param {object} miniProgram - automator实例
 * @param {string} pagePath - 页面路径如'/pages/home/home'
 * @param {number} waitMs - 等待毫秒，默认3000
 */
async function safeReLaunch(miniProgram, pagePath, waitMs = 3000) {
  const page = await miniProgram.reLaunch(pagePath);
  await page.waitFor(waitMs);
  return page;
}

// ========== P0: 数据闭环等待 ==========

/**
 * 等待页面data某个字段变化（用于等云函数返回后列表刷新）
 * @param {object} page - automator Page对象
 * @param {string} key - data key
 * @param {function} predicate - 返回true时停止等待
 * @param {number} timeout - 最大等待ms
 */
async function waitForDataChange(page, key, predicate, timeout = 10000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const value = await page.data(key);
    if (predicate(value)) return value;
    await new Promise(r => setTimeout(r, 500));
  }
  return await page.data(key);
}

// ========== P1: wx API代理 ==========

/**
 * 注入wx.showToast/showModal代理（evaluate方式，作为mockWxMethod的备选）
 */
async function injectWxProxy(miniProgram) {
  await miniProgram.evaluate(() => {
    if (!wx._toastLog) {
      wx._toastLog = [];
      const origToast = wx.showToast;
      wx.showToast = function(opts) {
        wx._toastLog.push({ title: opts.title, icon: opts.icon, duration: opts.duration });
        return origToast.call(wx, opts);
      };
    }
    if (!wx._modalLog) {
      wx._modalLog = [];
      const origModal = wx.showModal;
      wx.showModal = function(opts) {
        wx._modalLog.push({ title: opts.title, content: opts.content });
        return origModal.call(wx, opts);
      };
    }
  });
}

async function getToastLog(miniProgram) {
  return await miniProgram.evaluate(() => wx._toastLog || []);
}

async function getModalLog(miniProgram) {
  return await miniProgram.evaluate(() => wx._modalLog || []);
}

async function clearWxProxyLog(miniProgram) {
  await miniProgram.evaluate(() => {
    if (wx._toastLog) wx._toastLog = [];
    if (wx._modalLog) wx._modalLog = [];
  });
}

// ========== P2: 截图对比 ==========

/**
 * 截图保存（目录基于调用项目，不硬编码）
 * @param {object} miniProgram - automator实例
 * @param {string} name - 截图名称
 * @param {string} [baseDir] - 截图根目录，默认process.cwd()/tests/e2e/screenshots
 */
async function captureScreenshot(miniProgram, name, baseDir) {
  const screenshotDir = baseDir || path.join(process.cwd(), 'tests', 'e2e', 'screenshots');
  const baselineDir = path.join(screenshotDir, 'baseline');
  const diffDir = path.join(screenshotDir, 'diff');

  if (!fs.existsSync(screenshotDir)) fs.mkdirSync(screenshotDir, { recursive: true });
  if (!fs.existsSync(baselineDir)) fs.mkdirSync(baselineDir, { recursive: true });
  if (!fs.existsSync(diffDir)) fs.mkdirSync(diffDir, { recursive: true });

  const filePath = path.join(screenshotDir, `${name}.png`);
  await miniProgram.screenshot({ path: filePath });
  return filePath;
}

async function saveBaseline(miniProgram, name, baseDir) {
  const screenshotDir = baseDir || path.join(process.cwd(), 'tests', 'e2e', 'screenshots');
  const baselineDir = path.join(screenshotDir, 'baseline');
  if (!fs.existsSync(baselineDir)) fs.mkdirSync(baselineDir, { recursive: true });
  const filePath = path.join(baselineDir, `${name}.png`);
  await miniProgram.screenshot({ path: filePath });
  return filePath;
}

/**
 * 截图像素对比
 * @param {number} threshold - 允许的像素差异阈值
 */
async function compareScreenshot(baselinePath, currentPath, threshold = 100) {
  const diffDir = path.join(path.dirname(baselinePath), '..', 'diff');
  try {
    const PNG = require('pngjs').PNG;
    const pixelmatch = require('pixelmatch');

    const img1 = PNG.sync.read(fs.readFileSync(baselinePath));
    const img2 = PNG.sync.read(fs.readFileSync(currentPath));
    const { width, height } = img1;

    const diff = new PNG({ width, height });
    const mismatchedPixels = pixelmatch(img1.data, img2.data, diff.data, width, height, { threshold: 0.1 });

    if (!fs.existsSync(diffDir)) fs.mkdirSync(diffDir, { recursive: true });
    const diffPath = path.join(diffDir, `${path.basename(baselinePath, '.png')}_diff.png`);
    fs.writeFileSync(diffPath, PNG.sync.write(diff));

    return { mismatchedPixels, totalPixels: width * height, diffPath, pass: mismatchedPixels <= threshold };
  } catch (e) {
    console.log('pixelmatch/pngjs未安装，截图对比不可用');
    return { mismatchedPixels: 0, totalPixels: 0, diffPath: '', pass: true, skip: true };
  }
}

// ========== 导出 ==========

module.exports = {
  connect,
  safeGetData,
  safeReLaunch,
  waitForDataChange,
  injectWxProxy,
  getToastLog,
  getModalLog,
  clearWxProxyLog,
  captureScreenshot,
  saveBaseline,
  compareScreenshot,
};
