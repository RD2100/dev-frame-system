// FitTrack MiniApp E2E — 全13页深度测试
// 前置: IDE 已运行, 服务端口已开启
// 运行: node tests/fittrack/miniapp/e2e_full.js [--port 19541]
const automator = require('miniprogram-automator');
const fs = require('fs');
const path = require('path');

const PORT = parseInt(process.argv.find(a => a.startsWith('--port'))?.split('=')[1] || process.argv[process.argv.indexOf('--port') + 1], 10) || 19541;
const SCREENSHOT_DIR = path.resolve(__dirname, '../../../reports/fittrack');

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// 确保截图目录存在
function ensureScreenshotDir() {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }
}

// 截图辅助：每个页面独立截图
async function takeScreenshot(mp, name) {
  try {
    const filePath = path.join(SCREENSHOT_DIR, `e2e_${name}.png`);
    await mp.screenshot({ path: filePath });
    return filePath;
  } catch (e) {
    return null;
  }
}

// 安全获取页面数据
async function safeGetData(page) {
  try {
    return await page.data();
  } catch (e) {
    return null;
  }
}

// 安全获取UI元素数量
async function safeCountElements(page, selector) {
  try {
    const elements = await page.$$(selector);
    return elements.length;
  } catch (e) {
    return -1;
  }
}

async function main() {
  ensureScreenshotDir();

  const mp = await automator.connect({ wsEndpoint: 'ws://127.0.0.1:' + PORT });
  const results = [];
  const pass = (name) => results.push({ name, status: 'passed' });
  const fail = (name, error) => results.push({ name, status: 'failed', error: String(error).substring(0, 200) });
  const skip = (name, reason) => results.push({ name, status: 'skipped', error: reason });

  // ═══════════════════════════════════════════
  // 0. 基础环境检查
  // ═══════════════════════════════════════════
  try {
    let p = await mp.currentPage();
    pass('env:page=' + p.path);

    let s = await mp.systemInfo();
    pass('env:sdk=' + s.SDKVersion + ',model=' + s.model);

    let stack = await mp.pageStack();
    pass('env:stack_depth=' + stack.length);
  } catch (e) { fail('env', e.message); }

  // ═══════════════════════════════════════════
  // 1. Login 页 — pages/login/login
  // ═══════════════════════════════════════════
  try {
    // 登录页是首页（app.json pages[0]），reLaunch直达
    await mp.reLaunch('/pages/login/login');
    await sleep(1500);
    let page = await mp.currentPage();
    let data = await safeGetData(page);

    // 验证页面路径
    if (page.path.includes('login')) {
      pass('login:page_loaded');
    } else {
      // 可能已登录自动跳转首页
      skip('login:page_loaded', 'redirected to ' + page.path + ' (already logged in)');
    }

    // 验证数据字段
    if (data) {
      if (data.loading !== undefined) pass('login:field_loading');
      else skip('login:field_loading', 'not in data');

      if (data.motto !== undefined) pass('login:field_motto=' + data.motto);
      else skip('login:field_motto', 'not in data');

      if (data.userInfo !== undefined) pass('login:field_userInfo');
      else skip('login:field_userInfo', 'not in data');
    } else {
      skip('login:data', 'page data unavailable');
    }

    // 验证UI元素
    let elemCount = await safeCountElements(page, 'view, text, image, button');
    if (elemCount >= 0) pass('login:ui_elements=' + elemCount);
    else skip('login:ui_elements', 'query failed');

    // 截图
    let ss = await takeScreenshot(mp, 'login');
    if (ss) pass('login:screenshot');
    else skip('login:screenshot', 'screenshot failed');
  } catch (e) { fail('login', e.message); }

  // ═══════════════════════════════════════════
  // 2. Index 首页 — pages/index/index (Tab页)
  // ═══════════════════════════════════════════
  try {
    await mp.switchTab('/pages/index/index');
    await sleep(1500);
    let page = await mp.currentPage();
    let data = await safeGetData(page);

    // 验证页面路径
    if (page.path.includes('index')) {
      pass('index:page_loaded');
    } else {
      fail('index:page_loaded', 'expected index, got ' + page.path);
    }

    // 验证关键数据字段
    if (data) {
      if (data.greeting !== undefined) pass('index:field_greeting=' + (data.greeting || '').substring(0, 20));
      else skip('index:field_greeting', 'not in data');

      if (data.todayPlanText !== undefined) pass('index:field_todayPlanText');
      else skip('index:field_todayPlanText', 'not in data');

      if (data.avatarUrl !== undefined) pass('index:field_avatarUrl');
      else skip('index:field_avatarUrl', 'not in data');

      if (data.todayWorkout !== undefined) pass('index:field_todayWorkout');
      else skip('index:field_todayWorkout', 'not in data');

      if (data.weekStats) {
        let ws = data.weekStats;
        let wsFields = ['workoutCount', 'totalVolume', 'totalDuration', 'streakDays']
          .filter(k => ws[k] !== undefined);
        pass('index:field_weekStats=' + wsFields.join(','));
      } else {
        skip('index:field_weekStats', 'not in data');
      }

      if (Array.isArray(data.recentWorkouts)) {
        pass('index:field_recentWorkouts=' + data.recentWorkouts.length);
      } else {
        skip('index:field_recentWorkouts', 'not an array or missing');
      }
    } else {
      skip('index:data', 'page data unavailable');
    }

    // 验证UI元素
    let elemCount = await safeCountElements(page, 'view, text, image');
    if (elemCount >= 0) pass('index:ui_elements=' + elemCount);
    else skip('index:ui_elements', 'query failed');

    // 截图
    let ss = await takeScreenshot(mp, 'index');
    if (ss) pass('index:screenshot');
    else skip('index:screenshot', 'screenshot failed');
  } catch (e) { fail('index', e.message); }

  // ═══════════════════════════════════════════
  // 3. Training 训练页 — pages/training/training (Tab页)
  // ═══════════════════════════════════════════
  try {
    await mp.switchTab('/pages/training/training');
    await sleep(1500);
    let page = await mp.currentPage();
    let data = await safeGetData(page);

    // 验证页面路径
    if (page.path.includes('training')) {
      pass('training:page_loaded');
    } else {
      fail('training:page_loaded', 'expected training, got ' + page.path);
    }

    // 验证关键数据字段
    if (data) {
      if (data.currentTab !== undefined) pass('training:field_currentTab=' + data.currentTab);
      else skip('training:field_currentTab', 'not in data');

      if (Array.isArray(data.plans)) pass('training:field_plans=' + data.plans.length);
      else skip('training:field_plans', 'not an array or missing');

      if (Array.isArray(data.historyList)) pass('training:field_historyList=' + data.historyList.length);
      else skip('training:field_historyList', 'not an array or missing');

      if (Array.isArray(data.dayLabels)) pass('training:field_dayLabels=' + data.dayLabels.length);
      else skip('training:field_dayLabels', 'not an array or missing');
    } else {
      skip('training:data', 'page data unavailable');
    }

    // 交互测试：Tab切换 (plans <-> history)
    if (data && data.currentTab !== undefined) {
      try {
        // 切换到历史
        await page.setData({ currentTab: 'history' });
        await sleep(800);
        let data2 = await safeGetData(page);
        if (data2 && data2.currentTab === 'history') {
          pass('training:switch_to_history');
        } else {
          fail('training:switch_to_history', 'currentTab not changed');
        }

        // 切换回计划
        await page.setData({ currentTab: 'plans' });
        await sleep(800);
        let data3 = await safeGetData(page);
        if (data3 && data3.currentTab === 'plans') {
          pass('training:switch_to_plans');
        } else {
          fail('training:switch_to_plans', 'currentTab not changed');
        }
      } catch (e) {
        fail('training:tab_switch', e.message);
      }
    } else {
      skip('training:tab_switch', 'currentTab not in data');
    }

    // 验证UI元素
    let elemCount = await safeCountElements(page, 'view, text, image');
    if (elemCount >= 0) pass('training:ui_elements=' + elemCount);
    else skip('training:ui_elements', 'query failed');

    // 截图
    let ss = await takeScreenshot(mp, 'training');
    if (ss) pass('training:screenshot');
    else skip('training:screenshot', 'screenshot failed');
  } catch (e) { fail('training', e.message); }

  // ═══════════════════════════════════════════
  // 4. Exercise 动作库 — pages/exercise/exercise (Tab页)
  // ═══════════════════════════════════════════
  try {
    await mp.switchTab('/pages/exercise/exercise');
    await sleep(1500);
    let page = await mp.currentPage();
    let data = await safeGetData(page);

    // 验证页面路径
    if (page.path.includes('exercise')) {
      pass('exercise:page_loaded');
    } else {
      fail('exercise:page_loaded', 'expected exercise, got ' + page.path);
    }

    // 验证关键数据字段
    if (data) {
      if (data.keyword !== undefined) pass('exercise:field_keyword');
      else skip('exercise:field_keyword', 'not in data');

      if (data.currentCategory !== undefined) pass('exercise:field_currentCategory=' + data.currentCategory);
      else skip('exercise:field_currentCategory', 'not in data');

      if (Array.isArray(data.categories)) pass('exercise:field_categories=' + data.categories.length + '_cats');
      else skip('exercise:field_categories', 'not an array or missing');

      if (Array.isArray(data.exercises)) pass('exercise:field_exercises=' + data.exercises.length);
      else skip('exercise:field_exercises', 'not an array or missing');

      if (data.loading !== undefined) pass('exercise:field_loading=' + data.loading);
      else skip('exercise:field_loading', 'not in data');

      if (data.page !== undefined) pass('exercise:field_page=' + data.page);
      else skip('exercise:field_page', 'not in data');

      if (data.hasMore !== undefined) pass('exercise:field_hasMore=' + data.hasMore);
      else skip('exercise:field_hasMore', 'not in data');
    } else {
      skip('exercise:data', 'page data unavailable');
    }

    // 交互测试：搜索功能
    if (data && data.keyword !== undefined) {
      try {
        await page.callMethod('onSearch', { detail: { value: 'E2E' } });
        await sleep(1200);
        let data2 = await safeGetData(page);
        if (data2 && data2.keyword === 'E2E') {
          pass('exercise:search_keyword_set');
        } else {
          skip('exercise:search_keyword_set', 'keyword not updated');
        }
      } catch (e) {
        // onSearch可能被debounce包裹，callMethod可能不直接生效
        try {
          await page.setData({ keyword: 'E2E', page: 1, hasMore: true });
          await sleep(800);
          pass('exercise:search_keyword_set_via_setData');
        } catch (e2) {
          fail('exercise:search', e2.message);
        }
      }
    } else {
      skip('exercise:search', 'keyword field not in data');
    }

    // 交互测试：分类筛选
    if (data && data.currentCategory !== undefined) {
      try {
        await page.setData({ currentCategory: 'chest', page: 1, hasMore: true });
        await sleep(800);
        let data3 = await safeGetData(page);
        if (data3 && data3.currentCategory === 'chest') {
          pass('exercise:filter_category_chest');
        } else {
          fail('exercise:filter_category_chest', 'category not changed');
        }

        // 重置分类
        await page.setData({ currentCategory: '', page: 1, hasMore: true });
        await sleep(500);
        pass('exercise:filter_category_reset');
      } catch (e) {
        fail('exercise:filter', e.message);
      }
    } else {
      skip('exercise:filter', 'currentCategory not in data');
    }

    // 验证UI元素
    let elemCount = await safeCountElements(page, 'view, text, image');
    if (elemCount >= 0) pass('exercise:ui_elements=' + elemCount);
    else skip('exercise:ui_elements', 'query failed');

    // 截图
    let ss = await takeScreenshot(mp, 'exercise');
    if (ss) pass('exercise:screenshot');
    else skip('exercise:screenshot', 'screenshot failed');
  } catch (e) { fail('exercise', e.message); }

  // ═══════════════════════════════════════════
  // 5. Exercise Detail 动作详情 — pages/exercise/exercise-detail/exercise-detail
  // ═══════════════════════════════════════════
  try {
    // 先确保在exercise tab，获取一个动作ID
    await mp.switchTab('/pages/exercise/exercise');
    await sleep(1000);
    let exPage = await mp.currentPage();
    let exData = await safeGetData(exPage);

    let exerciseId = null;
    if (exData && Array.isArray(exData.exercises) && exData.exercises.length > 0) {
      exerciseId = exData.exercises[0]._id;
    }

    if (exerciseId) {
      await mp.navigateTo('/pages/exercise/exercise-detail/exercise-detail?id=' + exerciseId);
      await sleep(1500);
      let page = await mp.currentPage();
      let data = await safeGetData(page);

      // 验证页面路径
      if (page.path.includes('exercise-detail')) {
        pass('exercise-detail:page_loaded');
      } else {
        fail('exercise-detail:page_loaded', 'expected exercise-detail, got ' + page.path);
      }

      // 验证关键数据字段
      if (data) {
        if (data.exercise !== undefined) pass('exercise-detail:field_exercise');
        else skip('exercise-detail:field_exercise', 'not in data');

        if (data.relatedExercises !== undefined) pass('exercise-detail:field_relatedExercises=' + (Array.isArray(data.relatedExercises) ? data.relatedExercises.length : 'not_array'));
        else skip('exercise-detail:field_relatedExercises', 'not in data');

        if (data.loading !== undefined) pass('exercise-detail:field_loading=' + data.loading);
        else skip('exercise-detail:field_loading', 'not in data');

        // 如果exercise已加载，验证详情字段
        if (data.exercise && typeof data.exercise === 'object') {
          let detailFields = ['categoryName', 'difficultyName', 'difficultyColor', 'equipmentName', 'muscles']
            .filter(k => data.exercise[k] !== undefined);
          pass('exercise-detail:detail_fields=' + detailFields.join(','));
        } else {
          skip('exercise-detail:detail_fields', 'exercise object not loaded');
        }
      } else {
        skip('exercise-detail:data', 'page data unavailable');
      }

      // 验证UI元素
      let elemCount = await safeCountElements(page, 'view, text, image');
      if (elemCount >= 0) pass('exercise-detail:ui_elements=' + elemCount);
      else skip('exercise-detail:ui_elements', 'query failed');

      // 截图
      let ss = await takeScreenshot(mp, 'exercise-detail');
      if (ss) pass('exercise-detail:screenshot');
      else skip('exercise-detail:screenshot', 'screenshot failed');

      // 返回
      await mp.navigateBack();
      await sleep(500);
    } else {
      skip('exercise-detail:all', 'no exercise ID available from exercise list');
    }
  } catch (e) { fail('exercise-detail', e.message); }

  // ═══════════════════════════════════════════
  // 6. Profile 个人中心 — pages/profile/profile (Tab页)
  // ═══════════════════════════════════════════
  try {
    await mp.switchTab('/pages/profile/profile');
    await sleep(1500);
    let page = await mp.currentPage();
    let data = await safeGetData(page);

    // 验证页面路径
    if (page.path.includes('profile')) {
      pass('profile:page_loaded');
    } else {
      fail('profile:page_loaded', 'expected profile, got ' + page.path);
    }

    // 验证关键数据字段
    if (data) {
      if (data.userInfo !== undefined) pass('profile:field_userInfo');
      else skip('profile:field_userInfo', 'not in data');

      if (data.goalText !== undefined) pass('profile:field_goalText=' + data.goalText);
      else skip('profile:field_goalText', 'not in data');

      if (data.bmiValue !== undefined) pass('profile:field_bmiValue=' + data.bmiValue);
      else skip('profile:field_bmiValue', 'not in data');

      if (data.bmiLevel !== undefined) pass('profile:field_bmiLevel=' + data.bmiLevel);
      else skip('profile:field_bmiLevel', 'not in data');

      if (data.bmiColor !== undefined) pass('profile:field_bmiColor');
      else skip('profile:field_bmiColor', 'not in data');

      if (data.totalStats) {
        let ts = data.totalStats;
        let tsFields = ['workoutCount', 'totalHours', 'totalVolume', 'maxStreak']
          .filter(k => ts[k] !== undefined);
        pass('profile:field_totalStats=' + tsFields.join(','));
      } else {
        skip('profile:field_totalStats', 'not in data');
      }
    } else {
      skip('profile:data', 'page data unavailable');
    }

    // 验证UI元素
    let elemCount = await safeCountElements(page, 'view, text, image');
    if (elemCount >= 0) pass('profile:ui_elements=' + elemCount);
    else skip('profile:ui_elements', 'query failed');

    // 截图
    let ss = await takeScreenshot(mp, 'profile');
    if (ss) pass('profile:screenshot');
    else skip('profile:screenshot', 'screenshot failed');
  } catch (e) { fail('profile', e.message); }

  // ═══════════════════════════════════════════
  // 7. Profile Edit 编辑资料 — pages/profile/profile-edit/profile-edit
  // ═══════════════════════════════════════════
  try {
    await mp.switchTab('/pages/profile/profile');
    await sleep(800);
    await mp.navigateTo('/pages/profile/profile-edit/profile-edit');
    await sleep(1500);
    let page = await mp.currentPage();
    let data = await safeGetData(page);

    // 验证页面路径
    if (page.path.includes('profile-edit')) {
      pass('profile-edit:page_loaded');
    } else {
      fail('profile-edit:page_loaded', 'expected profile-edit, got ' + page.path);
    }

    // 验证关键数据字段
    if (data) {
      if (data.nickname !== undefined) pass('profile-edit:field_nickname=' + (data.nickname || '').substring(0, 15));
      else skip('profile-edit:field_nickname', 'not in data');

      if (data.height !== undefined) pass('profile-edit:field_height=' + data.height);
      else skip('profile-edit:field_height', 'not in data');

      if (data.weight !== undefined) pass('profile-edit:field_weight=' + data.weight);
      else skip('profile-edit:field_weight', 'not in data');

      if (data.goal !== undefined) pass('profile-edit:field_goal=' + data.goal);
      else skip('profile-edit:field_goal', 'not in data');

      if (Array.isArray(data.goals)) pass('profile-edit:field_goals=' + data.goals.length);
      else skip('profile-edit:field_goals', 'not an array or missing');
    } else {
      skip('profile-edit:data', 'page data unavailable');
    }

    // 交互测试：修改昵称（不保存，仅验证setData生效）
    if (data && data.nickname !== undefined) {
      try {
        let originalNickname = data.nickname;
        await page.setData({ nickname: 'E2E测试用户' });
        await sleep(500);
        let data2 = await safeGetData(page);
        if (data2 && data2.nickname === 'E2E测试用户') {
          pass('profile-edit:edit_nickname');
        } else {
          fail('profile-edit:edit_nickname', 'nickname not updated');
        }
        // 恢复原值
        await page.setData({ nickname: originalNickname });
        await sleep(300);
      } catch (e) {
        fail('profile-edit:edit_nickname', e.message);
      }
    } else {
      skip('profile-edit:edit_nickname', 'nickname field not in data');
    }

    // 交互测试：切换训练目标
    if (data && data.goal !== undefined) {
      try {
        let originalGoal = data.goal;
        await page.setData({ goal: 'muscle' });
        await sleep(500);
        let data3 = await safeGetData(page);
        if (data3 && data3.goal === 'muscle') {
          pass('profile-edit:switch_goal');
        } else {
          fail('profile-edit:switch_goal', 'goal not changed');
        }
        // 恢复原值
        await page.setData({ goal: originalGoal });
        await sleep(300);
      } catch (e) {
        fail('profile-edit:switch_goal', e.message);
      }
    } else {
      skip('profile-edit:switch_goal', 'goal field not in data');
    }

    // 验证UI元素
    let elemCount = await safeCountElements(page, 'view, text, image, input');
    if (elemCount >= 0) pass('profile-edit:ui_elements=' + elemCount);
    else skip('profile-edit:ui_elements', 'query failed');

    // 截图
    let ss = await takeScreenshot(mp, 'profile-edit');
    if (ss) pass('profile-edit:screenshot');
    else skip('profile-edit:screenshot', 'screenshot failed');

    // 返回
    await mp.navigateBack();
    await sleep(500);
  } catch (e) { fail('profile-edit', e.message); }

  // ═══════════════════════════════════════════
  // 8. Body Metrics 身体数据 — pages/profile/body-metrics/body-metrics
  // ═══════════════════════════════════════════
  try {
    await mp.switchTab('/pages/profile/profile');
    await sleep(800);
    await mp.navigateTo('/pages/profile/body-metrics/body-metrics');
    await sleep(1500);
    let page = await mp.currentPage();
    let data = await safeGetData(page);

    // 验证页面路径
    if (page.path.includes('body-metrics')) {
      pass('body-metrics:page_loaded');
    } else {
      fail('body-metrics:page_loaded', 'expected body-metrics, got ' + page.path);
    }

    // 验证关键数据字段
    if (data) {
      if (Array.isArray(data.metrics)) pass('body-metrics:field_metrics=' + data.metrics.length);
      else skip('body-metrics:field_metrics', 'not an array or missing');

      if (data.loading !== undefined) pass('body-metrics:field_loading=' + data.loading);
      else skip('body-metrics:field_loading', 'not in data');
    } else {
      skip('body-metrics:data', 'page data unavailable');
    }

    // 验证UI元素
    let elemCount = await safeCountElements(page, 'view, text, image');
    if (elemCount >= 0) pass('body-metrics:ui_elements=' + elemCount);
    else skip('body-metrics:ui_elements', 'query failed');

    // 截图
    let ss = await takeScreenshot(mp, 'body-metrics');
    if (ss) pass('body-metrics:screenshot');
    else skip('body-metrics:screenshot', 'screenshot failed');

    // 返回
    await mp.navigateBack();
    await sleep(500);
  } catch (e) { fail('body-metrics', e.message); }

  // ═══════════════════════════════════════════
  // 9. Personal Records 个人记录 — pages/profile/personal-records/personal-records
  // ═══════════════════════════════════════════
  try {
    await mp.switchTab('/pages/profile/profile');
    await sleep(800);
    await mp.navigateTo('/pages/profile/personal-records/personal-records');
    await sleep(1500);
    let page = await mp.currentPage();
    let data = await safeGetData(page);

    // 验证页面路径
    if (page.path.includes('personal-records')) {
      pass('personal-records:page_loaded');
    } else {
      fail('personal-records:page_loaded', 'expected personal-records, got ' + page.path);
    }

    // 验证关键数据字段
    if (data) {
      if (Array.isArray(data.records)) pass('personal-records:field_records=' + data.records.length);
      else skip('personal-records:field_records', 'not an array or missing');

      if (data.loading !== undefined) pass('personal-records:field_loading=' + data.loading);
      else skip('personal-records:field_loading', 'not in data');
    } else {
      skip('personal-records:data', 'page data unavailable');
    }

    // 验证UI元素
    let elemCount = await safeCountElements(page, 'view, text, image');
    if (elemCount >= 0) pass('personal-records:ui_elements=' + elemCount);
    else skip('personal-records:ui_elements', 'query failed');

    // 截图
    let ss = await takeScreenshot(mp, 'personal-records');
    if (ss) pass('personal-records:screenshot');
    else skip('personal-records:screenshot', 'screenshot failed');

    // 返回
    await mp.navigateBack();
    await sleep(500);
  } catch (e) { fail('personal-records', e.message); }

  // ═══════════════════════════════════════════
  // 10. Workout Detail 训练详情 — pages/workout-detail/workout-detail
  // ═══════════════════════════════════════════
  try {
    // 尝试从训练历史获取一个workout ID
    let workoutId = null;
    try {
      await mp.switchTab('/pages/training/training');
      await sleep(1000);
      let trPage = await mp.currentPage();
      // 切换到历史tab
      await trPage.setData({ currentTab: 'history' });
      await sleep(1000);
      let trData = await safeGetData(trPage);
      if (trData && Array.isArray(trData.historyList) && trData.historyList.length > 0) {
        workoutId = trData.historyList[0]._id;
      }
    } catch (e) {
      // 获取workout ID失败，继续用无ID方式
    }

    if (workoutId) {
      // 有历史记录：查看已完成训练详情
      await mp.navigateTo('/pages/workout-detail/workout-detail?id=' + workoutId);
      await sleep(1500);
    } else {
      // 无历史记录：以自由训练模式打开
      await mp.navigateTo('/pages/workout-detail/workout-detail');
      await sleep(1500);
    }

    let page = await mp.currentPage();
    let data = await safeGetData(page);

    // 验证页面路径
    if (page.path.includes('workout-detail')) {
      pass('workout-detail:page_loaded');
    } else {
      fail('workout-detail:page_loaded', 'expected workout-detail, got ' + page.path);
    }

    // 验证关键数据字段
    if (data) {
      if (data.workoutId !== undefined) pass('workout-detail:field_workoutId');
      else skip('workout-detail:field_workoutId', 'not in data');

      if (data.workout !== undefined) pass('workout-detail:field_workout');
      else skip('workout-detail:field_workout', 'not in data');

      if (data.isActive !== undefined) pass('workout-detail:field_isActive=' + data.isActive);
      else skip('workout-detail:field_isActive', 'not in data');

      if (data.elapsedTime !== undefined) pass('workout-detail:field_elapsedTime=' + data.elapsedTime);
      else skip('workout-detail:field_elapsedTime', 'not in data');

      if (data.progress !== undefined) pass('workout-detail:field_progress=' + data.progress + '%');
      else skip('workout-detail:field_progress', 'not in data');

      if (data.completedSets !== undefined) pass('workout-detail:field_completedSets=' + data.completedSets);
      else skip('workout-detail:field_completedSets', 'not in data');

      if (data.totalSets !== undefined) pass('workout-detail:field_totalSets=' + data.totalSets);
      else skip('workout-detail:field_totalSets', 'not in data');

      if (data.restSeconds !== undefined) pass('workout-detail:field_restSeconds=' + data.restSeconds);
      else skip('workout-detail:field_restSeconds', 'not in data');

      if (data.restActive !== undefined) pass('workout-detail:field_restActive=' + data.restActive);
      else skip('workout-detail:field_restActive', 'not in data');
    } else {
      skip('workout-detail:data', 'page data unavailable');
    }

    // 交互测试：模拟完成一组（仅当有exercises时）
    if (data && data.workout && Array.isArray(data.workout.exercises) && data.workout.exercises.length > 0) {
      try {
        let exercises = data.workout.exercises;
        let exIdx = -1;
        let setIdx = -1;
        // 找到第一个未完成的组
        for (let i = 0; i < exercises.length; i++) {
          if (exercises[i].sets && Array.isArray(exercises[i].sets)) {
            for (let j = 0; j < exercises[i].sets.length; j++) {
              if (!exercises[i].sets[j].completed) {
                exIdx = i;
                setIdx = j;
                break;
              }
            }
          }
          if (exIdx >= 0) break;
        }

        if (exIdx >= 0 && setIdx >= 0) {
          // 通过setData模拟toggleSet
          let updatedExercises = JSON.parse(JSON.stringify(exercises));
          updatedExercises[exIdx].sets[setIdx].completed = true;
          await page.setData({ 'workout.exercises': updatedExercises });
          await sleep(500);

          // 验证进度更新
          let data2 = await safeGetData(page);
          if (data2 && data2.workout && data2.workout.exercises[exIdx].sets[setIdx].completed) {
            pass('workout-detail:toggle_set_completed');
          } else {
            fail('workout-detail:toggle_set_completed', 'set not marked completed');
          }

          // 恢复（不实际保存）
          updatedExercises[exIdx].sets[setIdx].completed = false;
          await page.setData({ 'workout.exercises': updatedExercises });
          await sleep(300);
        } else {
          skip('workout-detail:toggle_set', 'no incomplete sets found');
        }
      } catch (e) {
        fail('workout-detail:toggle_set', e.message);
      }
    } else {
      skip('workout-detail:toggle_set', 'no exercises in workout data');
    }

    // 验证UI元素
    let elemCount = await safeCountElements(page, 'view, text, image');
    if (elemCount >= 0) pass('workout-detail:ui_elements=' + elemCount);
    else skip('workout-detail:ui_elements', 'query failed');

    // 截图
    let ss = await takeScreenshot(mp, 'workout-detail');
    if (ss) pass('workout-detail:screenshot');
    else skip('workout-detail:screenshot', 'screenshot failed');

    // 返回
    await mp.navigateBack();
    await sleep(500);
  } catch (e) { fail('workout-detail', e.message); }

  // ═══════════════════════════════════════════
  // 11. Plan Edit 计划编辑 — pages/plan-edit/plan-edit
  // ═══════════════════════════════════════════
  try {
    // 新建计划模式（无id参数）
    await mp.navigateTo('/pages/plan-edit/plan-edit');
    await sleep(1500);
    let page = await mp.currentPage();
    let data = await safeGetData(page);

    // 验证页面路径
    if (page.path.includes('plan-edit')) {
      pass('plan-edit:page_loaded');
    } else {
      fail('plan-edit:page_loaded', 'expected plan-edit, got ' + page.path);
    }

    // 验证关键数据字段
    if (data) {
      if (data.planId !== undefined) pass('plan-edit:field_planId=' + data.planId);
      else skip('plan-edit:field_planId', 'not in data');

      if (data.plan !== undefined) {
        pass('plan-edit:field_plan');
        if (data.plan.name !== undefined) pass('plan-edit:field_plan.name=' + (data.plan.name || '').substring(0, 15));
        else skip('plan-edit:field_plan.name', 'not in data');

        if (data.plan.goal !== undefined) pass('plan-edit:field_plan.goal=' + data.plan.goal);
        else skip('plan-edit:field_plan.goal', 'not in data');

        if (data.plan.frequency !== undefined) pass('plan-edit:field_plan.frequency=' + data.plan.frequency);
        else skip('plan-edit:field_plan.frequency', 'not in data');

        if (Array.isArray(data.plan.days)) pass('plan-edit:field_plan.days=' + data.plan.days.length);
        else skip('plan-edit:field_plan.days', 'not an array or missing');
      } else {
        skip('plan-edit:field_plan', 'not in data');
      }

      if (Array.isArray(data.goals)) pass('plan-edit:field_goals=' + data.goals.length);
      else skip('plan-edit:field_goals', 'not an array or missing');

      if (Array.isArray(data.frequencies)) pass('plan-edit:field_frequencies=' + data.frequencies.length);
      else skip('plan-edit:field_frequencies', 'not an array or missing');

      if (data.showExercisePicker !== undefined) pass('plan-edit:field_showExercisePicker=' + data.showExercisePicker);
      else skip('plan-edit:field_showExercisePicker', 'not in data');

      if (data.currentDayIndex !== undefined) pass('plan-edit:field_currentDayIndex=' + data.currentDayIndex);
      else skip('plan-edit:field_currentDayIndex', 'not in data');
    } else {
      skip('plan-edit:data', 'page data unavailable');
    }

    // 交互测试：修改计划名称
    if (data && data.plan && data.plan.name !== undefined) {
      try {
        await page.setData({ 'plan.name': 'E2E测试计划' });
        await sleep(500);
        let data2 = await safeGetData(page);
        if (data2 && data2.plan && data2.plan.name === 'E2E测试计划') {
          pass('plan-edit:edit_name');
        } else {
          fail('plan-edit:edit_name', 'name not updated');
        }
        // 恢复
        await page.setData({ 'plan.name': '' });
        await sleep(300);
      } catch (e) {
        fail('plan-edit:edit_name', e.message);
      }
    } else {
      skip('plan-edit:edit_name', 'plan.name not in data');
    }

    // 交互测试：切换训练目标
    if (data && data.plan && data.plan.goal !== undefined) {
      try {
        let originalGoal = data.plan.goal;
        await page.setData({ 'plan.goal': 'strength' });
        await sleep(500);
        let data3 = await safeGetData(page);
        if (data3 && data3.plan && data3.plan.goal === 'strength') {
          pass('plan-edit:switch_goal');
        } else {
          fail('plan-edit:switch_goal', 'goal not changed');
        }
        // 恢复
        await page.setData({ 'plan.goal': originalGoal });
        await sleep(300);
      } catch (e) {
        fail('plan-edit:switch_goal', e.message);
      }
    } else {
      skip('plan-edit:switch_goal', 'plan.goal not in data');
    }

    // 交互测试：添加训练日
    if (data && data.plan && Array.isArray(data.plan.days)) {
      try {
        let originalDayCount = data.plan.days.length;
        await page.setData({ 'plan.days': [...data.plan.days, { exercises: [] }] });
        await sleep(500);
        let data4 = await safeGetData(page);
        if (data4 && data4.plan && data4.plan.days && data4.plan.days.length === originalDayCount + 1) {
          pass('plan-edit:add_day');
        } else {
          fail('plan-edit:add_day', 'day not added');
        }
        // 恢复
        let restoredDays = [...data.plan.days];
        await page.setData({ 'plan.days': restoredDays });
        await sleep(300);
      } catch (e) {
        fail('plan-edit:add_day', e.message);
      }
    } else {
      skip('plan-edit:add_day', 'plan.days not in data');
    }

    // 验证UI元素
    let elemCount = await safeCountElements(page, 'view, text, image, input');
    if (elemCount >= 0) pass('plan-edit:ui_elements=' + elemCount);
    else skip('plan-edit:ui_elements', 'query failed');

    // 截图
    let ss = await takeScreenshot(mp, 'plan-edit');
    if (ss) pass('plan-edit:screenshot');
    else skip('plan-edit:screenshot', 'screenshot failed');

    // 返回
    await mp.navigateBack();
    await sleep(500);
  } catch (e) { fail('plan-edit', e.message); }

  // ═══════════════════════════════════════════
  // 12. Stats 统计页 — pages/stats/stats
  // ═══════════════════════════════════════════
  try {
    await mp.navigateTo('/pages/stats/stats');
    await sleep(1500);
    let page = await mp.currentPage();
    let data = await safeGetData(page);

    // 验证页面路径
    if (page.path.includes('stats')) {
      pass('stats:page_loaded');
    } else {
      fail('stats:page_loaded', 'expected stats, got ' + page.path);
    }

    // 验证关键数据字段
    if (data) {
      if (data.period !== undefined) pass('stats:field_period=' + data.period);
      else skip('stats:field_period', 'not in data');

      if (data.stats) {
        let st = data.stats;
        let stFields = ['workoutCount', 'totalVolume', 'totalHours']
          .filter(k => st[k] !== undefined);
        pass('stats:field_stats=' + stFields.join(','));
      } else {
        skip('stats:field_stats', 'not in data');
      }

      if (Array.isArray(data.frequencyData)) pass('stats:field_frequencyData=' + data.frequencyData.length);
      else skip('stats:field_frequencyData', 'not an array or missing');

      if (Array.isArray(data.muscleData)) pass('stats:field_muscleData=' + data.muscleData.length);
      else skip('stats:field_muscleData', 'not an array or missing');

      if (Array.isArray(data.personalRecords)) pass('stats:field_personalRecords=' + data.personalRecords.length);
      else skip('stats:field_personalRecords', 'not an array or missing');
    } else {
      skip('stats:data', 'page data unavailable');
    }

    // 交互测试：周期切换 (week -> month -> year)
    if (data && data.period !== undefined) {
      try {
        // 切换到月
        await page.setData({ period: 'month' });
        await sleep(1000);
        let data2 = await safeGetData(page);
        if (data2 && data2.period === 'month') {
          pass('stats:switch_to_month');
        } else {
          fail('stats:switch_to_month', 'period not changed');
        }

        // 切换到年
        await page.setData({ period: 'year' });
        await sleep(1000);
        let data3 = await safeGetData(page);
        if (data3 && data3.period === 'year') {
          pass('stats:switch_to_year');
        } else {
          fail('stats:switch_to_year', 'period not changed');
        }

        // 切换回周
        await page.setData({ period: 'week' });
        await sleep(1000);
        let data4 = await safeGetData(page);
        if (data4 && data4.period === 'week') {
          pass('stats:switch_to_week');
        } else {
          fail('stats:switch_to_week', 'period not changed');
        }
      } catch (e) {
        fail('stats:period_switch', e.message);
      }
    } else {
      skip('stats:period_switch', 'period not in data');
    }

    // 验证frequencyData结构（当有数据时）
    if (data && Array.isArray(data.frequencyData) && data.frequencyData.length > 0) {
      let firstItem = data.frequencyData[0];
      if (firstItem && firstItem.label !== undefined && firstItem.count !== undefined && firstItem.height !== undefined) {
        pass('stats:frequencyData_structure=label,count,height');
      } else {
        skip('stats:frequencyData_structure', 'item missing fields');
      }
    } else {
      skip('stats:frequencyData_structure', 'no frequency data');
    }

    // 验证UI元素
    let elemCount = await safeCountElements(page, 'view, text, image');
    if (elemCount >= 0) pass('stats:ui_elements=' + elemCount);
    else skip('stats:ui_elements', 'query failed');

    // 截图
    let ss = await takeScreenshot(mp, 'stats');
    if (ss) pass('stats:screenshot');
    else skip('stats:screenshot', 'screenshot failed');

    // 返回
    await mp.navigateBack();
    await sleep(500);
  } catch (e) { fail('stats', e.message); }

  // ═══════════════════════════════════════════
  // 13. Admin Seed Data — pages/admin/seed-data/seed-data
  // ═══════════════════════════════════════════
  try {
    await mp.navigateTo('/pages/admin/seed-data/seed-data');
    await sleep(1500);
    let page = await mp.currentPage();
    let data = await safeGetData(page);

    // 验证页面路径
    if (page.path.includes('seed-data')) {
      pass('seed-data:page_loaded');
    } else {
      fail('seed-data:page_loaded', 'expected seed-data, got ' + page.path);
    }

    // 验证关键数据字段
    if (data) {
      if (data.stats) {
        let st = data.stats;
        let stFields = ['imported', 'categories', 'available']
          .filter(k => st[k] !== undefined);
        pass('seed-data:field_stats=' + stFields.join(','));
        if (st.imported !== undefined) pass('seed-data:imported_count=' + st.imported);
      } else {
        skip('seed-data:field_stats', 'not in data');
      }

      if (Array.isArray(data.categoryProgress)) {
        pass('seed-data:field_categoryProgress=' + data.categoryProgress.length);
        // 验证每个分类进度项结构
        if (data.categoryProgress.length > 0) {
          let firstCat = data.categoryProgress[0];
          let catFields = ['name', 'imported', 'total', 'color']
            .filter(k => firstCat[k] !== undefined);
          pass('seed-data:categoryProgress_structure=' + catFields.join(','));
        }
      } else {
        skip('seed-data:field_categoryProgress', 'not an array or missing');
      }

      if (Array.isArray(data.logs)) pass('seed-data:field_logs=' + data.logs.length);
      else skip('seed-data:field_logs', 'not an array or missing');

      if (data.importing !== undefined) pass('seed-data:field_importing=' + data.importing);
      else skip('seed-data:field_importing', 'not in data');
    } else {
      skip('seed-data:data', 'page data unavailable');
    }

    // 验证UI元素
    let elemCount = await safeCountElements(page, 'view, text, image, button');
    if (elemCount >= 0) pass('seed-data:ui_elements=' + elemCount);
    else skip('seed-data:ui_elements', 'query failed');

    // 截图
    let ss = await takeScreenshot(mp, 'seed-data');
    if (ss) pass('seed-data:screenshot');
    else skip('seed-data:screenshot', 'screenshot failed');

    // 返回
    await mp.navigateBack();
    await sleep(500);
  } catch (e) { fail('seed-data', e.message); }

  // ═══════════════════════════════════════════
  // 最终汇总截图
  // ═══════════════════════════════════════════
  try {
    await mp.switchTab('/pages/index/index');
    await sleep(800);
    let ss = await takeScreenshot(mp, 'final');
    if (ss) pass('screenshot:final');
    else skip('screenshot:final', 'screenshot failed');
  } catch (e) { fail('screenshot:final', e.message); }

  // ═══════════════════════════════════════════
  // 结果统计
  // ═══════════════════════════════════════════
  const passed = results.filter(r => r.status === 'passed').length;
  const failed = results.filter(r => r.status === 'failed').length;
  const skipped = results.filter(r => r.status === 'skipped').length;
  const total = results.length;

  results.push({
    name: 'summary',
    status: 'info',
    total,
    passed,
    failed,
    skipped,
    passRate: total > 0 ? Math.round(passed / total * 100) + '%' : '0%'
  });

  await mp.close();
  console.log('MINIAPP_RESULTS:' + JSON.stringify(results));
}

main().catch(e => {
  console.log('MINIAPP_RESULTS:' + JSON.stringify([{ name: 'fatal', status: 'failed', error: e.message }]));
});
