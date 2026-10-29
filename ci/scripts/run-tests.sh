#!/bin/bash
# TestFrame 一键运行脚本
set -e

PROJECT="${1:-app-android}"
PROFILE="${2:-smoke}"

echo "🚀 TestFrame 启动"
echo "  项目: $PROJECT"
echo "  策略: $PROFILE"
echo ""

# 设置环境变量（从 .env 文件加载）
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

# 执行测试
python -m cli.main run --project="$PROJECT" --profile="$PROFILE"

# 生成报告
python -m cli.main report --project="$PROJECT"

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ 执行完成"
else
    echo "❌ 执行失败 (exit: $EXIT_CODE)"
fi
exit $EXIT_CODE
