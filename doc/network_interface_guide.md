# 网络接口配置功能说明

## 概述

新增了全局网络接口配置功能，允许用户选择用于IP地址配置的网络接口。当服务器实例使用非 `0.0.0.0` 或 `127.*` 的IP地址时，系统会自动在指定的网络接口上配置相应的IP地址。

## 后端接口

### 1. `server.get_interfaces`

获取系统所有网络接口列表及当前配置。

**请求参数**: 无需参数

**返回数据**:
```python
{
    "interfaces": [
        {
            "name": "eth0",           # 网卡名称
            "description": "eth0",    # 描述
            "is_up": true,            # 是否启用
            "addresses": ["192.168.1.100"]  # IP地址列表
        },
        ...
    ],
    "current_interface": {
        "name": "eth0",      # 当前配置的网卡名称
        "prefix_len": 24     # 子网掩码位数
    }  # 如果未配置则为 null
}
```

### 2. `server.set_interface`

设置全局网络接口配置（对所有服务器实例生效）。

**请求参数**:
```python
{
    "interface_name": "eth0",  # 网卡名称（必需）
    "prefix_len": 24           # 子网掩码位数（可选，默认24）
}
```

**返回数据**:
```python
{
    "interface_name": "eth0",
    "prefix_len": 24
}
```

## GUI界面更新

### 1. 单服务器面板 (`ServerPanel`)

在 "服务器配置" 组中新增以下控件：

- **网络接口下拉框**: 显示所有可用网卡，格式为 `网卡名 [状态] - IP地址`
- **子网掩码位数**: SpinBox，范围 1-32，默认 24
- **设置网络接口按钮**: 应用网络接口配置

**使用流程**:
1. 程序启动时自动加载网络接口列表
2. 选择要使用的网络接口
3. 设置子网掩码位数（CIDR格式）
4. 点击 "设置网络接口" 按钮应用配置

### 2. 多实例服务器面板 (`MultiServerPanel`)

在左侧面板顶部新增 "全局网络接口" 配置组：

- **网络接口下拉框**: 选择网卡
- **前缀长度**: SpinBox，设置子网掩码位数
- **应用配置按钮**: 应用到所有实例

**特点**:
- 配置对所有服务器实例生效
- 无需为每个实例单独配置
- 实例启动时自动使用全局配置

## 工作原理

### IP地址自动配置

当满足以下条件时，系统会自动配置IP地址：

1. 已通过 `server.set_interface` 设置了网络接口
2. 服务器实例的IP地址不是 `0.0.0.0` 或 `127.*`
3. 调用 `server.start` 启动服务器实例

**配置过程**:
```
用户启动服务器 (IP: 192.168.1.100)
    ↓
检查是否需要配置IP (非 0.0.0.0/127.*)
    ↓
使用libnl库在指定网卡上添加IP地址
    ↓
格式: 192.168.1.100/24 dev eth0 label eth0:iec<instance_id>
```

### IP地址清理

当调用 `server.remove` 删除服务器实例时，系统会自动清理配置的IP地址。

**注意**: `server.stop` 仅停止服务，不会清理IP地址。只有 `server.remove` 才会完全清理资源。

## 实现细节

### 后端 (C++)

- **网络配置模块**: `network_config.cpp/hpp`
- **使用libnl3库**: 通过netlink直接配置网络接口
- **主要函数**:
  - `get_network_interfaces()`: 枚举系统网卡
  - `add_ip_address()`: 添加IP地址（带label）
  - `remove_ip_address()`: 删除IP地址
  - `should_configure_ip()`: 判断是否需要配置

### 前端 (Python)

- **ServerProxy扩展**: `server_proxy.py`
  - `get_network_interfaces()`: 获取接口列表
  - `set_network_interface()`: 设置接口配置

- **GUI更新**: 
  - `server_panel.py`: 单实例面板
  - `multi_server_panel.py`: 多实例面板
  - `server_panel.ui`: UI布局文件

## 系统依赖

### Linux包

需要安装libnl开发库：

**Fedora/RHEL**:
```bash
sudo dnf install libnl3-devel
```

**Ubuntu/Debian**:
```bash
sudo apt-get install libnl-3-dev libnl-route-3-dev
```

### 权限要求

配置网络接口需要root权限。建议以下方式运行：

```bash
# 方式1: 使用sudo运行
sudo ./iec61850/build/bin/iec61850_core

# 方式2: 给程序添加CAP_NET_ADMIN权限
sudo setcap cap_net_admin+ep ./iec61850/build/bin/iec61850_core
```

## 测试

### 后端测试

```bash
# 启动后端服务
./iec61850/build/bin/iec61850_core

# 在另一个终端运行测试
python3 test_network_interface.py
```

### GUI测试

```bash
# 启动GUI程序
python3 main.py

# 在单实例或多实例服务器面板中:
# 1. 查看网络接口列表
# 2. 选择一个接口
# 3. 点击设置按钮
# 4. 配置服务器IP为非0.0.0.0的地址（如192.168.1.100）
# 5. 启动服务器
# 6. 使用 `ip addr show` 验证IP已配置
```

## 注意事项

1. **全局配置**: 网络接口配置是全局的，对所有服务器实例生效
2. **权限要求**: 需要root权限或CAP_NET_ADMIN能力
3. **IP冲突**: 确保配置的IP地址不与网络中其他设备冲突
4. **Label标识**: 配置的IP会带有label标识，格式为 `<interface>:iec<instance_id>`
5. **自动清理**: 只有 `server.remove` 会清理IP，`server.stop` 不会清理

## 示例

### 配置示例

```python
# 1. 获取接口列表
interfaces, current = proxy.get_network_interfaces()
# interfaces = [{'name': 'eth0', 'is_up': True, 'addresses': ['192.168.1.50']}]

# 2. 设置接口
proxy.set_network_interface("eth0", 24)

# 3. 启动服务器（IP: 192.168.1.100）
proxy.start()

# 系统会自动执行:
# ip addr add 192.168.1.100/24 dev eth0 label eth0:iec<id>
```

### 验证配置

```bash
# 查看网卡配置
ip addr show eth0

# 输出示例:
# 2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc pfifo_fast state UP group default qlen 1000
#     inet 192.168.1.50/24 brd 192.168.1.255 scope global eth0
#     inet 192.168.1.100/24 scope global secondary eth0:iec001
```

## 故障排查

### 问题1: 获取接口列表失败

**原因**: 后端服务未启动或IPC连接失败

**解决**: 
```bash
# 检查后端服务
ps aux | grep iec61850_core

# 检查socket文件
ls -l /tmp/iec61850_simulator.sock
```

### 问题2: 设置接口失败

**原因**: 权限不足

**解决**:
```bash
# 使用sudo运行后端
sudo ./iec61850/build/bin/iec61850_core
```

### 问题3: IP配置失败

**原因**: 
- 网卡不存在
- IP地址已被占用
- 权限不足

**解决**:
```bash
# 检查网卡是否存在
ip link show

# 检查IP是否已占用
ip addr show | grep 192.168.1.100

# 检查libnl是否安装
pkg-config --modversion libnl-3.0
```

## 相关文件

### 后端
- `iec61850/src/network_config.hpp/cpp` - 网络配置实现
- `iec61850/src/action_server.cpp` - 服务器动作处理
- `iec61850/src/core_context.hpp` - 上下文定义
- `iec61850/CMakeLists.txt` - CMake配置

### 前端
- `src/server/server_proxy.py` - 服务器代理
- `src/gui/server_panel.py` - 单实例面板
- `src/gui/multi_server_panel.py` - 多实例面板
- `src/gui/ui/server_panel.ui` - UI布局

### 测试
- `test_network_interface.py` - 网络接口测试脚本
