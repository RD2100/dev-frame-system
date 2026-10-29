"""FitTrack 模拟云函数服务器

模拟微信云开发后端，用于离线测试。
覆盖全部12个云函数: login / getExercises / getPlans / saveWorkout / planTemplates / seedExercises
+ adminAuth / adminExercises / adminPlans / adminUsers / adminStats / adminSeed
"""

import json
import time
import random
import hashlib
import base64
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

PORT = 8765  # Same port as demo mock server

# ── 种子数据 ──

CATEGORIES = ["chest", "back", "shoulder", "arm", "leg", "core", "cardio", "stretch"]
DIFFICULTIES = ["beginner", "intermediate", "advanced"]
EQUIPMENTS = ["barbell", "dumbbell", "machine", "cable", "bodyweight", "kettlebell", "band"]

SAMPLE_EXERCISES = [
    {"_id": "ex_001", "name": "杠铃卧推", "category": "chest", "difficulty": "intermediate",
     "equipment": "barbell", "muscleGroups": ["胸大肌", "肱三头肌"], "status": "active"},
    {"_id": "ex_002", "name": "哑铃飞鸟", "category": "chest", "difficulty": "beginner",
     "equipment": "dumbbell", "muscleGroups": ["胸大肌"], "status": "active"},
    {"_id": "ex_003", "name": "引体向上", "category": "back", "difficulty": "intermediate",
     "equipment": "bodyweight", "muscleGroups": ["背阔肌", "肱二头肌"], "status": "active"},
    {"_id": "ex_004", "name": "杠铃深蹲", "category": "leg", "difficulty": "advanced",
     "equipment": "barbell", "muscleGroups": ["股四头肌", "臀大肌"], "status": "active"},
    {"_id": "ex_005", "name": "哑铃弯举", "category": "arm", "difficulty": "beginner",
     "equipment": "dumbbell", "muscleGroups": ["肱二头肌"], "status": "active"},
    {"_id": "ex_006", "name": "哑铃侧平举", "category": "shoulder", "difficulty": "beginner",
     "equipment": "dumbbell", "muscleGroups": ["三角肌中束"], "status": "active"},
    {"_id": "ex_007", "name": "平板支撑", "category": "core", "difficulty": "beginner",
     "equipment": "bodyweight", "muscleGroups": ["腹直肌", "腹横肌"], "status": "active"},
    {"_id": "ex_008", "name": "跑步", "category": "cardio", "difficulty": "beginner",
     "equipment": "other", "muscleGroups": ["心肺系统"], "status": "active"},
    {"_id": "ex_009", "name": "杠铃硬拉", "category": "back", "difficulty": "advanced",
     "equipment": "barbell", "muscleGroups": ["竖脊肌", "臀大肌"], "status": "active"},
    {"_id": "ex_010", "name": "绳索下拉", "category": "arm", "difficulty": "intermediate",
     "equipment": "cable", "muscleGroups": ["肱三头肌"], "status": "inactive"},
    {"_id": "ex_011", "name": "腿举", "category": "leg", "difficulty": "intermediate",
     "equipment": "machine", "muscleGroups": ["股四头肌"], "status": "active"},
    {"_id": "ex_012", "name": "坐姿划船", "category": "back", "difficulty": "intermediate",
     "equipment": "cable", "muscleGroups": ["背阔肌", "菱形肌"], "status": "active"},
]

SAMPLE_PLANS = [
    {"_id": "plan_001", "name": "推拉腿分化", "goal": "hypertrophy", "frequency": 6,
     "days": [{"day": 1, "name": "推日", "exercises": ["ex_001", "ex_002", "ex_006"]},
              {"day": 2, "name": "拉日", "exercises": ["ex_003", "ex_009", "ex_012"]},
              {"day": 3, "name": "腿日", "exercises": ["ex_004", "ex_011"]}],
     "isActive": True, "isTemplate": True, "createdBy": "admin_001",
     "assignedTo": [], "createdAt": time.time() - 86400 * 30},
    {"_id": "plan_002", "name": "全身训练", "goal": "general", "frequency": 3,
     "days": [{"day": 1, "name": "全身A", "exercises": ["ex_001", "ex_003", "ex_004", "ex_005"]}],
     "isActive": False, "isTemplate": False, "createdBy": "mock_openid_1001",
     "assignedTo": [], "createdAt": time.time() - 86400 * 15},
]

# ── 运行时状态 ──

USERS = {}
WORKOUTS = []
ADMINS = {
    "admin_001": {
        "_id": "admin_001", "username": "admin",
        "password": hashlib.sha256("admin123".encode()).hexdigest(),
        "role": "super_admin", "createdAt": time.time() - 86400 * 90
    }
}
ADMIN_TOKENS = {}  # token -> admin_id
EXERCISES_DB = list(SAMPLE_EXERCISES)  # 可增删改的副本
PLANS_DB = list(SAMPLE_PLANS)
PERSONAL_RECORDS = {}  # openid -> { exerciseId -> { weight, reps, volume, date } }
SEED_STATS = {"imported": 85, "lastImport": time.time() - 86400 * 7}


class FitTrackHandler(BaseHTTPRequestHandler):
    """处理所有 /api/{functionName} 请求"""

    def log_message(self, fmt, *args):
        pass  # 静默日志，避免测试噪音

    # ── 通用响应 ──

    def _json(self, code, data=None, msg="ok"):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        body = {"code": code, "msg": msg}
        if data is not None:
            body["data"] = data
        self.wfile.write(json.dumps(body, ensure_ascii=False).encode())

    def _ok(self, data=None, msg="ok"):
        self._json(0, data, msg)

    def _err(self, msg="error", code=-1):
        self._json(code, None, msg)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def _require_auth(self, body):
        """验证管理员token，返回admin_id或None"""
        token = body.get("token", "")
        admin_id = ADMIN_TOKENS.get(token)
        if not admin_id:
            return None
        return admin_id

    def _get_openid(self, body):
        """从请求中获取openid，默认mock_openid_1001"""
        return body.get("userInfo", {}).get("openId", "mock_openid_1001")

    # ── 路由 ──

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            self._err("invalid path")
            return
        fn = path[5:]  # 去掉 /api/
        body = self._read_body()
        handler = getattr(self, f"_fn_{fn}", None)
        if handler:
            try:
                handler(body)
            except Exception as e:
                self._err(f"server error: {e}")
        else:
            self._err(f"unknown function: {fn}")

    # ══════════════════════════════════
    # ── 用户端云函数 ──
    # ══════════════════════════════════

    # ── login ──

    def _fn_login(self, body):
        openid = f"mock_openid_{random.randint(1000, 9999)}"
        if openid not in USERS:
            USERS[openid] = {
                "_id": openid, "nickname": f"用户{openid[-4:]}",
                "avatarUrl": "", "createdAt": time.time(),
                "bodyMetrics": {"height": 175, "weight": 70},
                "level": 1, "totalWorkouts": 0
            }
        self._ok(USERS[openid])

    # ── getExercises ──

    def _fn_getExercises(self, body):
        keyword = body.get("keyword", "").strip()
        category = body.get("category", "").strip()
        page = max(1, body.get("page", 1))
        pageSize = min(50, max(1, body.get("pageSize", 20)))
        difficulty = body.get("difficulty", "").strip()
        equipment = body.get("equipment", "").strip()

        results = list(EXERCISES_DB)
        # 只返回active状态，除非指定includeInactive
        if not body.get("includeInactive"):
            results = [e for e in results if e.get("status") == "active"]
        if keyword:
            results = [e for e in results if keyword.lower() in e["name"].lower()]
        if category:
            results = [e for e in results if e["category"] == category]
        if difficulty:
            results = [e for e in results if e["difficulty"] == difficulty]
        if equipment:
            results = [e for e in results if e["equipment"] == equipment]

        total = len(results)
        start = (page - 1) * pageSize
        items = results[start:start + pageSize]
        self._ok({"items": items, "total": total, "page": page, "pageSize": pageSize})

    # ── getPlans ──

    def _fn_getPlans(self, body):
        action = body.get("action", "list")
        openid = self._get_openid(body)

        if action == "list":
            goal = body.get("goal", "").strip()
            page = max(1, body.get("page", 1))
            pageSize = min(50, max(1, body.get("pageSize", 20)))
            results = list(PLANS_DB)
            # 用户只能看到自己的或模板或被分配的
            results = [p for p in results
                       if p.get("isTemplate")
                       or p.get("createdBy") == openid
                       or (p.get("assignedTo") and openid in p.get("assignedTo", []))]
            if goal:
                results = [p for p in results if p.get("goal") == goal]
            total = len(results)
            start = (page - 1) * pageSize
            items = results[start:start + pageSize]
            self._ok({"items": items, "total": total, "page": page, "pageSize": pageSize})
        elif action == "detail":
            plan_id = body.get("planId", "")
            plan = next((p for p in PLANS_DB if p["_id"] == plan_id), None)
            if plan:
                self._ok(plan)
            else:
                self._err("plan not found", 404)
        elif action == "create":
            name = body.get("name", "").strip()
            if not name:
                self._err("plan name required")
                return
            new_id = f"plan_{len(PLANS_DB) + 1:03d}"
            new_plan = {
                "_id": new_id, "name": name, "goal": body.get("goal", "general"),
                "frequency": body.get("frequency", 3), "days": body.get("days", []),
                "isActive": True, "isTemplate": False, "createdBy": openid,
                "assignedTo": [], "createdAt": time.time()
            }
            PLANS_DB.append(new_plan)
            self._ok(new_plan)
        elif action == "update":
            plan_id = body.get("planId", "")
            plan = next((p for p in PLANS_DB if p["_id"] == plan_id), None)
            if not plan:
                self._err("plan not found", 404)
                return
            for key in ["name", "goal", "frequency", "days", "isActive"]:
                if key in body:
                    plan[key] = body[key]
            self._ok(plan)
        elif action == "delete":
            plan_id = body.get("planId", "")
            idx = next((i for i, p in enumerate(PLANS_DB) if p["_id"] == plan_id), -1)
            if idx < 0:
                self._err("plan not found", 404)
                return
            PLANS_DB.pop(idx)
            self._ok({"deleted": plan_id})
        else:
            self._err(f"unknown action: {action}")

    # ── saveWorkout ──

    def _fn_saveWorkout(self, body):
        action = body.get("action", "save")
        openid = self._get_openid(body)

        # 确保用户存在（saveWorkout可能由未login的用户触发）
        if openid not in USERS:
            USERS[openid] = {
                "_id": openid, "nickname": f"用户{openid[-4:]}",
                "avatarUrl": "", "createdAt": time.time(),
                "bodyMetrics": {"height": 175, "weight": 70},
                "level": 1, "totalWorkouts": 0
            }

        if action == "save" or action == "start":
            wid = f"wk_{int(time.time())}_{random.randint(100, 999)}"
            workout = {
                "_id": wid, "userId": openid,
                "planId": body.get("planId", ""), "planName": body.get("planName", ""),
                "dayIndex": body.get("dayIndex", 0),
                "exercises": body.get("exercises", []),
                "status": "in_progress" if action == "start" else body.get("status", "completed"),
                "startTime": time.time(),
                "endTime": None, "duration": 0,
                "totalSets": 0, "totalVolume": 0,
                "notes": body.get("notes", ""),
                "createdAt": time.time()
            }
            # save且包含exercises时计算总量
            if action == "save" and workout["exercises"]:
                total_sets = 0
                total_volume = 0
                for ex in workout["exercises"]:
                    for s in ex.get("sets", []):
                        total_sets += 1
                        total_volume += s.get("weight", 0) * s.get("reps", 0)
                workout["totalSets"] = total_sets
                workout["totalVolume"] = total_volume
            WORKOUTS.append(workout)
            if openid in USERS:
                USERS[openid]["totalWorkouts"] = USERS[openid].get("totalWorkouts", 0) + 1
            self._ok(workout)

        elif action == "updateSet":
            wid = body.get("workoutId", "")
            workout = next((w for w in WORKOUTS if w["_id"] == wid), None)
            if not workout:
                self._err("workout not found", 404)
                return
            ex_idx = body.get("exerciseIndex", -1)
            set_idx = body.get("setIndex", -1)
            setData = body.get("setData", {})
            if 0 <= ex_idx < len(workout["exercises"]):
                sets = workout["exercises"][ex_idx].get("sets", [])
                if 0 <= set_idx < len(sets):
                    sets[set_idx].update(setData)
                else:
                    sets.append(setData)
            self._ok(workout)

        elif action == "complete":
            wid = body.get("workoutId", "")
            workout = next((w for w in WORKOUTS if w["_id"] == wid), None)
            if not workout:
                self._err("workout not found", 404)
                return
            workout["status"] = "completed"
            workout["endTime"] = time.time()
            workout["duration"] = body.get("duration", workout["endTime"] - workout.get("startTime", workout["endTime"]))
            # 重新计算总量
            total_sets = 0
            total_volume = 0
            for ex in workout.get("exercises", []):
                for s in ex.get("sets", []):
                    total_sets += 1
                    total_volume += s.get("weight", 0) * s.get("reps", 0)
            workout["totalSets"] = total_sets
            workout["totalVolume"] = total_volume
            # 自动更新个人记录
            self._update_personal_records(openid, workout)
            self._ok(workout)

        elif action == "history":
            page = max(1, body.get("page", 1))
            pageSize = min(50, max(1, body.get("pageSize", 20)))
            status = body.get("status", "")
            user_workouts = [w for w in WORKOUTS if w["userId"] == openid]
            if status:
                user_workouts = [w for w in user_workouts if w["status"] == status]
            user_workouts.sort(key=lambda w: w.get("createdAt", 0), reverse=True)
            total = len(user_workouts)
            start = (page - 1) * pageSize
            items = user_workouts[start:start + pageSize]
            self._ok({"items": items, "total": total, "page": page, "pageSize": pageSize})

        elif action == "detail":
            wid = body.get("workoutId", "")
            workout = next((w for w in WORKOUTS if w["_id"] == wid), None)
            if workout:
                self._ok(workout)
            else:
                self._err("workout not found", 404)

        elif action == "updateProfile":
            if openid not in USERS:
                self._err("user not found", 404)
                return
            profile_updates = body.get("profile", {})
            for key in ["nickname", "avatarUrl"]:
                if key in profile_updates:
                    USERS[openid][key] = profile_updates[key]
            if "bodyMetrics" in profile_updates:
                USERS[openid].setdefault("bodyMetrics", {}).update(profile_updates["bodyMetrics"])
            self._ok(USERS[openid])

        elif action == "personalRecords":
            records = PERSONAL_RECORDS.get(openid, {})
            self._ok(records)

        else:
            self._err(f"unknown action: {action}")

    def _update_personal_records(self, openid, workout):
        """自动更新个人记录（完成训练时调用）"""
        if openid not in PERSONAL_RECORDS:
            PERSONAL_RECORDS[openid] = {}
        records = PERSONAL_RECORDS[openid]
        for ex in workout.get("exercises", []):
            ex_id = ex.get("exerciseId", "")
            if not ex_id:
                continue
            for s in ex.get("sets", []):
                weight = s.get("weight", 0)
                reps = s.get("reps", 0)
                volume = weight * reps
                if ex_id not in records:
                    records[ex_id] = {"weight": 0, "reps": 0, "volume": 0, "date": 0}
                if weight > records[ex_id]["weight"]:
                    records[ex_id]["weight"] = weight
                    records[ex_id]["date"] = time.time()
                if reps > records[ex_id]["reps"]:
                    records[ex_id]["reps"] = reps
                if volume > records[ex_id]["volume"]:
                    records[ex_id]["volume"] = volume

    # ── planTemplates ──

    def _fn_planTemplates(self, body):
        templates = [p for p in PLANS_DB if p.get("isTemplate")]
        self._ok({"items": templates, "total": len(templates)})

    # ── seedExercises (用户端) ──

    def _fn_seedExercises(self, body):
        """用户端种子数据初始化"""
        action = body.get("action", "init")

        if action == "init":
            # 确保基础动作存在
            if not any(e.get("_id") == "ex_001" for e in EXERCISES_DB):
                EXERCISES_DB.extend(SAMPLE_EXERCISES)
            self._ok({"initialized": True, "count": len(SAMPLE_EXERCISES)})
        elif action == "status":
            active = len([e for e in EXERCISES_DB if e.get("status") == "active"])
            self._ok({"total": len(EXERCISES_DB), "active": active})
        else:
            self._err(f"unknown action: {action}")

    # ══════════════════════════════════
    # ── 管理端云函数 ──
    # ══════════════════════════════════

    # ── adminAuth ──

    def _fn_adminAuth(self, body):
        action = body.get("action", "login")

        if action == "login":
            username = body.get("username", "").strip()
            password = body.get("password", "").strip()
            if not username or not password:
                self._err("用户名和密码不能为空", 1001)
                return
            pw_hash = hashlib.sha256(password.encode()).hexdigest()
            admin = next((a for a in ADMINS.values()
                          if a["username"] == username and a["password"] == pw_hash), None)
            if not admin:
                self._err("用户名或密码错误", 1002)
                return
            token = base64.b64encode(f"{admin['_id']}:{int(time.time())}".encode()).decode()
            ADMIN_TOKENS[token] = admin["_id"]
            self._ok({"token": token, "admin": {
                "_id": admin["_id"], "username": admin["username"], "role": admin["role"]}})

        elif action == "verify":
            token = body.get("token", "")
            admin_id = ADMIN_TOKENS.get(token)
            if not admin_id or admin_id not in ADMINS:
                self._err("token无效或已过期", 1003)
                return
            admin = ADMINS[admin_id]
            self._ok({"valid": True, "admin": {
                "_id": admin["_id"], "username": admin["username"], "role": admin["role"]}})

        elif action == "changePassword":
            admin_id = self._require_auth(body)
            if not admin_id:
                self._err("未授权", 1003)
                return
            old_pw = body.get("oldPassword", "")
            new_pw = body.get("newPassword", "")
            if not old_pw or not new_pw:
                self._err("旧密码和新密码不能为空", 1001)
                return
            old_hash = hashlib.sha256(old_pw.encode()).hexdigest()
            if ADMINS[admin_id]["password"] != old_hash:
                self._err("旧密码错误", 1004)
                return
            if len(new_pw) < 6:
                self._err("新密码至少6位", 1005)
                return
            ADMINS[admin_id]["password"] = hashlib.sha256(new_pw.encode()).hexdigest()
            self._ok({"changed": True})

        elif action == "createAdmin":
            admin_id = self._require_auth(body)
            if not admin_id:
                self._err("未授权", 1003)
                return
            if ADMINS[admin_id]["role"] != "super_admin":
                self._err("权限不足，仅super_admin可创建管理员", 1006)
                return
            username = body.get("username", "").strip()
            password = body.get("password", "").strip()
            role = body.get("role", "admin")
            if not username or not password:
                self._err("用户名和密码不能为空", 1001)
                return
            if len(password) < 6:
                self._err("密码至少6位", 1005)
                return
            if any(a["username"] == username for a in ADMINS.values()):
                self._err("用户名已存在", 1007)
                return
            new_id = f"admin_{len(ADMINS) + 1:03d}"
            ADMINS[new_id] = {
                "_id": new_id, "username": username,
                "password": hashlib.sha256(password.encode()).hexdigest(),
                "role": role, "createdAt": time.time()
            }
            self._ok({"_id": new_id, "username": username, "role": role})

        else:
            self._err(f"unknown action: {action}")

    # ── adminExercises ──

    def _fn_adminExercises(self, body):
        action = body.get("action", "list")
        admin_id = self._require_auth(body)
        if not admin_id:
            self._err("未授权", 1003)
            return

        if action == "list":
            page = max(1, body.get("page", 1))
            pageSize = min(50, max(1, body.get("pageSize", 20)))
            category = body.get("category", "")
            status = body.get("status", "")
            keyword = body.get("keyword", "").strip()
            results = list(EXERCISES_DB)
            if category:
                results = [e for e in results if e["category"] == category]
            if status:
                results = [e for e in results if e.get("status") == status]
            if keyword:
                results = [e for e in results if keyword.lower() in e["name"].lower()]
            total = len(results)
            start = (page - 1) * pageSize
            items = results[start:start + pageSize]
            self._ok({"items": items, "total": total, "page": page, "pageSize": pageSize})

        elif action == "detail":
            ex_id = body.get("exerciseId", "")
            ex = next((e for e in EXERCISES_DB if e["_id"] == ex_id), None)
            if ex:
                self._ok(ex)
            else:
                self._err("exercise not found", 404)

        elif action == "create":
            name = body.get("name", "").strip()
            category = body.get("category", "").strip()
            if not name or not category:
                self._err("name和category必填", 1001)
                return
            new_id = f"ex_{len(EXERCISES_DB) + 1:03d}"
            new_ex = {
                "_id": new_id, "name": name, "category": category,
                "difficulty": body.get("difficulty", "beginner"),
                "equipment": body.get("equipment", ""),
                "muscleGroups": body.get("muscleGroups", []),
                "description": body.get("description", ""),
                "status": body.get("status", "active"),
                "createdBy": admin_id, "createdAt": time.time()
            }
            EXERCISES_DB.append(new_ex)
            self._ok(new_ex)

        elif action == "update":
            ex_id = body.get("exerciseId", "")
            ex = next((e for e in EXERCISES_DB if e["_id"] == ex_id), None)
            if not ex:
                self._err("exercise not found", 404)
                return
            for key in ["name", "category", "difficulty", "equipment", "muscleGroups", "description", "status"]:
                if key in body:
                    ex[key] = body[key]
            ex["updatedBy"] = admin_id
            ex["updatedAt"] = time.time()
            self._ok(ex)

        elif action == "delete":
            ex_id = body.get("exerciseId", "")
            idx = next((i for i, e in enumerate(EXERCISES_DB) if e["_id"] == ex_id), -1)
            if idx < 0:
                self._err("exercise not found", 404)
                return
            EXERCISES_DB.pop(idx)
            self._ok({"deleted": ex_id})

        elif action == "batchStatus":
            ids = body.get("exerciseIds", [])
            new_status = body.get("status", "active")
            if not ids:
                self._err("exerciseIds不能为空", 1001)
                return
            updated = 0
            for ex in EXERCISES_DB:
                if ex["_id"] in ids:
                    ex["status"] = new_status
                    updated += 1
            self._ok({"updated": updated})

        elif action == "stats":
            total = len(EXERCISES_DB)
            active = len([e for e in EXERCISES_DB if e.get("status") == "active"])
            by_category = {}
            by_difficulty = {}
            for e in EXERCISES_DB:
                by_category[e["category"]] = by_category.get(e["category"], 0) + 1
                by_difficulty[e["difficulty"]] = by_difficulty.get(e["difficulty"], 0) + 1
            self._ok({"total": total, "active": active, "inactive": total - active,
                      "byCategory": by_category, "byDifficulty": by_difficulty})

        else:
            self._err(f"unknown action: {action}")

    # ── adminPlans ──

    def _fn_adminPlans(self, body):
        action = body.get("action", "list")
        admin_id = self._require_auth(body)
        if not admin_id:
            self._err("未授权", 1003)
            return

        if action == "list":
            page = max(1, body.get("page", 1))
            pageSize = min(50, max(1, body.get("pageSize", 20)))
            isTemplate = body.get("isTemplate")
            goal = body.get("goal", "")
            results = list(PLANS_DB)
            if isTemplate is not None:
                results = [p for p in results if p.get("isTemplate") == isTemplate]
            if goal:
                results = [p for p in results if p.get("goal") == goal]
            total = len(results)
            start = (page - 1) * pageSize
            items = results[start:start + pageSize]
            self._ok({"items": items, "total": total, "page": page, "pageSize": pageSize})

        elif action == "detail":
            plan_id = body.get("planId", "")
            plan = next((p for p in PLANS_DB if p["_id"] == plan_id), None)
            if plan:
                self._ok(plan)
            else:
                self._err("plan not found", 404)

        elif action == "create":
            name = body.get("name", "").strip()
            if not name:
                self._err("plan name required", 1001)
                return
            new_id = f"plan_{len(PLANS_DB) + 1:03d}"
            new_plan = {
                "_id": new_id, "name": name, "goal": body.get("goal", "general"),
                "frequency": body.get("frequency", 3), "days": body.get("days", []),
                "isActive": body.get("isActive", True),
                "isTemplate": body.get("isTemplate", False),
                "createdBy": admin_id, "assignedTo": [],
                "createdAt": time.time()
            }
            PLANS_DB.append(new_plan)
            self._ok(new_plan)

        elif action == "update":
            plan_id = body.get("planId", "")
            plan = next((p for p in PLANS_DB if p["_id"] == plan_id), None)
            if not plan:
                self._err("plan not found", 404)
                return
            for key in ["name", "goal", "frequency", "days", "isActive", "isTemplate"]:
                if key in body:
                    plan[key] = body[key]
            plan["updatedBy"] = admin_id
            plan["updatedAt"] = time.time()
            self._ok(plan)

        elif action == "delete":
            plan_id = body.get("planId", "")
            idx = next((i for i, p in enumerate(PLANS_DB) if p["_id"] == plan_id), -1)
            if idx < 0:
                self._err("plan not found", 404)
                return
            PLANS_DB.pop(idx)
            self._ok({"deleted": plan_id})

        elif action == "setTemplate":
            plan_id = body.get("planId", "")
            isTemplate = body.get("isTemplate", True)
            plan = next((p for p in PLANS_DB if p["_id"] == plan_id), None)
            if not plan:
                self._err("plan not found", 404)
                return
            plan["isTemplate"] = isTemplate
            self._ok(plan)

        elif action == "assign":
            plan_id = body.get("planId", "")
            user_ids = body.get("userIds", [])
            plan = next((p for p in PLANS_DB if p["_id"] == plan_id), None)
            if not plan:
                self._err("plan not found", 404)
                return
            if not user_ids:
                self._err("userIds不能为空", 1001)
                return
            current = plan.get("assignedTo", [])
            for uid in user_ids:
                if uid not in current:
                    current.append(uid)
            plan["assignedTo"] = current
            self._ok(plan)

        elif action == "stats":
            total = len(PLANS_DB)
            templates = len([p for p in PLANS_DB if p.get("isTemplate")])
            active = len([p for p in PLANS_DB if p.get("isActive")])
            by_goal = {}
            for p in PLANS_DB:
                by_goal[p.get("goal", "general")] = by_goal.get(p.get("goal", "general"), 0) + 1
            self._ok({"total": total, "templates": templates, "active": active, "byGoal": by_goal})

        else:
            self._err(f"unknown action: {action}")

    # ── adminUsers ──

    def _fn_adminUsers(self, body):
        action = body.get("action", "list")
        admin_id = self._require_auth(body)
        if not admin_id:
            self._err("未授权", 1003)
            return

        if action == "list":
            page = max(1, body.get("page", 1))
            pageSize = min(50, max(1, body.get("pageSize", 20)))
            keyword = body.get("keyword", "").strip()
            results = list(USERS.values())
            if keyword:
                results = [u for u in results if keyword in u.get("nickname", "")]
            total = len(results)
            start = (page - 1) * pageSize
            items = results[start:start + pageSize]
            self._ok({"items": items, "total": total, "page": page, "pageSize": pageSize})

        elif action == "detail":
            user_id = body.get("userId", "")
            user = USERS.get(user_id)
            if user:
                # 附带训练历史摘要
                user_workouts = [w for w in WORKOUTS if w["userId"] == user_id]
                user_data = dict(user)
                user_data["workoutSummary"] = {
                    "totalWorkouts": len(user_workouts),
                    "completedWorkouts": len([w for w in user_workouts if w["status"] == "completed"]),
                    "totalVolume": sum(w.get("totalVolume", 0) for w in user_workouts),
                    "totalDuration": sum(w.get("duration", 0) for w in user_workouts)
                }
                self._ok(user_data)
            else:
                self._err("user not found", 404)

        elif action == "update":
            user_id = body.get("userId", "")
            user = USERS.get(user_id)
            if not user:
                self._err("user not found", 404)
                return
            for key in ["nickname", "avatarUrl", "level"]:
                if key in body:
                    user[key] = body[key]
            if "bodyMetrics" in body:
                user.setdefault("bodyMetrics", {}).update(body["bodyMetrics"])
            self._ok(user)

        elif action == "delete":
            user_id = body.get("userId", "")
            if user_id not in USERS:
                self._err("user not found", 404)
                return
            del USERS[user_id]
            self._ok({"deleted": user_id})

        elif action == "workoutHistory":
            user_id = body.get("userId", "")
            page = max(1, body.get("page", 1))
            pageSize = min(50, max(1, body.get("pageSize", 20)))
            user_workouts = [w for w in WORKOUTS if w["userId"] == user_id]
            user_workouts.sort(key=lambda w: w.get("createdAt", 0), reverse=True)
            total = len(user_workouts)
            start = (page - 1) * pageSize
            items = user_workouts[start:start + pageSize]
            self._ok({"items": items, "total": total, "page": page, "pageSize": pageSize})

        elif action == "bodyMetrics":
            user_id = body.get("userId", "")
            user = USERS.get(user_id)
            if not user:
                self._err("user not found", 404)
                return
            metrics = user.get("bodyMetrics", {})
            history = [
                {"date": time.time() - 86400 * 30, "weight": metrics.get("weight", 70) + 2,
                 "height": metrics.get("height", 175)},
                {"date": time.time() - 86400 * 15, "weight": metrics.get("weight", 70) + 1,
                 "height": metrics.get("height", 175)},
                {"date": time.time(), "weight": metrics.get("weight", 70),
                 "height": metrics.get("height", 175)},
            ]
            self._ok({"current": metrics, "history": history})

        elif action == "personalRecords":
            user_id = body.get("userId", "")
            records = PERSONAL_RECORDS.get(user_id, {})
            self._ok(records)

        else:
            self._err(f"unknown action: {action}")

    # ── adminStats ──

    def _fn_adminStats(self, body):
        action = body.get("action", "overview")
        admin_id = self._require_auth(body)
        if not admin_id:
            self._err("未授权", 1003)
            return

        if action == "overview":
            self._ok({
                "totalUsers": len(USERS),
                "totalWorkouts": len(WORKOUTS),
                "totalExercises": len(EXERCISES_DB),
                "totalPlans": len(PLANS_DB),
                "activeUsers": max(1, len(USERS) // 2),
                "completedWorkouts": len([w for w in WORKOUTS if w.get("status") == "completed"]),
                "avgWorkoutsPerUser": round(len(WORKOUTS) / max(1, len(USERS)), 1),
                "totalVolume": sum(w.get("totalVolume", 0) for w in WORKOUTS)
            })

        elif action == "workoutTrends":
            days = body.get("days", 7)
            trends = []
            for i in range(days):
                day_ts = time.time() - 86400 * (days - 1 - i)
                day_count = random.randint(1, 10)
                trends.append({"date": day_ts, "count": day_count,
                               "volume": day_count * random.randint(500, 2000)})
            self._ok({"trends": trends, "days": days})

        elif action == "userGrowth":
            days = body.get("days", 7)
            growth = []
            base = max(0, len(USERS) - days)
            for i in range(days):
                day_ts = time.time() - 86400 * (days - 1 - i)
                new_users = random.randint(0, 5)
                base += new_users
                growth.append({"date": day_ts, "newUsers": new_users, "totalUsers": base})
            self._ok({"growth": growth, "days": days})

        elif action == "exerciseUsage":
            usage = {}
            for ex in EXERCISES_DB:
                usage[ex["_id"]] = {"name": ex["name"], "count": random.randint(0, 50)}
            top = sorted(usage.values(), key=lambda x: x["count"], reverse=True)
            self._ok({"usage": top[:20], "total": len(usage)})

        elif action == "popularCategories":
            categories = {}
            for ex in EXERCISES_DB:
                cat = ex["category"]
                categories[cat] = categories.get(cat, 0) + random.randint(1, 20)
            self._ok({"categories": categories})

        elif action == "export":
            export_type = body.get("type", "users")
            if export_type == "users":
                data = list(USERS.values())
            elif export_type == "workouts":
                data = WORKOUTS
            elif export_type == "exercises":
                data = EXERCISES_DB
            else:
                self._err(f"unknown export type: {export_type}", 1001)
                return
            self._ok({"type": export_type, "count": len(data), "data": data})

        else:
            self._err(f"unknown action: {action}")

    # ── adminSeed ──

    def _fn_adminSeed(self, body):
        action = body.get("action", "import")
        admin_id = self._require_auth(body)
        if not admin_id:
            self._err("未授权", 1003)
            return

        if action == "import":
            count = body.get("count", 30)
            categories = body.get("categories", CATEGORIES)
            imported = 0
            for i in range(count):
                cat = categories[i % len(categories)] if isinstance(categories, list) else random.choice(CATEGORIES)
                new_id = f"seed_{len(EXERCISES_DB) + 1:04d}"
                EXERCISES_DB.append({
                    "_id": new_id,
                    "name": f"种子动作_{cat}_{i + 1}",
                    "category": cat,
                    "difficulty": random.choice(DIFFICULTIES),
                    "equipment": random.choice(EQUIPMENTS),
                    "muscleGroups": [cat],
                    "status": "active",
                    "isSeed": True,
                    "createdBy": admin_id,
                    "createdAt": time.time()
                })
                imported += 1
            SEED_STATS["imported"] = imported
            SEED_STATS["lastImport"] = time.time()
            self._ok({"imported": imported})

        elif action == "clear":
            before = len(EXERCISES_DB)
            EXERCISES_DB[:] = [e for e in EXERCISES_DB if not e.get("isSeed")]
            removed = before - len(EXERCISES_DB)
            self._ok({"removed": removed})

        elif action == "stats":
            seed_count = len([e for e in EXERCISES_DB if e.get("isSeed")])
            self._ok({
                "totalExercises": len(EXERCISES_DB),
                "seedExercises": seed_count,
                "customExercises": len(EXERCISES_DB) - seed_count,
                "lastImport": SEED_STATS.get("lastImport"),
                "lastImportedCount": SEED_STATS.get("imported", 0)
            })

        else:
            self._err(f"unknown action: {action}")


# ── 启动 ──

# 兼容旧代码的别名
FitTrackMockHandler = FitTrackHandler


def start_server(port=PORT):
    """启动mock服务器（兼容run_tests.py调用）"""
    server = HTTPServer(("127.0.0.1", port), FitTrackHandler)
    print(f"[FitTrack Mock] http://127.0.0.1:{port}")
    return server


def run_server():
    server = HTTPServer(("127.0.0.1", PORT), FitTrackHandler)
    print(f"FitTrack mock server running on http://127.0.0.1:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
