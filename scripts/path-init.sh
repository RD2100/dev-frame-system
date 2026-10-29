#!/bin/bash
# TestFrame PATH 初始化 — 将此文件 source 到你的 shell
# source D:/TestFrame/scripts/path-init.sh

# Android SDK
export ANDROID_HOME="$HOME/AppData/Local/Android/Sdk"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/tools:$PATH"

# Maestro
export PATH="$HOME/.maestro/bin:$PATH"

# Allure (from node_modules)
export PATH="$(cd "$(dirname "$0")/../node_modules/.bin" && pwd):$PATH"

echo "TestFrame PATH initialized"
echo "  ADB:     $(which adb 2>/dev/null || echo 'NOT FOUND')"
echo "  Maestro: $(which maestro 2>/dev/null || echo 'NOT FOUND')"
echo "  Allure:  $(which allure 2>/dev/null || echo 'NOT FOUND')"
echo "  Python:  $(python --version 2>&1)"
echo "  Node:    $(node --version 2>&1)"
