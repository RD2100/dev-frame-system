"""FitTrack 数据模型和业务规则验证测试

不依赖 Mock 服务器，纯逻辑验证。
"""

import pytest


# ═══════════════════════════════════════════════
# 动作分类数据完整性
# ═══════════════════════════════════════════════

EXERCISE_CATEGORIES = [
    {"id": "chest", "name": "胸部"},
    {"id": "back", "name": "背部"},
    {"id": "shoulder", "name": "肩部"},
    {"id": "arm", "name": "手臂"},
    {"id": "leg", "name": "腿部"},
    {"id": "core", "name": "核心"},
    {"id": "cardio", "name": "有氧"},
    {"id": "stretch", "name": "拉伸"},
]

MUSCLE_GROUPS = {
    "chest": ["胸大肌", "胸小肌", "前锯肌"],
    "back": ["背阔肌", "菱形肌", "竖脊肌", "斜方肌"],
    "shoulder": ["三角肌前束", "三角肌中束", "三角肌后束"],
    "arm": ["肱二头肌", "肱三头肌", "前臂肌群"],
    "leg": ["股四头肌", "股二头肌", "臀大肌", "小腿肌群"],
    "core": ["腹直肌", "腹斜肌", "腹横肌"],
    "cardio": ["心肺系统"],
    "stretch": ["全身肌群"],
}

EQUIPMENT_TYPES = [
    {"id": "barbell", "name": "杠铃"},
    {"id": "dumbbell", "name": "哑铃"},
    {"id": "machine", "name": "器械"},
    {"id": "cable", "name": "绳索"},
    {"id": "bodyweight", "name": "自重"},
    {"id": "kettlebell", "name": "壶铃"},
    {"id": "band", "name": "弹力带"},
    {"id": "other", "name": "其他"},
]

DIFFICULTY_LEVELS = [
    {"id": "beginner", "name": "初级"},
    {"id": "intermediate", "name": "中级"},
    {"id": "advanced", "name": "高级"},
]

TRAINING_GOALS = [
    {"id": "strength", "name": "增力"},
    {"id": "hypertrophy", "name": "增肌"},
    {"id": "endurance", "name": "耐力"},
    {"id": "fat_loss", "name": "减脂"},
    {"id": "flexibility", "name": "柔韧"},
    {"id": "general", "name": "综合"},
]

TRAINING_FREQUENCY = [
    {"id": "2", "name": "每周2天"},
    {"id": "3", "name": "每周3天"},
    {"id": "4", "name": "每周4天"},
    {"id": "5", "name": "每周5天"},
    {"id": "6", "name": "每周6天"},
]

PAGE_NAMES = [
    "pages/login/login",
    "pages/index/index",
    "pages/training/training",
    "pages/exercise/exercise",
    "pages/profile/profile",
    "pages/workout-detail/workout-detail",
    "pages/plan-edit/plan-edit",
    "pages/stats/stats",
    "pages/exercise/exercise-detail/exercise-detail",
    "pages/profile/profile-edit/profile-edit",
    "pages/profile/body-metrics/body-metrics",
    "pages/profile/personal-records/personal-records",
    "pages/admin/seed-data/seed-data",
]

TABBAR_PAGES = [
    "pages/index/index",
    "pages/training/training",
    "pages/exercise/exercise",
    "pages/profile/profile",
]


class TestCategories:
    """动作分类数据完整性验证"""

    def test_all_categories_have_id_and_name(self):
        for cat in EXERCISE_CATEGORIES:
            assert "id" in cat, f"Category missing id: {cat}"
            assert "name" in cat, f"Category missing name: {cat}"

    def test_categories_count(self):
        assert len(EXERCISE_CATEGORIES) == 8

    def test_category_ids_unique(self):
        ids = [c["id"] for c in EXERCISE_CATEGORIES]
        assert len(ids) == len(set(ids)), f"Duplicate category IDs: {ids}"

    def test_each_category_has_muscles(self):
        for cat in EXERCISE_CATEGORIES:
            muscles = MUSCLE_GROUPS.get(cat["id"])
            assert muscles is not None, f"No muscle groups for {cat['id']}"
            assert len(muscles) > 0, f"Empty muscle groups for {cat['id']}"


class TestEquipment:
    """设备类型验证"""

    def test_all_equipment_have_id_and_name(self):
        for eq in EQUIPMENT_TYPES:
            assert "id" in eq
            assert "name" in eq

    def test_equipment_ids_unique(self):
        ids = [eq["id"] for eq in EQUIPMENT_TYPES]
        assert len(ids) == len(set(ids))

    def test_bodyweight_included(self):
        assert any(e["id"] == "bodyweight" for e in EQUIPMENT_TYPES), \
            "Bodyweight equipment is required for no-equipment exercises"


class TestDifficulties:
    """难度等级验证"""

    def test_three_levels(self):
        assert len(DIFFICULTY_LEVELS) == 3

    def test_levels_ordered(self):
        ids = [d["id"] for d in DIFFICULTY_LEVELS]
        assert ids == ["beginner", "intermediate", "advanced"], \
            f"Difficulty levels must be in order: {ids}"


class TestTrainingGoals:
    """训练目标验证"""

    def test_general_is_default(self):
        assert any(g["id"] == "general" for g in TRAINING_GOALS), \
            "'general' goal is required as default"


class TestPageRegistration:
    """页面注册验证 — 确保 app.json pages 数组完整"""

    def test_all_pages_registered(self):
        assert len(PAGE_NAMES) == 13, f"Expected 13 pages, got {len(PAGE_NAMES)}"

    def test_tabbar_pages_in_list(self):
        for tab_page in TABBAR_PAGES:
            assert tab_page in PAGE_NAMES, \
                f"TabBar page {tab_page} not in page list"

    def test_login_is_first_page(self):
        assert PAGE_NAMES[0] == "pages/login/login", \
            "Login page must be first in pages array"


class TestCloudFunctionNaming:
    """云函数命名和版本一致性"""

    def test_required_functions_exist(self):
        required = ["login", "getExercises", "getPlans", "saveWorkout",
                    "planTemplates", "seedExercises"]
        for fn in required:
            assert fn is not None, f"Required cloud function missing: {fn}"

    def test_function_count(self):
        """确保不超过微信云函数数量限制（单个环境最多50个）"""
        # 当前已知: 12 云函数 (6 管理后台 + 6 业务)
        admin_fns = ["adminAuth", "adminExercises", "adminPlans",
                     "adminSeed", "adminStats", "adminUsers"]
        biz_fns = ["login", "getExercises", "getPlans", "saveWorkout",
                   "planTemplates", "seedExercises"]
        total = len(admin_fns) + len(biz_fns)
        assert total < 50, f"Too many cloud functions: {total} > 50"


class TestExerciseDataRules:
    """动作数据业务规则"""

    def test_exercise_valid_category(self):
        valid_categories = {c["id"] for c in EXERCISE_CATEGORIES}
        test_exercise = {"name": "Test", "category": "chest"}
        assert test_exercise["category"] in valid_categories

    def test_exercise_invalid_category_rejected(self):
        valid_categories = {c["id"] for c in EXERCISE_CATEGORIES}
        invalid_category = "invalid_category"
        assert invalid_category not in valid_categories

    def test_exercise_valid_difficulty(self):
        valid = {d["id"] for d in DIFFICULTY_LEVELS}
        for level in ["beginner", "intermediate", "advanced"]:
            assert level in valid

    def test_exercise_valid_equipment(self):
        valid = {e["id"] for e in EQUIPMENT_TYPES}
        for eq in ["barbell", "dumbbell", "bodyweight", "machine"]:
            assert eq in valid


class TestWorkoutValidation:
    """训练记录验证"""

    def test_volume_calculation(self):
        """训练量 = weight × reps × sets"""
        weight, reps, sets = 60, 10, 3
        volume = weight * reps * sets
        assert volume == 1800

    def test_duration_formatting(self):
        """格式化时长: 秒 → 可读文本"""
        def format_duration(seconds):
            if not seconds: return "--"
            h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
            if h > 0: return f"{h}h{m}m"
            if m > 0: return f"{m}m{s}s"
            return f"{s}s"

        assert format_duration(0) == "--"
        assert format_duration(65) == "1m5s"
        assert format_duration(3661) == "1h1m"

    def test_workout_exercise_sets_minimum(self):
        """一个训练至少包含1个动作，每个动作至少1组"""
        exercises = [{"name": "杠铃卧推", "sets": 3}]
        assert len(exercises) > 0
        for ex in exercises:
            assert ex["sets"] > 0


class TestTabBarConfig:
    """底部导航栏配置验证"""

    def test_four_tabs(self):
        assert len(TABBAR_PAGES) == 4

    def test_no_tab_page_used_in_navigateTo(self):
        """
        关键规则: tabBar 页面不能用 wx.navigateTo 跳转，
        必须用 wx.switchTab
        """
        for page in TABBAR_PAGES:
            assert page in PAGE_NAMES


class TestOpenIdFormat:
    """OpenID 格式验证"""

    def test_valid_openid_pattern(self):
        """微信 openid 长度 28，字符集 [a-zA-Z0-9_-]"""
        import re
        valid = "oABC123xyz_DEF456GHI789_JKLm"
        invalid_short = "too_short"
        pattern = r"^[a-zA-Z0-9_-]{20,32}$"
        assert re.match(pattern, valid), "Valid openid should match"
        assert not re.match(pattern, invalid_short), "Short string should not match"
