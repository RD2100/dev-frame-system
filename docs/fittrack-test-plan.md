# FitTrack 测试计划

> 项目：FitTrack 健身管理微信小程序  
> 路径：D:\FitnessManagement  
> 日期：2026-05-21

---

## 一、测试范围

| 层 | 框架 | 覆盖范围 | 测试数 |
|---|------|---------|--------|
| L1 单元测试 | Jest | util / constants / cloud / schemas | ~45 (已有) |
| L2 API 集成 | TestFrame pytest | 云函数 Mock (login/getExercises/getPlans/saveWorkout/planTemplates/admin) | 20 (已建) |
| L3 业务规则 | TestFrame pytest | 数据模型 / 页面注册 / 分类完整性 / TabBar 约束 | 25 (已建) |
| L4 小程序 E2E | TestFrame miniprogram-automator | 页面导航 / 数据渲染 / 截图 | 9 (已建) |
| L5 回归归因 | TestFrame 引擎 | 失败归因 / 门禁 / Allure 报告 | 自动 |

## 二、测试用例清单

### L1：单元测试（FitnessManagement 项目内 Jest）

| 文件 | 测试内容 |
|------|---------|
| `utils/__tests__/util.test.js` | generateId / deepClone / calcBMI / getBMILevel / calcWorkoutVolume / calcWorkoutDuration / getWeekRange / getMonthRange / storage |
| `utils/__tests__/constants.test.js` | 8分类完整性 / 8设备 / 3难度 / 6目标 / formatWeight / formatDuration / formatDate / formatVolume / 查找函数 |
| `utils/__tests__/cloud.test.js` | call成功/data格式/errMsg/错误抛出/重试/快捷方法 |
| `models/__tests__/schemas.test.js` | exercise/plan/workout/user/bodyMetric/record 6类schema字段+默认值 |

### L2：API 集成测试（TestFrame pytest + Mock）

| 模块 | 用例 | 验证点 |
|------|------|--------|
| Login | test_login_creates_user | openid生成、用户创建、字段完整性 |
| Login | test_login_returns_existing_user | 重复登录返回同一用户 |
| Login | test_login_user_has_required_fields | 8个必填字段 |
| getExercises | test_list_all_active | 只返回active、有name/category |
| getExercises | test_list_by_category | 分类过滤正确 |
| getExercises | test_list_pagination | 分页正确 |
| getExercises | test_detail_existing | 详情查询 |
| getExercises | test_detail_not_found | 不存在返回-1 |
| getExercises | test_detail_missing_id | 缺参数返回-1 |
| getExercises | test_search_finds_match | 关键词搜索 |
| getExercises | test_by_category | 分类查询 |
| getExercises | test_unknown_action | 未知action返回-1 |
| getPlans | test_list_all_plans | 计划列表完整性 |
| getPlans | test_active_only | 仅激活筛选 |
| getPlans | test_plan_has_valid_structure | day/exercises结构 |
| saveWorkout | test_save_valid_workout | 保存返回id |
| saveWorkout | test_save_empty_workout | 空训练保存 |
| planTemplates | test_list_templates | 4个模板 |
| Admin | test_stats/tests_seed | 统计+种子 |

### L3：业务规则验证（TestFrame pytest）

| 模块 | 用例 | 规则 |
|------|------|------|
| Categories | test_all_categories_have_id_and_name | 数据完整性 |
| Categories | test_categories_count | 8个分类 |
| Categories | test_category_ids_unique | ID唯一 |
| Categories | test_each_category_has_muscles | 肌群映射 |
| Equipment | test_all_equipment_have_id_and_name | 8种设备 |
| Equipment | test_equipment_ids_unique | ID唯一 |
| Equipment | test_bodyweight_included | 自重训练必备 |
| Difficulties | test_three_levels | 3个等级 |
| Difficulties | test_levels_ordered | 顺序正确 |
| TrainingGoals | test_general_is_default | general存在 |
| PageRegistration | test_all_pages_registered | 13页 |
| PageRegistration | test_tabbar_pages_in_list | 4个tab页都在 |
| PageRegistration | test_login_is_first_page | login首页 |
| CloudFunctions | test_required_functions_exist | 6个业务函数 |
| CloudFunctions | test_function_count | <50限制 |
| ExerciseRules | test_valid/invalid_category | 分类校验 |
| ExerciseRules | test_valid_difficulty/equipment | 难度+设备校验 |
| WorkoutValidation | test_volume_calculation | weight*reps*sets |
| WorkoutValidation | test_duration_formatting | 秒→可读格式 |
| WorkoutValidation | test_sets_minimum | 至少1组 |
| TabBarConfig | test_four_tabs | 4个tab |
| TabBarConfig | test_no_navigateTo | 禁止navigateTo跳tab |
| OpenID | test_valid_openid_pattern | 正则校验 |

### L4：小程序 E2E（miniprogram-automator）

| # | 测试 | 验证 |
|---|------|------|
| 1 | 当前页面 | 加载到 index |
| 2 | 系统信息 | platform/SDK/model |
| 3 | 页面栈 | 栈信息正确 |
| 4 | Tab-动作库 | 跳转正确 |
| 5 | Tab-训练 | 跳转正确 |
| 6 | Tab-我的 | 跳转正确 |
| 7 | Tab-首页 | 跳转正确 |
| 8 | 首页数据 | greeting/todayPlanText/avatarUrl/todayWorkout/weekStats |
| 9 | 动作库数据 | keyword/categories/exercises/loading/page/hasMore |
| 10 | 截图 | 动作库页面截图 |

### L5：回归与报告

| 步骤 | 工具 | 输出 |
|------|------|------|
| 结果聚合 | TestFrame aggregator | Allure JSON |
| 缺陷归因 | TestFrame attribution engine | 归因报告 |
| 质量门禁 | TestFrame gate | PASS/BLOCKED |
| HTML报告 | Allure | index.html |

## 三、执行顺序

```
Stage 0: 环境就绪（IDE 运行中、服务端口开启）
Stage 1: Jest 单元测试（FitnessManagement 项目内）
Stage 2: pytest API + 规则测试（TestFrame）
Stage 3: 小程序 E2E 测试（miniprogram-automator）
Stage 4: 结果聚合 + 归因 + 门禁 + Allure 报告
```
