"""FitTrack API 测试 conftest — 启动/停止 Mock 服务器"""
import threading
import time
import pytest
from tests.fittrack.mock_server import start_server


@pytest.fixture(scope="session", autouse=True)
def mock_server():
    """Session-scoped mock server: 启动一次，所有测试共享"""
    srv = start_server()
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    time.sleep(0.5)
    yield srv
    srv.shutdown()
