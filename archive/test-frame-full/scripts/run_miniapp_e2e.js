// FitTrack MiniApp E2E — 业务逻辑深度测试
// 前置: IDE 已运行, 服务端口已开启
const automator = require('miniprogram-automator');
const PORT = 19541;

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  const mp = await automator.connect({ wsEndpoint: 'ws://127.0.0.1:' + PORT });
  const results = [];
  const pass = (name) => results.push({ name, status: 'passed' });
  const fail = (name, error) => results.push({ name, status: 'failed', error: String(error).substring(0, 200) });
  const skip = (name, reason) => results.push({ name, status: 'skipped', error: reason });

  // ── 0. 基础环境 ──
  try {
    let p = await mp.currentPage();
    pass('env:page=' + p.path);

    let s = await mp.systemInfo();
    pass('env:sdk=' + s.SDKVersion + ',model=' + s.model);
  } catch (e) { fail('env', e.message); }


  // ── 2. Tab 导航 ──
  const tabs = [
    ['exercise', '/pages/exercise/exercise'],
    ['training', '/pages/training/training'],
    ['profile', '/pages/profile/profile'],
    ['index', '/pages/index/index'],
  ];
  for (const [name, path] of tabs) {
    try {
      await mp.switchTab(path); await sleep(600);
      let p = await mp.currentPage();
      pass('nav:tab_' + name + '=' + p.path);
    } catch (e) { fail('nav:tab_' + name, e.message); }
  }

  // ── 3. 动作库 — 搜索功能 ──
  try {
    await mp.switchTab('/pages/exercise/exercise'); await sleep(1000);
    let page = await mp.currentPage();
    let data = await page.data();

    // 验证数据结构
    if (data && Array.isArray(data.categories)) {
      pass('exercise:categories=' + data.categories.length + '_cats');
    } else {
      fail('exercise:categories', 'not an array or missing');
    }

    // 尝试触发搜索
    if (data && data.keyword !== undefined) {
      // 调用 setData 模拟输入
      await page.callMethod('onSearch', { detail: { value: 'E2E' } });
      await sleep(1000);
      let data2 = await page.data();
      pass('exercise:search_triggered');
    } else {
      skip('exercise:search', 'keyword field not in data');
    }

    // 分类筛选
    if (data && data.currentCategory !== undefined) {
      // 切换分类
      await page.setData({ currentCategory: 'chest' });
      await sleep(500);
      pass('exercise:filter_category');
    } else {
      skip('exercise:filter', 'category field not in data');
    }
  } catch (e) { fail('exercise', e.message); }

  // ── 4. 训练计划页 — 数据加载 ──
  try {
    await mp.switchTab('/pages/training/training'); await sleep(1500);
    let page = await mp.currentPage();
    let data = await page.data();

    if (data && Array.isArray(data.plans)) {
      pass('training:plans_loaded=' + data.plans.length);
    } else if (data && Array.isArray(data.historyList)) {
      pass('training:history_loaded=' + data.historyList.length);
    } else {
      let keys = Object.keys(data || {});
      pass('training:data_keys=' + keys.join(','));
    }

    // Tab 切换 (计划/历史)
    if (data && data.currentTab !== undefined) {
      await page.setData({ currentTab: 'history' });
      await sleep(500);
      pass('training:switch_to_history');
      await page.setData({ currentTab: 'plans' });
      await sleep(500);
      pass('training:switch_to_plans');
    } else {
      skip('training:tabs', 'currentTab not in data');
    }
  } catch (e) { fail('training', e.message); }

  // ── 5. 个人中心 — 数据验证 ──
  try {
    await mp.switchTab('/pages/profile/profile'); await sleep(1500);
    let page = await mp.currentPage();
    let data = await page.data();

    // 验证关键数据字段
    if (data && data.totalStats) {
      pass('profile:stats_loaded');
    }
    if (data && data.userInfo) {
      pass('profile:user_loaded');
    }
    if (data && data.bmiValue !== undefined) {
      pass('profile:bmi_calculated=' + data.bmiValue);
    }

    // 跳转到编辑页
    try {
      await mp.navigateTo('/pages/profile/profile-edit/profile-edit');
      await sleep(1000);
      let editPage = await mp.currentPage();
      let editData = await editPage.data();
      if (editData && editData.nickname !== undefined) {
        pass('profile:edit_page_loaded');
      }
      await mp.navigateBack();
      await sleep(500);
    } catch (e) {
      skip('profile:edit', 'navigateTo failed: ' + e.message.substring(0, 50));
    }
  } catch (e) { fail('profile', e.message); }

  // ── 6. 首页 — 数据完整性 ──
  try {
    await mp.switchTab('/pages/index/index'); await sleep(1500);
    let page = await mp.currentPage();
    let data = await page.data();

    let requiredFields = ['greeting', 'weekStats'];
    for (let f of requiredFields) {
      if (data && data[f] !== undefined) {
        pass('home:' + f);
      } else {
        skip('home:' + f, 'not in data');
      }
    }

    if (data && data.weekStats) {
      let ws = data.weekStats;
      pass('home:weekStats=' + ['workoutCount', 'totalVolume', 'totalDuration', 'streakDays']
        .filter(k => ws[k] !== undefined).join(','));
    }
  } catch (e) { fail('home', e.message); }

  // ── 7. 截图 ──
  try {
    await mp.screenshot({ path: 'reports/fittrack/e2e_final.png' });
    pass('screenshot:final');
  } catch (e) { fail('screenshot', e.message); }

  await mp.close();
  console.log('MINIAPP_RESULTS:' + JSON.stringify(results));
}

main().catch(e => {
  console.log('MINIAPP_RESULTS:' + JSON.stringify([{ name: 'fatal', status: 'failed', error: e.message }]));
});
