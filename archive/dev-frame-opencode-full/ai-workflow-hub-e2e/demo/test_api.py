"""Demo API 测试 — pytest + requests

覆盖：正常路径、异常路径、认证、超时 — 演示完整测试+归因流程
"""

import requests
import pytest
import time

BASE_URL = "http://127.0.0.1:8765"
TOKEN = None


class TestHealthCheck:
    """健康检查 — 全部应通过"""

    def test_health_ok(self):
        resp = requests.get(f"{BASE_URL}/api/health", timeout=5)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestAuth:
    """认证流程"""

    def test_login_success(self):
        global TOKEN
        resp = requests.post(f"{BASE_URL}/api/login",
                             json={"username": "test", "password": "123456"},
                             timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "token" in data
        TOKEN = data["token"]

    def test_login_fail_wrong_password(self):
        resp = requests.post(f"{BASE_URL}/api/login",
                             json={"username": "test", "password": "wrong"},
                             timeout=5)
        assert resp.status_code == 401
        # ⚠ 故意让这个断言失败 — 演示归因
        # 实际API返回 code=401，下面这行会被归因引擎匹配到
        assert resp.json()["code"] == 401

    def test_unauthorized_access(self):
        resp = requests.get(f"{BASE_URL}/api/users", timeout=5)
        assert resp.status_code == 401
        assert "Unauthorized" in resp.json()["message"]


class TestUsers:
    """用户管理 — 需认证"""

    def test_get_users_authenticated(self):
        global TOKEN
        if not TOKEN:
            pytest.skip("Token not available")
        resp = requests.get(f"{BASE_URL}/api/users",
                            headers={"Authorization": f"Bearer {TOKEN}"},
                            timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["users"]) > 0

    def test_get_users_returns_unauthorized(self):
        resp = requests.get(f"{BASE_URL}/api/users", timeout=5)
        assert resp.status_code == 401


class TestOrders:
    """订单流程"""

    def test_create_order_success(self):
        global TOKEN
        resp = requests.post(f"{BASE_URL}/api/orders",
                             headers={"Authorization": f"Bearer {TOKEN}"},
                             json={"product_id": "widget_a", "qty": 1},
                             timeout=5)
        assert resp.status_code == 201
        assert "order_id" in resp.json()

    def test_get_order_exists(self):
        resp = requests.get(f"{BASE_URL}/api/orders/123", timeout=5)
        assert resp.status_code == 200

    def test_get_order_not_found(self):
        resp = requests.get(f"{BASE_URL}/api/orders/404", timeout=5)
        assert resp.status_code == 404

    def test_create_order_server_error(self):
        """触发服务端错误 — 用于归因演示"""
        global TOKEN
        resp = requests.post(f"{BASE_URL}/api/orders",
                             headers={"Authorization": f"Bearer {TOKEN}"},
                             json={"product_id": "fail", "qty": 1},
                             timeout=5)
        assert resp.status_code == 201  # ← 故意断言通过，但实际返回500
        # 这会失败，被归因引擎检测到 500 模式


class TestProducts:
    """商品查询"""

    def test_get_products(self):
        resp = requests.get(f"{BASE_URL}/api/products", timeout=5)
        assert resp.status_code == 200
        products = resp.json()["products"]
        assert len(products) > 0
        assert all("name" in p and "price" in p for p in products)

    def test_product_not_found(self):
        resp = requests.get(f"{BASE_URL}/api/nonexistent", timeout=5)
        assert resp.status_code == 404


class TestSlowEndpoint:
    """超时测试"""

    @pytest.mark.slow
    def test_slow_response(self):
        resp = requests.post(f"{BASE_URL}/api/slow",
                             json={"delay": 1},
                             timeout=10)
        assert resp.status_code == 200
