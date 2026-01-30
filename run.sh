#!/usr/bin/env bash

set -e

# =========================
# 配置区
# =========================

PYTHON_BIN="$(which python)"
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IEC61850_CORE_BIN="$CURRENT_DIR/iec61850/build/src/iec61850_core"
APP_MAIN="main.py"

REQUIRED_CAPS="cap_net_bind_service,cap_net_raw,cap_net_admin"

# =========================
# 函数区
# =========================

has_required_caps() {
    local caps
	# fedora: path cap_net_bind_service,cap_net_admin,cap_net_raw=ep
	# ubuntu: path = cap_net_bind_service,cap_net_raw,cap_net_admin=ep
    caps=$(getcap "$IEC61850_CORE_BIN" 2>/dev/null | sed -E 's/^[^= ]+[ =]+//')

    [[ "$caps" == *"cap_net_bind_service"* && "$caps" == *"cap_net_raw"* && "$caps" == *"cap_net_admin"* ]]
}

add_caps_gui() {
    echo "🔐 Python 缺少网络权限, 正在请求管理员授权(GUI)..."

	echo $IEC61850_CORE_BIN
    pkexec setcap "${REQUIRED_CAPS}=+ep" "$IEC61850_CORE_BIN"

    echo "✅ capability 设置完成"
}

# =========================
# 主流程
# =========================

if [[ ! -x "$IEC61850_CORE_BIN" ]]; then
    echo "❌ IEC61850 Core 不存在或不可执行：$IEC61850_CORE_BIN"
    exit 1
fi

if has_required_caps; then
    echo "✅ IEC61850 Core 已具备所需网络权限"
else
    add_caps_gui
fi

echo "🚀 启动 PyQt 程序..."
exec "$PYTHON_BIN" "$APP_MAIN"
