"""Allure wrapper — 封装 allure generate/serve 命令"""

import subprocess
import os


def generate_report(allure_results_dir: str, output_dir: str, clean: bool = True) -> bool:
    """生成Allure HTML报告"""
    cmd = ["allure", "generate", allure_results_dir, "-o", output_dir]
    if clean:
        cmd.append("--clean")

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            print(f"  [REPORT] Allure报告: {output_dir}")
            return True
        else:
            print(f"  [FAIL] Allure生成失败: {r.stderr[:200]}")
            return False
    except FileNotFoundError:
        print("  [WARN] Allure CLI未安装，跳过 (brew install allure)")
        return False
    except subprocess.TimeoutExpired:
        print("  [WARN] Allure生成超时")
        return False


def serve_report(allure_results_dir: str, port: int = 8080) -> bool:
    """启动Allure报告服务"""
    cmd = ["allure", "serve", allure_results_dir, "-p", str(port)]
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"  [REPORT] Allure服务: http://localhost:{port}")
        return True
    except FileNotFoundError:
        print("  [WARN] Allure CLI未安装")
        return False


def open_report(output_dir: str) -> bool:
    """打开Allure报告"""
    index_path = os.path.join(output_dir, "index.html")
    if not os.path.exists(index_path):
        print(f"  [FAIL] 报告不存在: {index_path}")
        return False

    import webbrowser
    webbrowser.open(f"file://{os.path.abspath(index_path)}")
    return True
