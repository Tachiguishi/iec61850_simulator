# IEC61850 仿真器设计文档

**版本**: 1.0.0  
**日期**: 2026-01-22  
**作者**: IEC61850 Simulator Team

---

## 目录

1. [概述](#1-概述)
2. [系统架构](#2-系统架构)
3. [技术选型](#3-技术选型)
4. [模块设计](#4-模块设计)
5. [数据模型设计](#5-数据模型设计)
6. [通信协议设计](#6-通信协议设计)
7. [GUI设计](#7-gui设计)
8. [配置管理](#8-配置管理)
9. [接口设计](#9-接口设计)
10. [部署方案](#10-部署方案)
11. [扩展性设计](#11-扩展性设计)

---

## 1. 概述

### 1.1 项目背景

IEC61850 是电力系统自动化领域的国际标准，定义了变电站通信网络和系统的通信协议。本项目旨在开发一个基于 PyQt6 的 IEC61850 协议仿真器，用于：

- 电力系统软件开发测试
- IEC61850 协议学习和研究
- 变电站自动化系统集成测试
- 教学演示

### 1.2 系统目标

| 目标 | 描述 |
|------|------|
| 双模式支持 | 同时支持服务端（IED仿真）和客户端（SCADA仿真）模式 |
| 标准兼容 | 遵循 IEC61850 标准数据模型定义 |
| 易用性 | 提供直观的图形界面，降低使用门槛 |
| 可扩展 | 支持自定义数据模型和协议扩展 |
| 跨平台 | 支持 Windows、Linux、macOS |

### 1.3 术语定义

| 术语 | 全称 | 说明 |
|------|------|------|
| IED | Intelligent Electronic Device | 智能电子设备 |
| LD | Logical Device | 逻辑设备 |
| LN | Logical Node | 逻辑节点 |
| DO | Data Object | 数据对象 |
| DA | Data Attribute | 数据属性 |
| MMS | Manufacturing Message Specification | 制造报文规范 |
| GOOSE | Generic Object Oriented Substation Event | 通用面向对象变电站事件 |
| SV | Sampled Values | 采样值 |
| SCL | Substation Configuration Language | 变电站配置语言 |
| CDC | Common Data Class | 公共数据类 |
| FC | Functional Constraint | 功能约束 |

---

## 2. 系统架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        表现层 (Presentation Layer)               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  MainWindow │  │ ServerPanel │  │ ClientPanel │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│  ┌─────────────┐  ┌─────────────┐                               │
│  │DataTreeWidget│ │  LogWidget  │                               │
│  └─────────────┘  └─────────────┘                               │
├─────────────────────────────────────────────────────────────────┤
│                        业务逻辑层 (Business Logic Layer)         │
│  ┌─────────────────────────┐  ┌─────────────────────────┐       │
│  │    IEC61850Server       │  │    IEC61850Client       │       │
│  │  ┌─────────────────┐    │  │  ┌─────────────────┐    │       │
│  │  │ ConnectionMgr   │    │  │  │ ConnectionMgr   │    │       │
│  │  │ MessageHandler  │    │  │  │ RequestHandler  │    │       │
│  │  │ ReportEngine    │    │  │  │ SubscriptionMgr │    │       │
│  │  └─────────────────┘    │  │  └─────────────────┘    │       │
│  └─────────────────────────┘  └─────────────────────────┘       │
├─────────────────────────────────────────────────────────────────┤
│                        数据模型层 (Data Model Layer)             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   DataModelManager                       │    │
│  │  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐           │    │
│  │  │ IED │──│ LD  │──│ LN  │──│ DO  │──│ DA  │           │    │
│  │  └─────┘  └─────┘  └─────┘  └─────┘  └─────┘           │    │
│  └─────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│                        通信层 (Communication Layer)              │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              TCP Socket (MMS Protocol Simulation)        │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 分层说明

| 层次 | 职责 | 主要组件 |
|------|------|----------|
| 表现层 | 用户界面展示和交互 | MainWindow, ServerPanel, ClientPanel, DataTreeWidget |
| 业务逻辑层 | 业务处理和协议实现 | IEC61850Server, IEC61850Client |
| 数据模型层 | IEC61850 数据对象管理 | DataModelManager, IED, LD, LN, DO, DA |
| 通信层 | 网络通信和协议编解码 | TCP Socket, Message Encoder/Decoder |

### 2.3 组件交互图

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│   GUI    │◄────│  Server  │◄────│  Client  │
│ (PyQt6)  │     │  Module  │     │  Module  │
└────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │
     │    ┌───────────┴───────────┐    │
     │    │                       │    │
     ▼    ▼                       ▼    ▼
┌─────────────────────────────────────────┐
│           Data Model Manager            │
│  (IED → LD → LN → DO → DA Hierarchy)    │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│         Configuration Manager           │
│         (YAML Config Files)             │
└─────────────────────────────────────────┘
```

---

## 3. 技术选型

### 3.1 开发语言

| 选项 | 选择 | 理由 |
|------|------|------|
| 编程语言 | Python 3.9+ | 开发效率高、跨平台、丰富的生态系统 |

### 3.2 主要框架和库

| 类别 | 选择 | 版本 | 用途 |
|------|------|------|------|
| GUI框架 | PyQt6 | ≥6.5.0 | 现代化跨平台GUI |
| 配置管理 | PyYAML | ≥6.0 | YAML配置文件解析 |
| 数据验证 | Pydantic | ≥2.0.0 | 数据模型验证 |
| 日志 | Loguru | ≥0.7.0 | 结构化日志 |
| XML解析 | lxml | ≥4.9.0 | SCL文件解析 |
| 数据处理 | NumPy | ≥1.24.0 | 数值计算 |

### 3.3 技术选型对比

#### GUI框架对比

| 框架 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| PyQt6 | 功能完善、文档丰富、跨平台 | 商业许可需付费 | ✅ 选用 |
| PySide6 | LGPL许可、Qt官方支持 | 社区资源较少 | 备选 |
| Tkinter | 内置、轻量 | 界面简陋、功能有限 | ❌ |
| wxPython | 原生外观 | 安装复杂、文档较少 | ❌ |

#### IEC61850库

使用[libiec61850](https://github.com/mz-automation/libiec61850)，改库为C语言实现，功能齐全，且自带Python接口

---

## 4. 模块设计

### 4.1 模块划分

```
src/
├── core/                    # 核心模块
│   ├── __init__.py
│   └── data_model.py        # 数据模型定义
│
├── server/                  # 服务端模块
│   ├── __init__.py
│   └── iec61850_server.py   # 服务端实现
│
├── client/                  # 客户端模块
│   ├── __init__.py
│   └── iec61850_client.py   # 客户端实现
│
└── gui/                     # GUI模块
    ├── __init__.py
    ├── main_window.py       # 主窗口
    ├── server_panel.py      # 服务端面板
    ├── client_panel.py      # 客户端面板
    ├── data_tree_widget.py  # 数据树控件
    └── log_widget.py        # 日志控件
```

### 4.2 核心模块 (core)

#### 4.2.1 data_model.py

**职责**: 实现 IEC61850 数据模型层次结构

**核心类**:

```
┌─────────────────────────────────────────────────────────────┐
│                       DataModelManager                       │
│  - ieds: Dict[str, IED]                                     │
│  + load_from_yaml(path) -> IED                              │
│  + create_default_ied(name) -> IED                          │
│  + export_to_yaml(ied, path) -> bool                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                           IED                                │
│  - name: str                                                 │
│  - manufacturer: str                                         │
│  - logical_devices: Dict[str, LogicalDevice]                │
│  + add_logical_device(ld) -> LogicalDevice                  │
│  + get_data_attribute(reference) -> DataAttribute           │
│  + get_all_references() -> List[str]                        │
│  + to_dict() -> Dict                                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      LogicalDevice                           │
│  - name: str                                                 │
│  - description: str                                          │
│  - logical_nodes: Dict[str, LogicalNode]                    │
│  + add_logical_node(ln) -> LogicalNode                      │
│  + reference -> str (property)                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       LogicalNode                            │
│  - name: str                                                 │
│  - ln_class: str (PTOC, XCBR, MMXU, etc.)                  │
│  - data_objects: Dict[str, DataObject]                      │
│  + add_data_object(do) -> DataObject                        │
│  + get_all_attributes() -> List[DataAttribute]              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       DataObject                             │
│  - name: str                                                 │
│  - cdc: str (SPS, DPS, MV, etc.)                           │
│  - attributes: Dict[str, DataAttribute]                     │
│  + add_attribute(da) -> DataAttribute                       │
│  + get_value(attr_name) -> Any                              │
│  + set_value(attr_name, value) -> bool                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      DataAttribute                           │
│  - name: str                                                 │
│  - data_type: DataType                                       │
│  - value: Any                                                │
│  - fc: FunctionalConstraint                                  │
│  - quality: Quality                                          │
│  - timestamp: datetime                                       │
│  + set_value(value, update_timestamp) -> bool               │
│  + add_callback(callback)                                    │
│  + reference -> str (property)                              │
└─────────────────────────────────────────────────────────────┘
```

**枚举类型**:

```python
class DataType(Enum):
    BOOLEAN = "BOOLEAN"
    INT32 = "INT32"
    FLOAT32 = "FLOAT32"
    ENUM = "Enum"
    DBPOS = "Dbpos"
    QUALITY = "Quality"
    TIMESTAMP = "Timestamp"
    ANALOGUE_VALUE = "AnalogueValue"
    # ...

class FunctionalConstraint(Enum):
    ST = "ST"  # Status
    MX = "MX"  # Measured values
    SP = "SP"  # Setpoint
    CO = "CO"  # Control
    # ...

class Quality(IntEnum):
    GOOD = 0
    INVALID = 1
    QUESTIONABLE = 3
    # ...
```

### 4.3 服务端模块 (server)

#### 4.3.1 iec61850_server.py

**职责**: 实现 IED 仿真服务器

**类图**:

```
┌─────────────────────────────────────────────────────────────┐
│                     IEC61850Server                           │
├─────────────────────────────────────────────────────────────┤
│  - config: ServerConfig                                      │
│  - state: ServerState                                        │
│  - ied: IED                                                  │
│  - _server_socket: socket                                    │
│  - _clients: Dict[str, ClientConnection]                    │
│  - _accept_thread: Thread                                    │
│  - _update_thread: Thread                                    │
├─────────────────────────────────────────────────────────────┤
│  + start() -> bool                                          │
│  + stop() -> bool                                           │
│  + restart() -> bool                                        │
│  + load_ied(ied: IED)                                       │
│  + load_ied_from_yaml(path: str) -> bool                    │
│  + get_data_value(reference: str) -> Any                    │
│  + set_data_value(reference: str, value: Any) -> bool       │
│  + get_connected_clients() -> List[Dict]                    │
│  + get_status() -> Dict                                     │
│  + on_state_change(callback)                                │
│  + on_connection_change(callback)                           │
│  + on_data_change(callback)                                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      ServerConfig                            │
├─────────────────────────────────────────────────────────────┤
│  - ip_address: str = "0.0.0.0"                              │
│  - port: int = 102                                          │
│  - max_connections: int = 10                                │
│  - update_interval_ms: int = 1000                           │
│  - enable_random_values: bool = False                       │
│  - enable_reporting: bool = True                            │
│  - enable_goose: bool = False                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    ClientConnection                          │
├─────────────────────────────────────────────────────────────┤
│  - id: str                                                   │
│  - address: Tuple[str, int]                                 │
│  - socket: socket                                            │
│  - connected_at: datetime                                    │
│  - last_activity: datetime                                   │
│  - subscriptions: Set[str]                                  │
└─────────────────────────────────────────────────────────────┘
```

**状态机**:

```
                    ┌─────────┐
                    │ STOPPED │◄───────────────┐
                    └────┬────┘                │
                         │ start()             │
                         ▼                     │
                    ┌─────────┐                │
                    │STARTING │                │
                    └────┬────┘                │
                         │ success             │ stop()
                         ▼                     │
                    ┌─────────┐                │
          ┌────────│ RUNNING │────────────────┤
          │        └────┬────┘                │
          │             │ stop()              │
          │             ▼                     │
          │        ┌─────────┐                │
          │        │STOPPING │────────────────┘
          │        └─────────┘
          │ error
          ▼
     ┌─────────┐
     │  ERROR  │
     └─────────┘
```

### 4.4 客户端模块 (client)

#### 4.4.1 iec61850_client.py

**职责**: 实现 IEC61850 客户端功能

**类图**:

```
┌─────────────────────────────────────────────────────────────┐
│                     IEC61850Client                           │
├─────────────────────────────────────────────────────────────┤
│  - config: ClientConfig                                      │
│  - state: ClientState                                        │
│  - _connection: ConnectionInfo                               │
│  - _socket: socket                                           │
│  - _server_directory: ServerDirectory                       │
│  - _cached_values: Dict[str, DataValue]                     │
│  - _subscriptions: Dict[str, Callable]                      │
├─────────────────────────────────────────────────────────────┤
│  + connect(host, port, name) -> bool                        │
│  + disconnect() -> bool                                      │
│  + reconnect() -> bool                                       │
│  + get_server_info() -> Dict                                │
│  + get_logical_devices() -> List[str]                       │
│  + browse_data_model() -> Dict                              │
│  + read_value(reference) -> DataValue                       │
│  + read_values(references) -> Dict[str, DataValue]          │
│  + write_value(reference, value) -> bool                    │
│  + operate(reference, value) -> bool                        │
│  + select_before_operate(reference) -> bool                 │
│  + subscribe(reference, callback)                           │
│  + unsubscribe(reference)                                    │
│  + on_state_change(callback)                                │
│  + on_data_change(callback)                                 │
└─────────────────────────────────────────────────────────────┘
```

### 4.5 GUI模块 (gui)

#### 4.5.1 组件层次

```
MainWindow
├── MenuBar
│   ├── 文件菜单 (加载/保存配置, 退出)
│   ├── 视图菜单 (日志面板, 清除日志)
│   └── 帮助菜单 (关于)
│
├── ToolBar
│   ├── 启动/停止按钮
│   └── 刷新按钮
│
├── ModeSelector (服务端/客户端模式切换)
│
├── PanelStack (QStackedWidget)
│   ├── ServerPanel
│   │   ├── ConfigGroup (服务器配置)
│   │   ├── ControlGroup (启动/停止)
│   │   ├── IEDGroup (数据模型管理)
│   │   ├── ClientGroup (客户端连接列表)
│   │   └── DataView (数据浏览/编辑)
│   │
│   └── ClientPanel
│       ├── ConnectionGroup (连接配置)
│       ├── ServerInfoGroup (服务器信息)
│       ├── OperationGroup (读写操作)
│       └── DataView (数据浏览/订阅)
│
├── LogWidget (日志面板)
│
└── StatusBar (状态栏)
```

#### 4.5.2 信号与槽连接

```
┌─────────────┐                    ┌─────────────┐
│ ServerPanel │                    │   Server    │
│             │─── start_server ──►│             │
│             │◄── state_changed ──│             │
│             │◄── data_changed ───│             │
│             │◄── log_message ────│             │
└─────────────┘                    └─────────────┘

┌─────────────┐                    ┌─────────────┐
│ ClientPanel │                    │   Client    │
│             │─── connect ───────►│             │
│             │◄── state_changed ──│             │
│             │◄── data_changed ───│             │
└─────────────┘                    └─────────────┘

┌─────────────┐                    ┌─────────────┐
│DataTreeWidget│                   │   Panel     │
│             │◄── load_ied ───────│             │
│             │─── value_changed ─►│             │
│             │─── item_selected ─►│             │
└─────────────┘                    └─────────────┘
```

---

## 5. 数据模型设计

### 5.1 IEC61850 数据层次

```
┌─────────────────────────────────────────────────────────────┐
│                           IED                                │
│                   (Intelligent Electronic Device)            │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐    │
│  │                    Logical Device                    │    │
│  │                  (如: PROT, MEAS, CTRL)              │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │  ┌─────────────────────────────────────────────┐    │    │
│  │  │              Logical Node                    │    │    │
│  │  │          (如: LLN0, PTOC1, XCBR1)           │    │    │
│  │  ├─────────────────────────────────────────────┤    │    │
│  │  │  ┌─────────────────────────────────────┐    │    │    │
│  │  │  │          Data Object                 │    │    │    │
│  │  │  │       (如: Pos, Op, TotW)           │    │    │    │
│  │  │  ├─────────────────────────────────────┤    │    │    │
│  │  │  │  ┌─────────────────────────────┐    │    │    │    │
│  │  │  │  │     Data Attribute          │    │    │    │    │
│  │  │  │  │   (如: stVal, q, t)         │    │    │    │    │
│  │  │  │  └─────────────────────────────┘    │    │    │    │
│  │  │  └─────────────────────────────────────┘    │    │    │
│  │  └─────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 数据引用格式

```
完整引用格式: IEDName + LDName / LNName . DOName . DAName

示例:
  SimulatedIEDPROT/PTOC1.Op.general
  │          │    │    │  │
  │          │    │    │  └── Data Attribute (数据属性)
  │          │    │    └───── Data Object (数据对象)
  │          │    └────────── Logical Node (逻辑节点)
  │          └─────────────── Logical Device (逻辑设备)
  └────────────────────────── IED Name (设备名称)
```

### 5.3 常用逻辑节点类

| 类别 | LN Class | 说明 |
|------|----------|------|
| 系统 | LLN0 | 逻辑节点零 |
| 系统 | LPHD | 物理设备信息 |
| 保护 | PTOC | 过流保护 |
| 保护 | PDIS | 距离保护 |
| 保护 | PDIF | 差动保护 |
| 开关设备 | XCBR | 断路器 |
| 开关设备 | XSWI | 隔离开关 |
| 测量 | MMXU | 测量单元 |
| 测量 | MMTR | 电度表 |
| 控制 | CSWI | 开关控制 |

### 5.4 常用公共数据类 (CDC)

| CDC | 说明 | 典型属性 |
|-----|------|----------|
| SPS | 单点状态 | stVal, q, t |
| DPS | 双点状态 | stVal, q, t |
| INS | 整数状态 | stVal, q, t |
| ENS | 枚举状态 | stVal, q, t |
| ACT | 保护动作 | general, phsA/B/C, q, t |
| ACD | 保护启动 | general, dirGeneral, q, t |
| SPC | 单点控制 | stVal, ctlModel, Oper |
| DPC | 双点控制 | stVal, ctlModel, Oper |
| MV | 测量值 | mag, q, t, units |
| CMV | 复数测量值 | cVal, q, t |
| WYE | 三相测量 | phsA, phsB, phsC |
| ENC | 枚举控制 | stVal, ctlModel |

### 5.5 默认数据模型

```yaml
SimulatedIED
├── PROT (保护逻辑设备)
│   ├── LLN0
│   │   ├── Mod (ENC) - 模式
│   │   │   ├── stVal: Enum = 1
│   │   │   ├── q: Quality = 0
│   │   │   └── t: Timestamp
│   │   ├── Beh (ENS) - 行为
│   │   │   ├── stVal: Enum = 1
│   │   │   └── q: Quality = 0
│   │   └── Health (ENS) - 健康
│   │
│   ├── LPHD1
│   │   ├── PhyNam (DPL) - 物理名称
│   │   ├── PhyHealth (ENS)
│   │   └── Proxy (SPS)
│   │
│   ├── PTOC1 (过流保护)
│   │   ├── Mod (ENC)
│   │   ├── Beh (ENS)
│   │   ├── Op (ACT) - 动作
│   │   │   ├── general: BOOLEAN = false
│   │   │   ├── phsA: BOOLEAN = false
│   │   │   ├── phsB: BOOLEAN = false
│   │   │   ├── phsC: BOOLEAN = false
│   │   │   ├── q: Quality = 0
│   │   │   └── t: Timestamp
│   │   └── Str (ACD) - 启动
│   │
│   └── XCBR1 (断路器)
│       ├── Mod (ENC)
│       ├── Beh (ENS)
│       ├── Pos (DPC) - 位置
│       │   ├── stVal: Dbpos = 2 (ON)
│       │   ├── q: Quality = 0
│       │   ├── t: Timestamp
│       │   └── ctlModel: Enum = 2
│       ├── BlkOpn (SPC) - 闭锁分闸
│       └── BlkCls (SPC) - 闭锁合闸
│
└── MEAS (测量逻辑设备)
    ├── LLN0
    │   ├── Mod (ENC)
    │   └── Beh (ENS)
    │
    └── MMXU1 (测量单元)
        ├── Mod (ENC)
        ├── Beh (ENS)
        ├── TotW (MV) - 总有功功率
        │   ├── mag: AnalogueValue = 1000.0
        │   ├── q: Quality = 0
        │   ├── t: Timestamp
        │   └── units: Unit = "W"
        ├── TotVAr (MV) - 总无功功率
        ├── Hz (MV) - 频率
        │   ├── mag: AnalogueValue = 50.0
        │   └── units: Unit = "Hz"
        ├── PPV (WYE) - 相间电压
        │   ├── phsAB: CMV
        │   ├── phsBC: CMV
        │   └── phsCA: CMV
        └── A (WYE) - 相电流
            ├── phsA: CMV
            ├── phsB: CMV
            └── phsC: CMV
```

---

## 6. 通信协议设计

### 6.1 消息格式

本仿真器使用简化的二进制协议模拟 MMS 通信:

```
┌─────────────────────────────────────────────────────────┐
│                     Message Format                       │
├──────────┬──────────┬───────────────────────────────────┤
│ Type (1B)│Length(2B)│           Payload (N bytes)       │
├──────────┼──────────┼───────────────────────────────────┤
│  0x01    │  0x00 0F │  {"key": "value", ...}           │
└──────────┴──────────┴───────────────────────────────────┘
```

### 6.2 消息类型

| 类型码 | 名称 | 方向 | 说明 |
|--------|------|------|------|
| 0x01 | GET_SERVER_DIRECTORY | C→S | 获取服务器目录 |
| 0x02 | GET_LD_DIRECTORY | C→S | 获取逻辑设备目录 |
| 0x03 | GET_LN_DIRECTORY | C→S | 获取逻辑节点目录 |
| 0x04 | GET_DATA_VALUES | C→S | 读取数据值 |
| 0x05 | SET_DATA_VALUES | C→S | 写入数据值 |
| 0x06 | GET_DATA_DEFINITION | C→S | 获取数据定义 |
| 0x10 | SELECT | C→S | SBO选择 |
| 0x11 | OPERATE | C→S | 执行控制 |
| 0x12 | CANCEL | C→S | 取消控制 |
| 0x20 | ENABLE_REPORTING | C→S | 启用报告 |
| 0x21 | DISABLE_REPORTING | C→S | 禁用报告 |
| 0x80 | RESPONSE_OK | S→C | 成功响应 |
| 0x81 | RESPONSE_ERROR | S→C | 错误响应 |
| 0x82 | REPORT_DATA | S→C | 报告数据 |
| 0xF0 | HEARTBEAT | 双向 | 心跳 |
| 0xFF | DISCONNECT | 双向 | 断开连接 |

### 6.3 请求/响应示例

#### 获取服务器目录

**请求**:
```
Type: 0x01
Length: 0
Payload: (empty)
```

**响应**:
```json
{
  "ied_name": "SimulatedIED",
  "manufacturer": "IEC61850Simulator",
  "model": "VirtualIED",
  "revision": "1.0",
  "logical_devices": ["PROT", "MEAS"]
}
```

#### 读取数据值

**请求**:
```json
["SimulatedIEDPROT/XCBR1.Pos.stVal", "SimulatedIEDMEAS/MMXU1.TotW.mag"]
```

**响应**:
```json
{
  "SimulatedIEDPROT/XCBR1.Pos.stVal": {
    "value": 2,
    "quality": 0,
    "timestamp": "2026-01-22T10:30:00.000"
  },
  "SimulatedIEDMEAS/MMXU1.TotW.mag": {
    "value": 1000.5,
    "quality": 0,
    "timestamp": "2026-01-22T10:30:00.000"
  }
}
```

#### 控制操作

**请求**:
```json
{
  "reference": "SimulatedIEDPROT/XCBR1.Pos.stVal",
  "value": 1,
  "timestamp": "2026-01-22T10:30:00.000"
}
```

**响应**:
```json
{
  "reference": "SimulatedIEDPROT/XCBR1.Pos.stVal",
  "success": true,
  "timestamp": "2026-01-22T10:30:00.001"
}
```

### 6.4 连接管理

```
┌────────┐                              ┌────────┐
│ Client │                              │ Server │
└───┬────┘                              └───┬────┘
    │                                       │
    │──────── TCP Connect ─────────────────►│
    │                                       │
    │──────── GET_SERVER_DIRECTORY ────────►│
    │◄─────── RESPONSE_OK ──────────────────│
    │                                       │
    │──────── GET_LD_DIRECTORY ────────────►│
    │◄─────── RESPONSE_OK ──────────────────│
    │                                       │
    │──────── GET_DATA_VALUES ─────────────►│
    │◄─────── RESPONSE_OK ──────────────────│
    │                                       │
    │◄─────── HEARTBEAT ────────────────────│
    │──────── HEARTBEAT ───────────────────►│
    │                                       │
    │──────── DISCONNECT ──────────────────►│
    │                                       │
```

---

## 7. GUI设计

### 7.1 主窗口布局

```
┌─────────────────────────────────────────────────────────────────┐
│ 文件(F)  视图(V)  帮助(H)                                        │
├─────────────────────────────────────────────────────────────────┤
│ [▶ 启动] [⏹ 停止] [🔄 刷新]                    │ 工具栏          │
├─────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 选择模式:  [🖥️ 服务端模式]  [💻 客户端模式]                 │ │
│ │            ─────────────     ─────────────                  │ │
│ │                        仿真IED设备，提供MMS服务端功能        │ │
│ └─────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│ ┌──────────────────────┬────────────────────────────────────┐   │
│ │                      │                                    │   │
│ │    配置面板          │          数据视图                   │   │
│ │                      │                                    │   │
│ │  ┌────────────────┐  │  ┌──────────────────────────────┐  │   │
│ │  │ 服务器配置     │  │  │ 📊 数据浏览 | ✏️ 编辑 | 🎛️ 仿真│  │   │
│ │  │ IP: [0.0.0.0 ] │  │  ├──────────────────────────────┤  │   │
│ │  │ 端口: [102   ] │  │  │ 🔍 搜索...  [展开] [折叠]    │  │   │
│ │  │ 最大连接: [10] │  │  ├──────────────────────────────┤  │   │
│ │  └────────────────┘  │  │ ▼ SimulatedIED               │  │   │
│ │                      │  │   ▼ PROT                     │  │   │
│ │  ┌────────────────┐  │  │     ▼ LLN0                   │  │   │
│ │  │ 服务控制       │  │  │       ▼ Mod (ENC)            │  │   │
│ │  │ [▶ 启动服务]   │  │  │         stVal: 1             │  │   │
│ │  │ [⏹ 停止服务]   │  │  │         q: Good              │  │   │
│ │  │ 状态: 已停止   │  │  │     ▼ PTOC1                  │  │   │
│ │  └────────────────┘  │  │     ▼ XCBR1                  │  │   │
│ │                      │  │   ▼ MEAS                     │  │   │
│ │  ┌────────────────┐  │  │     ▼ MMXU1                  │  │   │
│ │  │ IED数据模型    │  │  └──────────────────────────────┘  │   │
│ │  │ 名称:[Simul..] │  │                                    │   │
│ │  │ [加载] [创建]  │  │  ┌──────────────────────────────┐  │   │
│ │  └────────────────┘  │  │ 选中项详情                    │  │   │
│ │                      │  │ 引用: ...PROT/XCBR1.Pos.stVal│  │   │
│ │  ┌────────────────┐  │  │ 值: 2                        │  │   │
│ │  │ 客户端连接     │  │  │ 质量: Good                   │  │   │
│ │  │ 连接数: 0      │  │  └──────────────────────────────┘  │   │
│ │  └────────────────┘  │                                    │   │
│ └──────────────────────┴────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 📋 日志                           级别:[DEBUG▼] [自动滚动✓] │ │
│ ├─────────────────────────────────────────────────────────────┤ │
│ │ [10:30:00] [INFO    ] Server started on 0.0.0.0:102        │ │
│ │ [10:30:05] [INFO    ] Client connected: 192.168.1.100      │ │
│ │ [10:30:06] [DEBUG   ] GET_SERVER_DIRECTORY request         │ │
│ └─────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│ 模式: 服务端 | 状态: 运行中 |              IED: SimulatedIED   │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 颜色方案

| 元素 | 颜色 | 用途 |
|------|------|------|
| 主题色 | #0078d4 | 选中按钮、重要操作 |
| 成功 | #28a745 | 启动按钮、成功状态 |
| 危险 | #dc3545 | 停止按钮、错误状态 |
| 警告 | #ffc107 | 警告信息 |
| 信息 | #17a2b8 | 一般信息 |
| IED | #000000 | IED节点 |
| LD | #0066cc | 逻辑设备节点 |
| LN | #006600 | 逻辑节点 |
| DO | #996600 | 数据对象 |
| DA | #000000 | 数据属性 |

### 7.3 交互设计

#### 模式切换
- 点击模式按钮切换服务端/客户端模式
- 切换时停止当前服务/连接
- 保留配置信息

#### 数据树操作
- 单击选中节点，显示详情
- 双击DA节点读取最新值
- 右键菜单：复制引用、复制值、修改值
- 支持搜索过滤
- 值变化高亮显示（黄色背景1秒）

#### 控制操作
- 双击确认机制防误操作
- 操作结果即时反馈
- 支持快捷控制按钮

---

## 8. 配置管理

### 8.1 配置文件结构

```yaml
# config/config.yaml

application:
  name: "IEC61850 Simulator"
  version: "1.0.0"
  language: "zh-CN"
  theme: "fusion"

server:
  network:
    ip_address: "0.0.0.0"
    port: 102
    max_connections: 10
  
  ied:
    name: "SimulatedIED"
    manufacturer: "IEC61850Simulator"
    
  simulation:
    update_interval_ms: 1000
    enable_random_values: false
    
  reporting:
    enabled: true
    buffer_size: 100

client:
  connection:
    timeout_ms: 5000
    retry_count: 3
    
  subscription:
    polling_interval_ms: 1000
    
  saved_servers:
    - name: "本地服务器"
      ip: "127.0.0.1"
      port: 102

logging:
  level: "DEBUG"
  file_enabled: true
  file_path: "logs/simulator.log"

gui:
  window:
    width: 1400
    height: 900
  data_view:
    refresh_rate_ms: 500
```

### 8.2 数据模型配置

```yaml
# config/data_model.yaml

ied:
  name: "ProtectionIED"
  description: "保护装置仿真器"
  
  logical_devices:
    - name: "PROT"
      description: "保护逻辑设备"
      
      logical_nodes:
        - name: "PTOC1"
          class: "PTOC"
          description: "过流保护"
          data_objects:
            - name: "Op"
              cdc: "ACT"
              data_attributes:
                - name: "general"
                  type: "BOOLEAN"
                  value: false
                - name: "q"
                  type: "Quality"
                  value: 0
```

---

## 9. 接口设计

### 9.1 服务端API

```python
class IEC61850Server:
    # 生命周期
    def start(self) -> bool: ...
    def stop(self) -> bool: ...
    def restart(self) -> bool: ...
    
    # IED管理
    def load_ied(self, ied: IED) -> None: ...
    def load_ied_from_yaml(self, path: str) -> bool: ...
    
    # 数据操作
    def get_data_value(self, reference: str) -> Any: ...
    def set_data_value(self, reference: str, value: Any) -> bool: ...
    
    # 状态查询
    def get_status(self) -> Dict: ...
    def get_connected_clients(self) -> List[Dict]: ...
    
    # 事件回调
    def on_state_change(self, callback: Callable[[ServerState], None]): ...
    def on_connection_change(self, callback: Callable[[str, bool], None]): ...
    def on_data_change(self, callback: Callable[[str, Any, Any], None]): ...
    def on_log(self, callback: Callable[[str, str], None]): ...
```

### 9.2 客户端API

```python
class IEC61850Client:
    # 连接管理
    def connect(self, host: str, port: int = 102, name: str = "") -> bool: ...
    def disconnect(self) -> bool: ...
    def reconnect(self) -> bool: ...
    def is_connected(self) -> bool: ...
    
    # 数据模型浏览
    def get_server_info(self) -> Optional[Dict]: ...
    def get_logical_devices(self) -> List[str]: ...
    def get_logical_device_directory(self, ld_name: str) -> Optional[Dict]: ...
    def browse_data_model(self) -> Dict: ...
    
    # 数据读写
    def read_value(self, reference: str) -> Optional[DataValue]: ...
    def read_values(self, references: List[str]) -> Dict[str, DataValue]: ...
    def write_value(self, reference: str, value: Any) -> bool: ...
    def write_values(self, updates: Dict[str, Any]) -> Dict[str, bool]: ...
    
    # 控制操作
    def select_before_operate(self, reference: str) -> bool: ...
    def operate(self, reference: str, value: Any) -> bool: ...
    def cancel(self, reference: str) -> bool: ...
    
    # 订阅
    def subscribe(self, reference: str, callback: Callable): ...
    def unsubscribe(self, reference: str): ...
    
    # 事件回调
    def on_state_change(self, callback: Callable[[ClientState], None]): ...
    def on_data_change(self, callback: Callable[[str, Any], None]): ...
```

### 9.3 数据模型API

```python
class DataModelManager:
    def load_from_yaml(self, path: str) -> Optional[IED]: ...
    def create_default_ied(self, name: str = "SimulatedIED") -> IED: ...
    def export_to_yaml(self, ied: IED, path: str) -> bool: ...
    def get_ied(self, name: str) -> Optional[IED]: ...

class IED:
    def add_logical_device(self, ld: LogicalDevice) -> LogicalDevice: ...
    def get_logical_device(self, name: str) -> Optional[LogicalDevice]: ...
    def get_data_attribute(self, reference: str) -> Optional[DataAttribute]: ...
    def get_all_references(self) -> List[str]: ...
    def to_dict(self) -> Dict: ...

class DataAttribute:
    def set_value(self, value: Any, update_timestamp: bool = True) -> bool: ...
    def add_callback(self, callback: Callable): ...
    def remove_callback(self, callback: Callable): ...
    @property
    def reference(self) -> str: ...
```

---

## 10. 部署方案

### 10.1 开发环境部署

```bash
# 1. 克隆项目
git clone <repository_url>
cd iec61850_simulator

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
.\venv\Scripts\activate   # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 运行
python main.py
```

### 10.2 生产环境部署

#### 打包为可执行文件

```bash
# 使用 PyInstaller
pip install pyinstaller

pyinstaller --name="IEC61850Simulator" \
            --windowed \
            --icon=resources/icon.ico \
            --add-data="config:config" \
            main.py
```

#### Docker 部署 (无界面服务器)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 102

CMD ["python", "main.py", "--headless", "-H", "0.0.0.0", "-p", "102"]
```

### 10.3 系统要求

| 项目 | 最低要求 | 推荐配置 |
|------|----------|----------|
| 操作系统 | Windows 10 / Ubuntu 20.04 / macOS 10.15 | 最新版本 |
| Python | 3.9 | 3.11+ |
| 内存 | 512MB | 2GB |
| 磁盘 | 100MB | 500MB |
| 显示器 | 1280x720 | 1920x1080 |

---

## 11. 扩展性设计

### 11.1 插件架构 (规划中)

```
┌─────────────────────────────────────────────────────────────┐
│                     Plugin Manager                           │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ Protocol    │  │ Data Model  │  │ GUI         │         │
│  │ Plugins     │  │ Plugins     │  │ Plugins     │         │
│  ├─────────────┤  ├─────────────┤  ├─────────────┤         │
│  │ - GOOSE     │  │ - SCL Parser│  │ - Charts    │         │
│  │ - SV        │  │ - Custom LN │  │ - Reports   │         │
│  │ - MMS Full  │  │ - Templates │  │ - Themes    │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

### 11.2 协议扩展点

| 扩展点 | 描述 | 接口 |
|--------|------|------|
| 消息处理器 | 自定义消息类型处理 | `MessageHandler` |
| 协议编解码 | 自定义协议格式 | `ProtocolCodec` |
| 认证模块 | 自定义认证机制 | `Authenticator` |

### 11.3 数据模型扩展点

| 扩展点 | 描述 | 接口 |
|--------|------|------|
| 自定义CDC | 添加新的公共数据类 | `CDCDefinition` |
| 自定义LN | 添加新的逻辑节点类 | `LNTemplate` |
| 数据验证 | 自定义数据验证规则 | `DataValidator` |

### 11.4 后续开发计划

| 阶段 | 功能 | 优先级 |
|------|------|--------|
| Phase 2 | 集成 libiec61850 完整 MMS 实现 | 高 |
| Phase 2 | SCL/ICD/CID 文件导入导出 | 高 |
| Phase 3 | GOOSE 发布/订阅 | 中 |
| Phase 3 | 采样值 (SV) 支持 | 中 |
| Phase 4 | 时间同步 (SNTP) | 低 |
| Phase 4 | 安全认证 (TLS) | 低 |
| Phase 5 | 数据趋势图表 | 低 |
| Phase 5 | 报表生成 | 低 |

---

## 附录

### A. 参考标准

- IEC 61850-1: 概述和原则
- IEC 61850-5: 功能和设备模型的通信要求
- IEC 61850-6: 变电站自动化系统配置语言
- IEC 61850-7-1: 基本通信结构 - 原则和模型
- IEC 61850-7-2: 基本通信结构 - ACSI
- IEC 61850-7-3: 公共数据类
- IEC 61850-7-4: 兼容的逻辑节点类和数据类
- IEC 61850-8-1: 特定通信服务映射 - MMS

### B. 术语表

| 术语 | 说明 |
|------|------|
| ACSI | Abstract Communication Service Interface - 抽象通信服务接口 |
| CDC | Common Data Class - 公共数据类 |
| DA | Data Attribute - 数据属性 |
| DO | Data Object - 数据对象 |
| FC | Functional Constraint - 功能约束 |
| GOOSE | Generic Object Oriented Substation Event - 通用面向对象变电站事件 |
| IED | Intelligent Electronic Device - 智能电子设备 |
| LD | Logical Device - 逻辑设备 |
| LN | Logical Node - 逻辑节点 |
| MMS | Manufacturing Message Specification - 制造报文规范 |
| SBO | Select Before Operate - 选择后执行 |
| SCL | Substation Configuration Language - 变电站配置语言 |
| SV | Sampled Values - 采样值 |

### C. 修订历史

| 版本 | 日期 | 作者 | 说明 |
|------|------|------|------|
| 1.0.0 | 2026-01-22 | IEC61850 Simulator Team | 初始版本 |

---

