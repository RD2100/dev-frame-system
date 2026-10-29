"""FitTrack API 集成测试

覆盖全部12个云函数的HTTP接口测试:
- login / getExercises / getPlans / saveWorkout / planTemplates / seedExercises
- adminAuth / adminExercises / adminPlans / adminUsers / adminStats / adminSeed

所有测试POST到 http://127.0.0.1:8765/api/{functionName}
需先启动 mock_server.py
"""

import json
import time
import unittest
import hashlib
import requests

BASE = "http://127.0.0.1:8765/api"


def call(fn, data=None):
    """调用云函数"""
    r = requests.post(f"{BASE}/{fn}", json=data or {}, timeout=5)
    return r.json()


def call_ok(fn, data=None):
    """调用云函数并返回data"""
    resp = call(fn, data)
    assert resp["code"] == 0, f"expected code=0, got {resp['code']}: {resp['msg']}"
    return resp["data"]


def admin_token():
    """获取管理员token"""
    resp = call("adminAuth", {"action": "login", "username": "admin", "password": "admin123"})
    assert resp["code"] == 0, f"admin login failed: {resp['msg']}"
    return resp["data"]["token"]


# ══════════════════════════════════
# ── 用户端云函数 ──
# ══════════════════════════════════


class TestLogin(unittest.TestCase):
    """login 云函数测试"""

    def test_basic_login(self):
        """基本登录，应返回用户信息"""
        data = call_ok("login")
        self.assertIn("_id", data)
        self.assertIn("nickname", data)
        self.assertIn("createdAt", data)

    def test_login_returns_new_user(self):
        """每次登录应返回有效用户（新或已有）"""
        data = call_ok("login")
        self.assertTrue(data["_id"].startswith("mock_openid_"))

    def test_login_user_has_body_metrics(self):
        """用户应包含体测数据"""
        data = call_ok("login")
        self.assertIn("bodyMetrics", data)
        self.assertIn("height", data["bodyMetrics"])
        self.assertIn("weight", data["bodyMetrics"])


class TestGetExercises(unittest.TestCase):
    """getExercises 云函数测试"""

    def test_list_all(self):
        """无筛选条件应返回动作列表"""
        data = call_ok("getExercises")
        self.assertIn("items", data)
        self.assertIn("total", data)
        self.assertGreaterEqual(data["total"], 0)

    def test_filter_by_category(self):
        """按分类筛选"""
        data = call_ok("getExercises", {"category": "chest"})
        for item in data["items"]:
            self.assertEqual(item["category"], "chest")

    def test_filter_by_keyword(self):
        """按关键词筛选"""
        data = call_ok("getExercises", {"keyword": "卧推"})
        for item in data["items"]:
            self.assertIn("卧推", item["name"])

    def test_empty_keyword_returns_all(self):
        """空关键词应返回所有active动作"""
        data = call_ok("getExercises", {"keyword": ""})
        self.assertGreater(data["total"], 0)

    def test_invalid_category_returns_empty(self):
        """无效分类应返回空列表"""
        data = call_ok("getExercises", {"category": "nonexistent"})
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["items"], [])

    def test_large_pagination(self):
        """大分页参数应正常工作"""
        data = call_ok("getExercises", {"page": 100, "pageSize": 50})
        self.assertEqual(data["items"], [])
        self.assertEqual(data["page"], 100)

    def test_pagination_page1(self):
        """分页第1页"""
        data = call_ok("getExercises", {"page": 1, "pageSize": 3})
        self.assertLessEqual(len(data["items"]), 3)
        self.assertEqual(data["page"], 1)

    def test_filter_by_difficulty(self):
        """按难度筛选"""
        data = call_ok("getExercises", {"difficulty": "beginner"})
        for item in data["items"]:
            self.assertEqual(item["difficulty"], "beginner")

    def test_filter_by_equipment(self):
        """按器械筛选"""
        data = call_ok("getExercises", {"equipment": "barbell"})
        for item in data["items"]:
            self.assertEqual(item["equipment"], "barbell")

    def test_default_excludes_inactive(self):
        """默认不返回inactive动作"""
        data = call_ok("getExercises")
        for item in data["items"]:
            self.assertEqual(item["status"], "active")


class TestGetPlans(unittest.TestCase):
    """getPlans 云函数测试"""

    def test_list_plans(self):
        """列出训练计划"""
        data = call_ok("getPlans", {"action": "list"})
        self.assertIn("items", data)
        self.assertIn("total", data)

    def test_filter_by_goal(self):
        """按目标筛选计划"""
        data = call_ok("getPlans", {"action": "list", "goal": "hypertrophy"})
        for item in data["items"]:
            self.assertEqual(item["goal"], "hypertrophy")

    def test_plan_detail(self):
        """获取计划详情"""
        data = call_ok("getPlans", {"action": "detail", "planId": "plan_001"})
        self.assertEqual(data["_id"], "plan_001")

    def test_plan_detail_not_found(self):
        """查询不存在的计划"""
        resp = call("getPlans", {"action": "detail", "planId": "plan_nonexist"})
        self.assertNotEqual(resp["code"], 0)

    def test_create_plan(self):
        """创建新计划"""
        data = call_ok("getPlans", {
            "action": "create", "name": "测试计划", "goal": "strength",
            "frequency": 4, "days": [{"day": 1, "name": "上肢", "exercises": ["ex_001"]}]
        })
        self.assertEqual(data["name"], "测试计划")
        self.assertEqual(data["goal"], "strength")
        self.assertFalse(data.get("isTemplate", False))

    def test_create_plan_empty_name(self):
        """创建计划名称为空应失败"""
        resp = call("getPlans", {"action": "create", "name": ""})
        self.assertNotEqual(resp["code"], 0)

    def test_update_plan(self):
        """更新计划"""
        data = call_ok("getPlans", {
            "action": "update", "planId": "plan_001",
            "name": "更新后的计划", "frequency": 5
        })
        self.assertEqual(data["name"], "更新后的计划")
        self.assertEqual(data["frequency"], 5)

    def test_delete_plan(self):
        """删除计划"""
        # 先创建一个计划
        created = call_ok("getPlans", {"action": "create", "name": "待删除计划"})
        plan_id = created["_id"]
        # 删除
        data = call_ok("getPlans", {"action": "delete", "planId": plan_id})
        self.assertEqual(data["deleted"], plan_id)
        # 验证已删除
        resp = call("getPlans", {"action": "detail", "planId": plan_id})
        self.assertNotEqual(resp["code"], 0)

    def test_pagination(self):
        """分页参数"""
        data = call_ok("getPlans", {"action": "list", "page": 1, "pageSize": 1})
        self.assertLessEqual(len(data["items"]), 1)


class TestSaveWorkout(unittest.TestCase):
    """saveWorkout 云函数测试"""

    def test_save_basic_workout(self):
        """保存基本训练记录"""
        data = call_ok("saveWorkout", {
            "action": "save", "planName": "测试训练",
            "exercises": [{"exerciseId": "ex_001", "name": "卧推",
                           "sets": [{"weight": 60, "reps": 10}, {"weight": 70, "reps": 8}]}],
            "duration": 3600
        })
        self.assertIn("_id", data)
        self.assertEqual(data["totalSets"], 2)
        self.assertAlmostEqual(data["totalVolume"], 60 * 10 + 70 * 8)

    def test_start_workout(self):
        """开始训练（in_progress状态）"""
        data = call_ok("saveWorkout", {
            "action": "start", "planId": "plan_001", "planName": "推拉腿"
        })
        self.assertEqual(data["status"], "in_progress")
        self.assertIn("_id", data)
        workout_id = data["_id"]
        return workout_id

    def test_update_set(self):
        """更新训练组数据"""
        # 先开始训练
        started = call_ok("saveWorkout", {
            "action": "start", "planName": "测试更新组",
            "exercises": [{"exerciseId": "ex_001", "sets": [{"weight": 50, "reps": 10}]}]
        })
        wid = started["_id"]
        # 更新某组
        data = call_ok("saveWorkout", {
            "action": "updateSet", "workoutId": wid,
            "exerciseIndex": 0, "setIndex": 0,
            "setData": {"weight": 60, "reps": 12}
        })
        self.assertEqual(data["exercises"][0]["sets"][0]["weight"], 60)

    def test_complete_workout(self):
        """完成训练"""
        started = call_ok("saveWorkout", {
            "action": "start", "planName": "待完成训练",
            "exercises": [{"exerciseId": "ex_001", "name": "卧推",
                           "sets": [{"weight": 80, "reps": 5}]}]
        })
        wid = started["_id"]
        data = call_ok("saveWorkout", {
            "action": "complete", "workoutId": wid, "duration": 2700
        })
        self.assertEqual(data["status"], "completed")
        self.assertIsNotNone(data["endTime"])

    def test_workout_history(self):
        """获取训练历史"""
        # 先保存一个训练
        call_ok("saveWorkout", {"action": "save", "planName": "历史训练"})
        data = call_ok("saveWorkout", {"action": "history"})
        self.assertIn("items", data)
        self.assertIn("total", data)

    def test_workout_history_pagination(self):
        """训练历史分页"""
        data = call_ok("saveWorkout", {"action": "history", "page": 1, "pageSize": 2})
        self.assertIn("items", data)
        self.assertLessEqual(len(data["items"]), 2)

    def test_workout_history_filter_status(self):
        """按状态筛选训练历史"""
        data = call_ok("saveWorkout", {"action": "history", "status": "completed"})
        for item in data["items"]:
            self.assertEqual(item["status"], "completed")

    def test_workout_detail(self):
        """获取训练详情"""
        saved = call_ok("saveWorkout", {"action": "save", "planName": "详情测试"})
        wid = saved["_id"]
        data = call_ok("saveWorkout", {"action": "detail", "workoutId": wid})
        self.assertEqual(data["_id"], wid)

    def test_workout_detail_not_found(self):
        """查询不存在的训练"""
        resp = call("saveWorkout", {"action": "detail", "workoutId": "wk_nonexist"})
        self.assertNotEqual(resp["code"], 0)

    def test_update_profile(self):
        """更新用户资料"""
        data = call_ok("saveWorkout", {
            "action": "updateProfile",
            "profile": {"nickname": "健身达人", "bodyMetrics": {"weight": 72}}
        })
        self.assertEqual(data["nickname"], "健身达人")

    def test_personal_records(self):
        """获取个人记录"""
        # 先完成一个训练以生成PR
        started = call_ok("saveWorkout", {
            "action": "start", "planName": "PR测试",
            "exercises": [{"exerciseId": "ex_001", "name": "卧推",
                           "sets": [{"weight": 100, "reps": 5}]}]
        })
        call_ok("saveWorkout", {"action": "complete", "workoutId": started["_id"], "duration": 1800})
        # 查询PR
        data = call_ok("saveWorkout", {"action": "personalRecords"})
        self.assertIn("ex_001", data)
        self.assertEqual(data["ex_001"]["weight"], 100)

    def test_personal_records_auto_update(self):
        """PR自动更新：更大重量应覆盖"""
        # 第一轮训练
        started1 = call_ok("saveWorkout", {
            "action": "start", "planName": "PR更新1",
            "exercises": [{"exerciseId": "ex_004", "name": "深蹲",
                           "sets": [{"weight": 80, "reps": 10}]}]
        })
        call_ok("saveWorkout", {"action": "complete", "workoutId": started1["_id"], "duration": 1800})
        # 第二轮更大重量
        started2 = call_ok("saveWorkout", {
            "action": "start", "planName": "PR更新2",
            "exercises": [{"exerciseId": "ex_004", "name": "深蹲",
                           "sets": [{"weight": 100, "reps": 8}]}]
        })
        call_ok("saveWorkout", {"action": "complete", "workoutId": started2["_id"], "duration": 1800})
        data = call_ok("saveWorkout", {"action": "personalRecords"})
        self.assertGreaterEqual(data["ex_004"]["weight"], 100)


class TestPlanTemplates(unittest.TestCase):
    """planTemplates 云函数测试"""

    def test_list_templates(self):
        """获取模板列表"""
        data = call_ok("planTemplates")
        self.assertIn("items", data)
        self.assertIn("total", data)

    def test_templates_are_marked(self):
        """模板应标记isTemplate"""
        data = call_ok("planTemplates")
        for item in data["items"]:
            self.assertTrue(item.get("isTemplate"))


class TestSeedExercises(unittest.TestCase):
    """seedExercises 云函数测试"""

    def test_init(self):
        """初始化种子数据"""
        data = call_ok("seedExercises", {"action": "init"})
        self.assertTrue(data["initialized"])
        self.assertGreater(data["count"], 0)

    def test_status(self):
        """种子数据状态"""
        data = call_ok("seedExercises", {"action": "status"})
        self.assertIn("total", data)
        self.assertIn("active", data)

    def test_unknown_action(self):
        """未知操作应报错"""
        resp = call("seedExercises", {"action": "invalid"})
        self.assertNotEqual(resp["code"], 0)


# ══════════════════════════════════
# ── 管理端云函数 ──
# ══════════════════════════════════


class TestAdminAuth(unittest.TestCase):
    """adminAuth 云函数测试"""

    def test_login_success(self):
        """管理员登录成功"""
        data = call_ok("adminAuth", {"action": "login", "username": "admin", "password": "admin123"})
        self.assertIn("token", data)
        self.assertIn("admin", data)
        self.assertEqual(data["admin"]["username"], "admin")

    def test_login_wrong_password(self):
        """错误密码应登录失败"""
        resp = call("adminAuth", {"action": "login", "username": "admin", "password": "wrong"})
        self.assertNotEqual(resp["code"], 0)

    def test_login_empty_credentials(self):
        """空用户名/密码应登录失败"""
        resp1 = call("adminAuth", {"action": "login", "username": "", "password": "test"})
        self.assertNotEqual(resp1["code"], 0)
        resp2 = call("adminAuth", {"action": "login", "username": "admin", "password": ""})
        self.assertNotEqual(resp2["code"], 0)

    def test_verify_valid_token(self):
        """验证有效token"""
        login_data = call_ok("adminAuth", {"action": "login", "username": "admin", "password": "admin123"})
        token = login_data["token"]
        data = call_ok("adminAuth", {"action": "verify", "token": token})
        self.assertTrue(data["valid"])

    def test_verify_invalid_token(self):
        """验证无效token应失败"""
        resp = call("adminAuth", {"action": "verify", "token": "invalid_token"})
        self.assertNotEqual(resp["code"], 0)

    def test_change_password(self):
        """修改密码"""
        token = admin_token()
        # 修改密码
        data = call_ok("adminAuth", {
            "action": "changePassword", "token": token,
            "oldPassword": "admin123", "newPassword": "newpass123"
        })
        self.assertTrue(data["changed"])
        # 用新密码登录
        login_data = call_ok("adminAuth", {"action": "login", "username": "admin", "password": "newpass123"})
        self.assertIn("token", login_data)
        # 改回原密码
        new_token = login_data["token"]
        call_ok("adminAuth", {
            "action": "changePassword", "token": new_token,
            "oldPassword": "newpass123", "newPassword": "admin123"
        })

    def test_change_password_wrong_old(self):
        """旧密码错误应修改失败"""
        token = admin_token()
        resp = call("adminAuth", {
            "action": "changePassword", "token": token,
            "oldPassword": "wrong", "newPassword": "newpass123"
        })
        self.assertNotEqual(resp["code"], 0)

    def test_change_password_too_short(self):
        """新密码太短应修改失败"""
        token = admin_token()
        resp = call("adminAuth", {
            "action": "changePassword", "token": token,
            "oldPassword": "admin123", "newPassword": "12345"
        })
        self.assertNotEqual(resp["code"], 0)

    def test_change_password_no_auth(self):
        """无token修改密码应失败"""
        resp = call("adminAuth", {
            "action": "changePassword",
            "oldPassword": "admin123", "newPassword": "newpass123"
        })
        self.assertNotEqual(resp["code"], 0)

    def test_create_admin(self):
        """创建新管理员"""
        token = admin_token()
        # 使用时间戳确保用户名唯一，避免跨测试状态残留
        ts = int(time.time() * 1000) % 100000
        data = call_ok("adminAuth", {
            "action": "createAdmin", "token": token,
            "username": f"testadmin_{ts}", "password": "test123456", "role": "admin"
        })
        self.assertIn("testadmin_", data["username"])
        self.assertEqual(data["role"], "admin")

    def test_create_admin_duplicate_username(self):
        """重复用户名应创建失败"""
        token = admin_token()
        ts = int(time.time() * 1000) % 100000
        dup_name = f"dup_admin_{ts}"
        # 先创建
        call_ok("adminAuth", {
            "action": "createAdmin", "token": token,
            "username": dup_name, "password": "test123456"
        })
        # 重复创建
        resp = call("adminAuth", {
            "action": "createAdmin", "token": token,
            "username": dup_name, "password": "test123456"
        })
        self.assertNotEqual(resp["code"], 0)

    def test_create_admin_short_password(self):
        """密码太短应创建失败"""
        token = admin_token()
        ts = int(time.time() * 1000) % 100000
        resp = call("adminAuth", {
            "action": "createAdmin", "token": token,
            "username": f"shortpw_{ts}", "password": "12345"
        })
        self.assertNotEqual(resp["code"], 0)

    def test_create_admin_no_auth(self):
        """无token创建管理员应失败"""
        resp = call("adminAuth", {
            "action": "createAdmin",
            "username": "noauth_admin", "password": "test123456"
        })
        self.assertNotEqual(resp["code"], 0)

    def test_create_admin_non_super(self):
        """非super_admin创建管理员应失败"""
        token = admin_token()
        ts = int(time.time() * 1000) % 100000
        # 先创建一个普通admin
        new_admin = call_ok("adminAuth", {
            "action": "createAdmin", "token": token,
            "username": f"normal_admin_{ts}", "password": "normal123456", "role": "admin"
        })
        # 用普通admin登录
        login_data = call_ok("adminAuth", {"action": "login", "username": f"normal_admin_{ts}", "password": "normal123456"})
        normal_token = login_data["token"]
        # 尝试创建管理员
        resp = call("adminAuth", {
            "action": "createAdmin", "token": normal_token,
            "username": f"should_fail_{ts}", "password": "test123456"
        })
        self.assertNotEqual(resp["code"], 0)


class TestAdminExercises(unittest.TestCase):
    """adminExercises 云函数测试"""

    def setUp(self):
        self.token = admin_token()

    def test_list_exercises(self):
        """管理员列出动作"""
        data = call_ok("adminExercises", {"action": "list", "token": self.token})
        self.assertIn("items", data)
        self.assertIn("total", data)

    def test_list_with_filters(self):
        """带筛选条件列出动作"""
        data = call_ok("adminExercises", {
            "action": "list", "token": self.token,
            "category": "chest", "status": "active"
        })
        for item in data["items"]:
            self.assertEqual(item["category"], "chest")
            self.assertEqual(item["status"], "active")

    def test_list_with_keyword(self):
        """按关键词搜索动作"""
        data = call_ok("adminExercises", {
            "action": "list", "token": self.token, "keyword": "杠铃"
        })
        for item in data["items"]:
            self.assertIn("杠铃", item["name"])

    def test_exercise_detail(self):
        """获取动作详情"""
        data = call_ok("adminExercises", {"action": "detail", "token": self.token, "exerciseId": "ex_001"})
        self.assertEqual(data["_id"], "ex_001")
        self.assertIn("name", data)

    def test_exercise_detail_not_found(self):
        """查询不存在动作"""
        resp = call("adminExercises", {"action": "detail", "token": self.token, "exerciseId": "ex_nonexist"})
        self.assertNotEqual(resp["code"], 0)

    def test_create_exercise(self):
        """创建动作"""
        data = call_ok("adminExercises", {
            "action": "create", "token": self.token,
            "name": "测试动作", "category": "chest",
            "difficulty": "intermediate", "equipment": "dumbbell",
            "muscleGroups": ["胸大肌"]
        })
        self.assertEqual(data["name"], "测试动作")
        self.assertEqual(data["category"], "chest")

    def test_create_exercise_missing_fields(self):
        """缺少必填字段应创建失败"""
        resp = call("adminExercises", {
            "action": "create", "token": self.token,
            "name": "", "category": ""
        })
        self.assertNotEqual(resp["code"], 0)

    def test_update_exercise(self):
        """更新动作"""
        data = call_ok("adminExercises", {
            "action": "update", "token": self.token,
            "exerciseId": "ex_002", "name": "更新后动作", "difficulty": "advanced"
        })
        self.assertEqual(data["name"], "更新后动作")
        self.assertEqual(data["difficulty"], "advanced")

    def test_update_exercise_not_found(self):
        """更新不存在动作应失败"""
        resp = call("adminExercises", {
            "action": "update", "token": self.token,
            "exerciseId": "ex_nonexist", "name": "不存在"
        })
        self.assertNotEqual(resp["code"], 0)

    def test_delete_exercise(self):
        """删除动作"""
        # 先创建一个
        created = call_ok("adminExercises", {
            "action": "create", "token": self.token,
            "name": "待删除动作", "category": "leg"
        })
        ex_id = created["_id"]
        data = call_ok("adminExercises", {"action": "delete", "token": self.token, "exerciseId": ex_id})
        self.assertEqual(data["deleted"], ex_id)

    def test_delete_exercise_not_found(self):
        """删除不存在动作应失败"""
        resp = call("adminExercises", {"action": "delete", "token": self.token, "exerciseId": "ex_nonexist"})
        self.assertNotEqual(resp["code"], 0)

    def test_batch_status(self):
        """批量更新状态"""
        data = call_ok("adminExercises", {
            "action": "batchStatus", "token": self.token,
            "exerciseIds": ["ex_010"], "status": "active"
        })
        self.assertGreaterEqual(data["updated"], 1)

    def test_batch_status_empty_ids(self):
        """空ID列表应失败"""
        resp = call("adminExercises", {
            "action": "batchStatus", "token": self.token,
            "exerciseIds": [], "status": "active"
        })
        self.assertNotEqual(resp["code"], 0)

    def test_exercise_stats(self):
        """动作统计"""
        data = call_ok("adminExercises", {"action": "stats", "token": self.token})
        self.assertIn("total", data)
        self.assertIn("active", data)
        self.assertIn("byCategory", data)
        self.assertIn("byDifficulty", data)

    def test_no_auth(self):
        """无token应被拒绝"""
        resp = call("adminExercises", {"action": "list"})
        self.assertNotEqual(resp["code"], 0)


class TestAdminPlans(unittest.TestCase):
    """adminPlans 云函数测试"""

    def setUp(self):
        self.token = admin_token()

    def test_list_plans(self):
        """管理员列出计划"""
        data = call_ok("adminPlans", {"action": "list", "token": self.token})
        self.assertIn("items", data)
        self.assertIn("total", data)

    def test_list_template_plans(self):
        """只列模板计划"""
        data = call_ok("adminPlans", {"action": "list", "token": self.token, "isTemplate": True})
        for item in data["items"]:
            self.assertTrue(item.get("isTemplate"))

    def test_list_by_goal(self):
        """按目标筛选计划"""
        data = call_ok("adminPlans", {"action": "list", "token": self.token, "goal": "hypertrophy"})
        for item in data["items"]:
            self.assertEqual(item["goal"], "hypertrophy")

    def test_plan_detail(self):
        """获取计划详情"""
        data = call_ok("adminPlans", {"action": "detail", "token": self.token, "planId": "plan_001"})
        self.assertEqual(data["_id"], "plan_001")

    def test_plan_detail_not_found(self):
        """不存在的计划"""
        resp = call("adminPlans", {"action": "detail", "token": self.token, "planId": "plan_nonexist"})
        self.assertNotEqual(resp["code"], 0)

    def test_create_plan(self):
        """创建计划"""
        data = call_ok("adminPlans", {
            "action": "create", "token": self.token,
            "name": "管理员计划", "goal": "strength", "frequency": 4,
            "isTemplate": True
        })
        self.assertEqual(data["name"], "管理员计划")
        self.assertTrue(data["isTemplate"])

    def test_create_plan_empty_name(self):
        """空名称应创建失败"""
        resp = call("adminPlans", {"action": "create", "token": self.token, "name": ""})
        self.assertNotEqual(resp["code"], 0)

    def test_update_plan(self):
        """更新计划"""
        data = call_ok("adminPlans", {
            "action": "update", "token": self.token,
            "planId": "plan_002", "name": "更新计划", "frequency": 5
        })
        self.assertEqual(data["name"], "更新计划")

    def test_update_plan_not_found(self):
        """更新不存在计划"""
        resp = call("adminPlans", {
            "action": "update", "token": self.token,
            "planId": "plan_nonexist", "name": "不存在"
        })
        self.assertNotEqual(resp["code"], 0)

    def test_delete_plan(self):
        """删除计划"""
        created = call_ok("adminPlans", {
            "action": "create", "token": self.token, "name": "待删计划"
        })
        data = call_ok("adminPlans", {"action": "delete", "token": self.token, "planId": created["_id"]})
        self.assertEqual(data["deleted"], created["_id"])

    def test_delete_plan_not_found(self):
        """删除不存在计划"""
        resp = call("adminPlans", {"action": "delete", "token": self.token, "planId": "plan_nonexist"})
        self.assertNotEqual(resp["code"], 0)

    def test_set_template(self):
        """设置/取消模板"""
        data = call_ok("adminPlans", {
            "action": "setTemplate", "token": self.token,
            "planId": "plan_002", "isTemplate": True
        })
        self.assertTrue(data["isTemplate"])

    def test_assign_plan_to_users(self):
        """分配计划给用户"""
        data = call_ok("adminPlans", {
            "action": "assign", "token": self.token,
            "planId": "plan_001", "userIds": ["mock_openid_1001", "mock_openid_1002"]
        })
        self.assertIn("mock_openid_1001", data["assignedTo"])

    def test_assign_empty_users(self):
        """空用户列表应失败"""
        resp = call("adminPlans", {
            "action": "assign", "token": self.token,
            "planId": "plan_001", "userIds": []
        })
        self.assertNotEqual(resp["code"], 0)

    def test_plan_stats(self):
        """计划统计"""
        data = call_ok("adminPlans", {"action": "stats", "token": self.token})
        self.assertIn("total", data)
        self.assertIn("templates", data)
        self.assertIn("active", data)
        self.assertIn("byGoal", data)

    def test_no_auth(self):
        """无token应被拒绝"""
        resp = call("adminPlans", {"action": "list"})
        self.assertNotEqual(resp["code"], 0)


class TestAdminUsers(unittest.TestCase):
    """adminUsers 云函数测试"""

    def setUp(self):
        self.token = admin_token()
        # 确保至少有一个用户
        self.test_user = call_ok("login")

    def test_list_users(self):
        """列出用户"""
        data = call_ok("adminUsers", {"action": "list", "token": self.token})
        self.assertIn("items", data)
        self.assertIn("total", data)
        self.assertGreaterEqual(data["total"], 1)

    def test_list_users_with_keyword(self):
        """按昵称搜索用户"""
        data = call_ok("adminUsers", {
            "action": "list", "token": self.token,
            "keyword": self.test_user["nickname"][:2]
        })
        self.assertGreaterEqual(data["total"], 1)

    def test_user_detail(self):
        """获取用户详情（含训练摘要）"""
        data = call_ok("adminUsers", {
            "action": "detail", "token": self.token,
            "userId": self.test_user["_id"]
        })
        self.assertEqual(data["_id"], self.test_user["_id"])
        self.assertIn("workoutSummary", data)
        self.assertIn("totalWorkouts", data["workoutSummary"])

    def test_user_detail_not_found(self):
        """查询不存在用户"""
        resp = call("adminUsers", {"action": "detail", "token": self.token, "userId": "nonexist"})
        self.assertNotEqual(resp["code"], 0)

    def test_update_user(self):
        """更新用户信息"""
        data = call_ok("adminUsers", {
            "action": "update", "token": self.token,
            "userId": self.test_user["_id"],
            "nickname": "管理员修改昵称", "level": 3
        })
        self.assertEqual(data["nickname"], "管理员修改昵称")
        self.assertEqual(data["level"], 3)

    def test_update_user_body_metrics(self):
        """更新用户体测数据"""
        data = call_ok("adminUsers", {
            "action": "update", "token": self.token,
            "userId": self.test_user["_id"],
            "bodyMetrics": {"weight": 75, "height": 180}
        })
        self.assertEqual(data["bodyMetrics"]["weight"], 75)

    def test_update_user_not_found(self):
        """更新不存在用户"""
        resp = call("adminUsers", {
            "action": "update", "token": self.token,
            "userId": "nonexist", "nickname": "不存在"
        })
        self.assertNotEqual(resp["code"], 0)

    def test_delete_user(self):
        """删除用户"""
        # 创建一个临时用户
        temp_user = call_ok("login")
        data = call_ok("adminUsers", {
            "action": "delete", "token": self.token,
            "userId": temp_user["_id"]
        })
        self.assertEqual(data["deleted"], temp_user["_id"])

    def test_delete_user_not_found(self):
        """删除不存在用户"""
        resp = call("adminUsers", {"action": "delete", "token": self.token, "userId": "nonexist"})
        self.assertNotEqual(resp["code"], 0)

    def test_user_workout_history(self):
        """用户训练历史"""
        data = call_ok("adminUsers", {
            "action": "workoutHistory", "token": self.token,
            "userId": self.test_user["_id"]
        })
        self.assertIn("items", data)
        self.assertIn("total", data)

    def test_user_body_metrics(self):
        """用户体测历史"""
        data = call_ok("adminUsers", {
            "action": "bodyMetrics", "token": self.token,
            "userId": self.test_user["_id"]
        })
        self.assertIn("current", data)
        self.assertIn("history", data)
        self.assertGreaterEqual(len(data["history"]), 1)

    def test_user_personal_records(self):
        """用户个人记录"""
        data = call_ok("adminUsers", {
            "action": "personalRecords", "token": self.token,
            "userId": self.test_user["_id"]
        })
        # 可能空，但不应报错
        self.assertIsNotNone(data)

    def test_no_auth(self):
        """无token应被拒绝"""
        resp = call("adminUsers", {"action": "list"})
        self.assertNotEqual(resp["code"], 0)


class TestAdminStats(unittest.TestCase):
    """adminStats 云函数测试"""

    def setUp(self):
        self.token = admin_token()

    def test_overview(self):
        """总览统计"""
        data = call_ok("adminStats", {"action": "overview", "token": self.token})
        self.assertIn("totalUsers", data)
        self.assertIn("totalWorkouts", data)
        self.assertIn("totalExercises", data)
        self.assertIn("totalPlans", data)
        self.assertIn("completedWorkouts", data)

    def test_workout_trends(self):
        """训练趋势"""
        data = call_ok("adminStats", {"action": "workoutTrends", "token": self.token, "days": 7})
        self.assertIn("trends", data)
        self.assertEqual(len(data["trends"]), 7)
        for t in data["trends"]:
            self.assertIn("date", t)
            self.assertIn("count", t)

    def test_workout_trends_custom_days(self):
        """自定义天数训练趋势"""
        data = call_ok("adminStats", {"action": "workoutTrends", "token": self.token, "days": 14})
        self.assertEqual(len(data["trends"]), 14)

    def test_user_growth(self):
        """用户增长"""
        data = call_ok("adminStats", {"action": "userGrowth", "token": self.token, "days": 7})
        self.assertIn("growth", data)
        self.assertEqual(len(data["growth"]), 7)
        for g in data["growth"]:
            self.assertIn("newUsers", g)
            self.assertIn("totalUsers", g)

    def test_exercise_usage(self):
        """动作使用排行"""
        data = call_ok("adminStats", {"action": "exerciseUsage", "token": self.token})
        self.assertIn("usage", data)
        self.assertIn("total", data)

    def test_popular_categories(self):
        """热门分类"""
        data = call_ok("adminStats", {"action": "popularCategories", "token": self.token})
        self.assertIn("categories", data)

    def test_export_users(self):
        """导出用户数据"""
        data = call_ok("adminStats", {"action": "export", "token": self.token, "type": "users"})
        self.assertEqual(data["type"], "users")
        self.assertIn("data", data)
        self.assertIn("count", data)

    def test_export_workouts(self):
        """导出训练数据"""
        data = call_ok("adminStats", {"action": "export", "token": self.token, "type": "workouts"})
        self.assertEqual(data["type"], "workouts")

    def test_export_exercises(self):
        """导出动作数据"""
        data = call_ok("adminStats", {"action": "export", "token": self.token, "type": "exercises"})
        self.assertEqual(data["type"], "exercises")

    def test_export_invalid_type(self):
        """无效导出类型应失败"""
        resp = call("adminStats", {"action": "export", "token": self.token, "type": "invalid"})
        self.assertNotEqual(resp["code"], 0)

    def test_no_auth(self):
        """无token应被拒绝"""
        resp = call("adminStats", {"action": "overview"})
        self.assertNotEqual(resp["code"], 0)


class TestAdminSeed(unittest.TestCase):
    """adminSeed 云函数测试"""

    def setUp(self):
        self.token = admin_token()

    def test_import_seed(self):
        """导入种子数据"""
        data = call_ok("adminSeed", {
            "action": "import", "token": self.token, "count": 5
        })
        self.assertEqual(data["imported"], 5)

    def test_import_default_count(self):
        """默认导入数量"""
        data = call_ok("adminSeed", {"action": "import", "token": self.token})
        self.assertGreater(data["imported"], 0)

    def test_import_with_categories(self):
        """指定分类导入"""
        data = call_ok("adminSeed", {
            "action": "import", "token": self.token,
            "count": 3, "categories": ["chest", "back"]
        })
        self.assertEqual(data["imported"], 3)

    def test_clear_seed(self):
        """清除种子数据"""
        # 先导入
        call_ok("adminSeed", {"action": "import", "token": self.token, "count": 3})
        # 清除
        data = call_ok("adminSeed", {"action": "clear", "token": self.token})
        self.assertIn("removed", data)

    def test_seed_stats(self):
        """种子数据统计"""
        data = call_ok("adminSeed", {"action": "stats", "token": self.token})
        self.assertIn("totalExercises", data)
        self.assertIn("seedExercises", data)
        self.assertIn("customExercises", data)

    def test_no_auth(self):
        """无token应被拒绝"""
        resp = call("adminSeed", {"action": "import"})
        self.assertNotEqual(resp["code"], 0)

    def test_unknown_action(self):
        """未知操作应报错"""
        resp = call("adminSeed", {"action": "invalid", "token": self.token})
        self.assertNotEqual(resp["code"], 0)


# ══════════════════════════════════
# ── 跨函数集成测试 ──
# ══════════════════════════════════


class TestCrossFunctionIntegration(unittest.TestCase):
    """跨云函数集成测试"""

    def test_login_then_workout(self):
        """登录 -> 训练 -> 查看历史的完整流程"""
        user = call_ok("login")
        # 开始训练
        started = call_ok("saveWorkout", {
            "action": "start", "planName": "集成测试训练",
            "exercises": [{"exerciseId": "ex_001", "name": "卧推",
                           "sets": [{"weight": 70, "reps": 8}]}]
        })
        # 完成训练
        call_ok("saveWorkout", {
            "action": "complete", "workoutId": started["_id"], "duration": 3600
        })
        # 查看历史
        history = call_ok("saveWorkout", {"action": "history"})
        self.assertGreater(history["total"], 0)

    def test_admin_create_exercise_then_user_sees(self):
        """管理员创建动作 -> 用户端可见"""
        token = admin_token()
        created = call_ok("adminExercises", {
            "action": "create", "token": token,
            "name": "集成测试动作", "category": "chest",
            "difficulty": "beginner"
        })
        # 用户端搜索
        data = call_ok("getExercises", {"keyword": "集成测试动作"})
        found = any(e["_id"] == created["_id"] for e in data["items"])
        self.assertTrue(found)

    def test_admin_seed_then_stats(self):
        """管理员导入种子 -> 统计更新"""
        token = admin_token()
        call_ok("adminSeed", {"action": "import", "token": token, "count": 5})
        stats = call_ok("adminSeed", {"action": "stats", "token": token})
        self.assertGreaterEqual(stats["seedExercises"], 5)

    def test_admin_assign_plan_user_sees(self):
        """管理员分配计划 -> 用户端可见"""
        token = admin_token()
        # 先登录获取用户ID
        user = call_ok("login")
        user_id = user["_id"]
        # 分配计划
        call_ok("adminPlans", {
            "action": "assign", "token": token,
            "planId": "plan_001", "userIds": [user_id]
        })
        # 用户端查看计划
        data = call_ok("getPlans", {"action": "list", "userInfo": {"openId": user_id}})
        plan_ids = [p["_id"] for p in data["items"]]
        self.assertIn("plan_001", plan_ids)


if __name__ == "__main__":
    unittest.main()
