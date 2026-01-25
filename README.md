# IEC61850 Simulator

基于 PyQt6 的 IEC61850 协议仿真器，支持服务端（IED仿真）和客户端（SCADA/控制台）两种工作模式。

## 功能特性

### 服务端模式
- 🖥️ 仿真 IED (智能电子设备)
- 📊 完整的 IEC61850 数据模型支持 (IED/LD/LN/DO/DA)
- 🔌 MMS 协议服务端实现
- 📈 实时数据仿真和随机值生成
- 👥 多客户端连接管理
- 📋 报告和 GOOSE 发布支持
- 💾 YAML 配置文件加载/导出

### 客户端模式
- 🔗 连接到 IED 服务器
- 🌲 数据模型浏览
- 📖 数据读取和写入
- 🎮 控制操作 (直接控制/SBO)
- 📡 数据订阅和轮询
- 📊 实时数据监控

### GUI 功能
- 🎨 现代化 PyQt6 界面
- 🔄 服务端/客户端模式一键切换
- 🌲 树形数据模型视图
- 📋 实时日志显示
- ⚙️ 配置管理
- 🌍 中文界面支持

## 项目结构

```
iec61850_simulator/
├── main.py                     # 主入口文件
├── requirements.txt            # Python 依赖
├── README.md                   # 项目说明
│
├── config/                     # 配置文件
│   ├── config.yaml             # 应用配置
│   └── data_model.yaml         # 示例数据模型
│
├── src/
│   ├── core/                   # 核心模块
│   │   ├── __init__.py
│   │   └── data_model.py       # IEC61850 数据模型实现
│   │
│   ├── server/                 # 服务端模块
│   │   ├── __init__.py
│   │   └── iec61850_server.py  # MMS 服务器实现
│   │
│   ├── client/                 # 客户端模块
│   │   ├── __init__.py
│   │   └── iec61850_client.py  # MMS 客户端实现
│   │
│   └── gui/                    # GUI 模块
│       ├── __init__.py
│       ├── main_window.py      # 主窗口
│       ├── server_panel.py     # 服务端面板
│       ├── client_panel.py     # 客户端面板
│       ├── data_tree_widget.py # 数据树控件
│       └── log_widget.py       # 日志控件
│
└── logs/                       # 日志文件 (运行时生成)
```

## 安装

### 环境要求
- Python 3.9+
- PyQt6

### 安装步骤

1. 克隆或下载项目
```bash
cd /path/to/iec61850_simulator
```

2. 创建虚拟环境 (推荐)
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
.\venv\Scripts\activate   # Windows
```

3. 安装依赖
```bash
pip install -r requirements.txt
```

## 使用方法

### GUI 模式

启动图形界面:
```bash
python main.py
```

直接进入服务端模式:
```bash
python main.py --server
```

直接进入客户端模式:
```bash
python main.py --client
```

### 无界面服务器模式

运行无界面的 IED 服务器:
```bash
python main.py --headless
```

指定端口:
```bash
python main.py --headless -p 8102
```

### 命令行客户端

连接到本地服务器:
```bash
python main.py --cli -H 127.0.0.1
```

## 命令行参数

```
usage: main.py [-h] [--server | --client | --headless | --cli] 
               [-H HOST] [-p PORT] [--log-level {DEBUG,INFO,WARNING,ERROR}]
               [--log-file LOG_FILE] [--version]

选项:
  --server, -s       启动服务端模式
  --client, -c       启动客户端模式
  --headless         无界面服务器模式
  --cli              命令行客户端模式
  -H, --host HOST    主机地址 (默认: 0.0.0.0/127.0.0.1)
  -p, --port PORT    端口号 (默认: 102)
  --log-level        日志级别 (DEBUG/INFO/WARNING/ERROR)
  --log-file         日志文件名
  --version, -v      显示版本
```

## 快速开始

### 场景1: 本地测试

1. 启动 GUI:
```bash
python main.py
```

2. 在服务端模式下点击"启动服务"

3. 切换到客户端模式，输入 `127.0.0.1:102`，点击"连接"

4. 浏览数据模型，读写数据点

### 场景2: 多机测试

**服务器端:**
```bash
python main.py --headless -H 0.0.0.0 -p 102
```

**客户端:**
```bash
python main.py --client
# 输入服务器IP地址进行连接
```

## 数据模型

### 默认 IED 结构

```
SimulatedIED
├── PROT (保护逻辑设备)
│   ├── LLN0 (逻辑节点零)
│   │   ├── Mod (模式)
│   │   └── Beh (行为)
│   ├── PTOC1 (过流保护)
│   │   ├── Mod
│   │   └── Op (动作)
│   └── XCBR1 (断路器)
│       └── Pos (位置)
│
└── MEAS (测量逻辑设备)
    └── MMXU1 (测量单元)
        ├── TotW (有功功率)
        └── Hz (频率)
```

### 自定义数据模型

编辑 `config/data_model.yaml` 文件定义自己的 IED 数据模型。

## API 示例

### 服务端 API

```python
from src.server import IEC61850Server, ServerConfig
from src.core import DataModelManager

# 创建服务器
config = ServerConfig(ip_address="0.0.0.0", port=102)
server = IEC61850Server(config)

# 创建默认 IED
manager = DataModelManager()
ied = manager.create_default_ied("MyIED")
server.load_ied(ied)

# 启动服务
server.start()

# 设置数据值
server.set_data_value("MyIEDPROT/PTOC1.Op.general", True)

# 停止服务
server.stop()
```

### 客户端 API

```python
from src.client import IEC61850Client

# 创建客户端
client = IEC61850Client()

# 连接服务器
client.connect("127.0.0.1", 102)

# 浏览数据模型
model = client.browse_data_model()

# 读取数据
value = client.read_value("SimulatedIEDPROT/XCBR1.Pos.stVal")
print(f"断路器位置: {value.value}")

# 写入数据
client.write_value("SimulatedIEDPROT/XCBR1.Pos.stVal", 2)

# 控制操作
client.operate("SimulatedIEDPROT/XCBR1.Pos.stVal", 1)  # 分闸

# 断开连接
client.disconnect()
```

## 技术说明

### IEC61850 数据层次

| 层次 | 说明 | 示例 |
|------|------|------|
| IED | 智能电子设备 | SimulatedIED |
| LD | 逻辑设备 | PROT, MEAS |
| LN | 逻辑节点 | PTOC1, XCBR1, MMXU1 |
| DO | 数据对象 | Pos, Op, TotW |
| DA | 数据属性 | stVal, q, t |

### 数据引用格式

```
IEDName + LDName / LNName . DOName . DAName
例如: SimulatedIEDPROT/XCBR1.Pos.stVal
```

### 协议说明

本仿真器使用简化的 TCP 协议模拟 MMS 通信。完整的 MMS/ACSI 实现需要使用 libiec61850 库。

## 开发计划

- [ ] 完整的 MMS 协议支持 (集成 libiec61850)
- [ ] GOOSE 发布/订阅
- [ ] 采样值 (SV) 支持
- [ ] SCL/ICD/CID 文件导入导出
- [ ] 时间同步 (SNTP)
- [ ] 安全认证
- [ ] 数据趋势图表
- [ ] 报表生成

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request!
