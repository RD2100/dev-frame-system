"""自包含 Mock API 服务器 — 零依赖，仅使用 Python stdlib

模拟一个电商后端，用于演示 TestFrame 完整流水线。
"""

import json
import time
import random
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = 8765
TOKENS = {}


class MockAPIHandler(BaseHTTPRequestHandler):
    """模拟电商 API"""

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json(200, {"status": "ok", "version": "1.0.0"})
        elif path == "/api/users":
            if not self._auth_check():
                return
            self._json(200, {
                "users": [
                    {"id": 1, "name": "TestUser", "email": "test@example.com"},
                    {"id": 2, "name": "DemoUser", "email": "demo@example.com"},
                ],
                "total": 2
            })
        elif path.startswith("/api/orders/"):
            order_id = path.split("/")[-1]
            if order_id == "404":
                self._json(404, {"code": 404, "message": "Order not found"})
            else:
                self._json(200, {
                    "id": order_id,
                    "status": "paid",
                    "amount": 99.9,
                    "items": [{"product": "TestFrame Pro", "qty": 1}]
                })
        elif path == "/api/products":
            self._json(200, {
                "products": [
                    {"id": 1, "name": "Widget A", "price": 9.9},
                    {"id": 2, "name": "Widget B", "price": 19.9},
                ]
            })
        else:
            self._json(404, {"code": 404, "message": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_body()

        if path == "/api/login":
            if body.get("username") == "test" and body.get("password") == "123456":
                token = f"tok_{random.randint(10000, 99999)}"
                TOKENS[token] = body["username"]
                self._json(200, {"code": 200, "token": token, "user": {"id": 1, "name": "TestUser"}})
            else:
                self._json(401, {"code": 401, "message": "Invalid credentials"})

        elif path == "/api/orders":
            if not self._auth_check():
                return
            # 模拟偶尔创建失败（用于测试归因）
            if body.get("product_id") == "fail":
                self._json(500, {"code": 500, "message": "Internal Server Error"})
            else:
                self._json(201, {"code": 201, "order_id": f"ord_{random.randint(1000, 9999)}"})

        elif path == "/api/slow":
            delay = body.get("delay", 3)
            time.sleep(min(delay, 5))
            self._json(200, {"status": "done", "delay": delay})

        else:
            self._json(404, {"code": 404, "message": "Not found"})

    def do_PUT(self):
        body = self._read_body()
        path = urlparse(self.path).path
        if path.startswith("/api/users/"):
            if not self._auth_check():
                return
            self._json(200, {"code": 200, "user": body})
        else:
            self._json(404, {"code": 404, "message": "Not found"})

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path.startswith("/api/orders/"):
            if not self._auth_check():
                return
            self._json(200, {"code": 200, "message": "Order cancelled"})
        else:
            self._json(404, {"code": 404, "message": "Not found"})

    def _auth_check(self) -> bool:
        auth = self.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "")
        if token not in TOKENS:
            self._json(401, {"code": 401, "message": "Unauthorized"})
            return False
        return True

    def _read_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(length)) if length > 0 else {}
        except (json.JSONDecodeError, ValueError):
            return {}

    def _json(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
        # 🔑 所有响应都记录到 stdout，供 TestFrame 收集
        if code >= 500:
            print(f"[MOCK-ERROR] {code} {data.get('message', '')}")

    def log_message(self, format, *args):
        pass  # 禁用默认日志，避免干扰


def start_server(port: int = PORT):
    server = HTTPServer(("127.0.0.1", port), MockAPIHandler)
    print(f"[MOCK] Server started at http://127.0.0.1:{port}")
    print(f"[MOCK] Endpoints: health, login, users, orders, products, slow")
    return server


if __name__ == "__main__":
    srv = start_server()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[MOCK] Server stopped")
        srv.shutdown()
