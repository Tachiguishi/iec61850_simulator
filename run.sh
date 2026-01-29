#!/usr/bin/env bash

set -e

# =========================
# 配置区
# =========================

PYTHON_BIN="$(which python)"
PYTHON_BIN_REAL="$(readlink -f "$PYTHON_BIN")"
APP_MAIN="main.py"

REQUIRED_CAPS="cap_net_bind_service,cap_net_raw,cap_net_admin"

# =========================
# 函数区
# =========================

has_required_caps() {
    local caps
	# fedora: path cap_net_bind_service,cap_net_admin,cap_net_raw=ep
	# ubuntu: path = cap_net_bind_service,cap_net_raw,cap_net_admin=ep
    caps=$(getcap "$PYTHON_BIN_REAL" 2>/dev/null | sed -E 's/^[^= ]+[ =]+//')

    [[ "$caps" == *"cap_net_bind_service"* && "$caps" == *"cap_net_raw"* && "$caps" == *"cap_net_admin"* ]]
}

add_caps_gui() {
    echo "🔐 Python 缺少网络权限, 正在请求管理员授权(GUI)..."

	echo $PYTHON_BIN_REAL
    pkexec setcap "${REQUIRED_CAPS}=+ep" "$PYTHON_BIN_REAL"

    echo "✅ capability 设置完成"
}

# =========================
# 主流程
# =========================

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "❌ Python 不存在或不可执行：$PYTHON_BIN"
    exit 1
fi

if has_required_caps; then
    echo "✅ Python 已具备所需网络权限"
else
    add_caps_gui
fi

echo "🚀 启动 PyQt 程序..."
exec "$PYTHON_BIN" "$APP_MAIN"
