/** FitTrack 小程序 E2E 测试 — 真实 IDE 连接 */
const automator = require('miniprogram-automator');

const CLI = 'D:/微信web开发者工具/cli.bat';
const PROJECT = 'D:/FitnessManagement';
const AUTO_PORT = 19520;

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  // Step 1: Enable auto mode on running IDE
  console.log('Enabling automation mode...');
  const { spawn } = require('child_process');
  await new Promise((resolve, reject) => {
    const c = spawn('cmd.exe', ['/c',
      `"${CLI}" auto --project "${PROJECT}" --auto-port ${AUTO_PORT} --trust-project`]);
    c.stderr.on('data', d => process.stderr.write(d));
    c.on('close', resolve);
    c.on('error', reject);
  });
  await sleep(5000);

  // Step 2: Connect
  console.log('Connecting...');
  const mp = await automator.connect({ wsEndpoint: `ws://127.0.0.1:${AUTO_PORT}` });
  console.log('Connected!\n');

  let passed = 0, total = 0;

  // Test 1: Current page
  total++; try {
    const page = await mp.currentPage();
    console.log(`[${total}] Page: ${page.path}`);
    passed++;
  } catch(e) { console.log(`[${total}] FAIL: ${e.message}`); }

  // Test 2: System info
  total++; try {
    const sys = await mp.systemInfo();
    console.log(`[${total}] Platform: ${sys.platform} | SDK: ${sys.SDKVersion} | Model: ${sys.model}`);
    passed++;
  } catch(e) { console.log(`[${total}] FAIL: ${e.message}`); }

  // Test 3: Page stack
  total++; try {
    const stack = await mp.pageStack();
    console.log(`[${total}] Stack: ${stack.map(p => p.path).join(' -> ')}`);
    passed++;
  } catch(e) { console.log(`[${total}] FAIL: ${e.message}`); }

  // Test 4-7: Tab navigation
  const tabs = [
    ['exercise', '/pages/exercise/exercise'],
    ['training', '/pages/training/training'],
    ['profile', '/pages/profile/profile'],
    ['index', '/pages/index/index'],
  ];
  for (const [name, path] of tabs) {
    total++; try {
      await mp.switchTab(path); await sleep(800);
      const p = await mp.currentPage();
      console.log(`[${total}] Tab ${name}: ${p.path}`);
      passed++;
    } catch(e) { console.log(`[${total}] FAIL ${name}: ${e.message}`); }
  }

  // Test 8: Page data on index
  total++; try {
    await mp.switchTab('/pages/index/index'); await sleep(1000);
    const p = await mp.currentPage();
    const data = await p.data();
    const keys = Object.keys(data || {}).join(', ') || '<empty>';
    console.log(`[${total}] Index data: ${keys}`);
    passed++;
  } catch(e) { console.log(`[${total}] FAIL: ${e.message}`); }

  // Test 9-10: Exercise page detail
  total++; try {
    await mp.switchTab('/pages/exercise/exercise'); await sleep(1500);
    const p = await mp.currentPage();
    const data = await p.data();
    console.log(`[${total}] Exercise data keys: ${Object.keys(data || {}).join(', ')}`);
    passed++;
  } catch(e) { console.log(`[${total}] FAIL: ${e.message}`); }

  total++; try {
    // Check for UI elements on exercise page
    const p = await mp.currentPage();
    const views = await p.$$('view, text, image');
    console.log(`[${total}] Exercise page elements: ${views.length}`);
    passed++;
  } catch(e) { console.log(`[${total}] FAIL: ${e.message}`); }

  // Screenshot
  total++; try {
    await mp.screenshot({ path: 'reports/fittrack/exercise_page.png' });
    console.log(`[${total}] Screenshot saved: reports/fittrack/exercise_page.png`);
    passed++;
  } catch(e) { console.log(`[${total}] FAIL: ${e.message}`); }

  await mp.close();
  console.log(`\n${'='.repeat(40)}`);
  console.log(`Result: ${passed}/${total} passed`);
  console.log(`${'='.repeat(40)}`);
}

main().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
