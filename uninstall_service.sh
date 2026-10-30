#!/usr/bin/env bash
set -e

PLIST_NAME="com.sehuatang.autosign.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo ">>> 正在停止并卸载色花堂后台签到服务..."

if [ -f "$PLIST_PATH" ]; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
    echo "✅ 后台服务已成功停止，并移除了配置文件: $PLIST_PATH"
else
    echo "⚠️ 未找到服务配置文件: $PLIST_PATH"
fi
