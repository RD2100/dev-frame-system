import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from control_plane.handoff_generator import generate_handoff, save_handoff


def test_generate_handoff_returns_string():
    text = generate_handoff("new-conversation")
    assert isinstance(text, str)
    assert len(text) > 500


def test_generate_handoff_contains_required_sections():
    text = generate_handoff("new-conversation")
    for section in ["项目定位", "架构", "安全边界", "期望回复格式"]:
        assert section in text, f"Missing: {section}"


def test_generate_handoff_has_authorship_warning():
    text = generate_handoff("new-conversation")
    assert "交接文档作者模型" in text or "完整上下文" in text


def test_save_handoff_writes_file(tmp_path):
    path = save_handoff(tmp_path / "test_handoff.md", "new-conversation")
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "HANDOFF — DevFrame Control Plane" in content
