#!/bin/bash
# TestFrame 一键环境安装脚本
set -e
echo "🚀 TestFrame 环境安装..."

echo ""
echo ">>> [1/6] 检查 Python..."
python3 --version 2>/dev/null || python --version 2>/dev/null || {
    echo "❌ 请安装 Python 3.10+: https://python.org"
    exit 1
}

echo ""
echo ">>> [2/6] 检查 Node.js..."
node --version 2>/dev/null || {
    echo "❌ 请安装 Node.js 18+: https://nodejs.org"
    exit 1
}

echo ""
echo ">>> [3/6] 检查 ADB..."
adb --version 2>/dev/null || {
    echo "⚠ ADB 未安装 (Android测试需要)"
    echo "  安装: Android SDK Platform Tools"
}

echo ""
echo ">>> [4/6] 安装 Python 依赖..."
pip install -r requirements.txt 2>/dev/null || pip3 install -r requirements.txt

echo ""
echo ">>> [5/6] 安装 Node.js 依赖..."
npm install 2>/dev/null || echo "⚠ npm install 失败 (package.json 可能不存在)"

echo ""
echo ">>> [6/6] 检查可选工具..."

# Maestro
command -v maestro &>/dev/null && echo "  ✅ Maestro: $(maestro --version)" || {
    echo "  ⚠ Maestro未安装: curl -fsSL 'https://get.maestro.mobile.dev' | bash"
}

# Allure
command -v allure &>/dev/null && echo "  ✅ Allure: $(allure --version)" || {
    echo "  ⚠ Allure未安装: brew install allure / npm install -g allure-commandline"
}

# Playwright
npx playwright --version &>/dev/null && echo "  ✅ Playwright 可用" || {
    echo "  ⚠ Playwright未安装: npm init playwright@latest"
}

# Airtest
python -c "import airtest" 2>/dev/null && echo "  ✅ Airtest 可用" || {
    echo "  ⚠ Airtest未安装: pip install airtest pocoui"
}

echo ""
echo "✅ 环境检查完成"
echo ""
echo "下一步:"
echo "  1. 配置项目: 编辑 config/projects/<项目名>.yaml"
echo "  2. 运行测试: python -m cli.main run --project=<项目名> --profile=smoke"
echo "  3. 安装工具: 参考 SETUP.md 安装所需第三方工具"
