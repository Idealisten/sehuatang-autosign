#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEY="$1"

if [ -z "$KEY" ]; then
    echo "用法: ./set_bark.sh <你的Bark_Key或完整URL>"
    echo "示例: ./set_bark.sh abc12345678"
    echo "示例: ./set_bark.sh https://api.day.app/abc12345678"
    exit 1
fi

echo ">>> 正在配置 Bark Key 并发送测试推送..."
"$DIR/.venv/bin/python" "$DIR/sehuatang_sign.py" --bark-key "$KEY" --test-bark "$KEY"
