#!/usr/bin/env bash
set -e

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME/.sehuatang"
PLIST_NAME="com.sehuatang.autosign.plist"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$PLIST_NAME"

HOUR="${1:-0}"
MINUTE="${2:-1}"

# 格式化展示两位数时间
TIME_FMT=$(printf "%02d:%02d" "$HOUR" "$MINUTE")

echo ">>> 正在配置色花堂后台自动签到服务..."
echo ">>> 执行时间: 每日 $TIME_FMT (支持休眠唤醒补跑)"
echo ">>> 源码目录: $SOURCE_DIR"
echo ">>> 安装目标: $TARGET_DIR"

# 1. 创建 ~/.sehuatang 并同步文件 (避开 macOS 对 ~/Documents 的 launchd 权限沙盒限制)
mkdir -p "$TARGET_DIR"
mkdir -p "$PLIST_DIR"

echo ">>> 同步程序文件及运行环境至 $TARGET_DIR ..."
rsync -av --exclude "sehuatang_sign.log" "$SOURCE_DIR/" "$TARGET_DIR/" >/dev/null

# 2. 卸载已存在的旧服务
if launchctl list | grep -q "com.sehuatang.autosign"; then
    echo ">>> 卸载旧服务..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

# 3. 生成 LaunchAgent plist 配置文件
cat <<EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.sehuatang.autosign</string>
    <key>ProgramArguments</key>
    <array>
        <string>$TARGET_DIR/.venv/bin/python</string>
        <string>$TARGET_DIR/sehuatang_sign.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$TARGET_DIR</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>$HOUR</integer>
        <key>Minute</key>
        <integer>$MINUTE</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$TARGET_DIR/sehuatang_sign.log</string>
    <key>StandardErrorPath</key>
    <string>$TARGET_DIR/sehuatang_sign.log</string>
</dict>
</plist>
EOF

# 4. 加载服务到 launchctl
echo ">>> 加载并启动 launchd 后台服务..."
launchctl load "$PLIST_PATH"

# 在当前工作目录创建日志软链接，方便随时查看
if [ ! -L "$SOURCE_DIR/sehuatang_sign.log" ] && [ "$SOURCE_DIR" != "$TARGET_DIR" ]; then
    touch "$TARGET_DIR/sehuatang_sign.log"
    rm -f "$SOURCE_DIR/sehuatang_sign.log"
    ln -s "$TARGET_DIR/sehuatang_sign.log" "$SOURCE_DIR/sehuatang_sign.log"
fi

echo "✅ 服务安装并加载成功！"
echo "   服务标识: com.sehuatang.autosign"
echo "   配置文件: $PLIST_PATH"
echo "   每天将在 $TIME_FMT 自动静默运行签到 (电脑休眠时唤醒后自动补跑)"
echo "   日志文件: $TARGET_DIR/sehuatang_sign.log"
echo "   如需卸载请运行: ./uninstall_service.sh"
