#!/usr/bin/env bash
set -e

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME/.sehuatang"
PLIST_NAME="com.sehuatang.exporter.plist"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$PLIST_NAME"

echo ">>> 正在为当前电脑 (电脑 A) 配置 Cookie 自动导出后台服务..."
echo ">>> 程序目录: $TARGET_DIR"

mkdir -p "$TARGET_DIR"
mkdir -p "$PLIST_DIR"

# 同步程序文件
rsync -av --exclude "sehuatang_sign.log" "$SOURCE_DIR/" "$TARGET_DIR/" >/dev/null

# 卸载旧服务 (若存在)
if launchctl list | grep -q "com.sehuatang.exporter"; then
    echo ">>> 卸载旧导出服务..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

cat <<EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.sehuatang.exporter</string>
    <key>ProgramArguments</key>
    <array>
        <string>$TARGET_DIR/.venv/bin/python</string>
        <string>$TARGET_DIR/sehuatang_sign.py</string>
        <string>--export-cookies</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$TARGET_DIR</string>
    <key>StartCalendarInterval</key>
    <array>
        <dict>
            <key>Hour</key>
            <integer>12</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
        <dict>
            <key>Hour</key>
            <integer>20</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/sehuatang_exporter.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/sehuatang_exporter.log</string>
</dict>
</plist>
EOF

launchctl load "$PLIST_PATH"

echo "✅ 电脑 A 自动导出服务安装成功！"
echo "   每天将在 12:00 和 20:00 (以及开机时) 自动解密 Chrome 最新 Cookies 并同步至 iCloud / 电脑 B。"
echo "   如需卸载请运行: launchctl unload $PLIST_PATH && rm -f $PLIST_PATH"
