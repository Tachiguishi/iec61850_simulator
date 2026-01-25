"""
IEC61850 Server Implementation
==============================

实现IEC61850服务端功能，包括：
- MMS协议服务器
- 数据点管理
- 客户端连接管理
- 报告和GOOSE发布

注意：这是一个仿真实现，使用TCP socket模拟MMS协议。
完整的MMS实现需要使用libiec61850库。
"""

from __future__ import annotations

import asyncio
import json
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from queue import Queue

from loguru import logger

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.data_model import (
    IED, LogicalDevice, LogicalNode, DataObject, DataAttribute,
    DataModelManager, DataType, Quality, FunctionalConstraint
)


class ServerState(Enum):
    """服务器状态"""
    STOPPED = auto()
    STARTING = auto()
    RUNNING = auto()
    STOPPING = auto()
    ERROR = auto()


@dataclass
class ServerConfig:
    """服务器配置"""
    ip_address: str = "0.0.0.0"
    port: int = 102
    max_connections: int = 10
    update_interval_ms: int = 1000
    enable_random_values: bool = False
    enable_reporting: bool = True
    enable_goose: bool = False
    
    @classmethod
    def from_dict(cls, data: Dict) -> ServerConfig:
        """从字典创建配置"""
        return cls(
            ip_address=data.get("ip_address", "0.0.0.0"),
            port=data.get("port", 102),
            max_connections=data.get("max_connections", 10),
            update_interval_ms=data.get("update_interval_ms", 1000),
            enable_random_values=data.get("enable_random_values", False),
            enable_reporting=data.get("enable_reporting", True),
            enable_goose=data.get("enable_goose", False),
        )


@dataclass
class ClientConnection:
    """客户端连接信息"""
    id: str
    address: Tuple[str, int]
    socket: socket.socket
    connected_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    subscriptions: Set[str] = field(default_factory=set)
    
    def __hash__(self):
        return hash(self.id)


class MessageType(Enum):
    """消息类型"""
    # 请求类型
    GET_SERVER_DIRECTORY = 0x01
    GET_LOGICAL_DEVICE_DIRECTORY = 0x02
    GET_LOGICAL_NODE_DIRECTORY = 0x03
    GET_DATA_VALUES = 0x04
    SET_DATA_VALUES = 0x05
    GET_DATA_DEFINITION = 0x06
    
    # 控制操作
    SELECT = 0x10
    OPERATE = 0x11
    CANCEL = 0x12
    
    # 报告
    ENABLE_REPORTING = 0x20
    DISABLE_REPORTING = 0x21
    GET_REPORT = 0x22
    
    # 响应
    RESPONSE_OK = 0x80
    RESPONSE_ERROR = 0x81
    REPORT_DATA = 0x82
    
    # 系统
    HEARTBEAT = 0xF0
    DISCONNECT = 0xFF


class IEC61850Server:
    """
    IEC61850服务端仿真器
    
    提供以下功能：
    - 启动/停止MMS服务
    - 管理IED数据模型
    - 处理客户端请求
    - 数据值仿真更新
    - 报告生成
    """
    
    def __init__(self, config: Optional[ServerConfig] = None):
        """
        初始化服务器
        
        Args:
            config: 服务器配置
        """
        self.config = config or ServerConfig()
        self.state = ServerState.STOPPED
        
        # 数据模型
        self.data_model_manager = DataModelManager()
        self.ied: Optional[IED] = None
        
        # 网络
        self._server_socket: Optional[socket.socket] = None
        self._clients: Dict[str, ClientConnection] = {}
        self._client_lock = threading.Lock()
        
        # 线程
        self._accept_thread: Optional[threading.Thread] = None
        self._update_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # 回调
        self._state_callbacks: List[Callable[[ServerState], None]] = []
        self._connection_callbacks: List[Callable[[str, bool], None]] = []
        self._data_callbacks: List[Callable[[str, Any, Any], None]] = []
        self._log_callbacks: List[Callable[[str, str], None]] = []
        
        # 消息队列
        self._message_queue: Queue = Queue()
        
    # ========================================================================
    # 生命周期管理
    # ========================================================================
    
    def start(self) -> bool:
        """
        启动服务器
        
        Returns:
            是否成功启动
        """
        if self.state == ServerState.RUNNING:
            self._log("warning", "Server is already running")
            return False
        
        if self.ied is None:
            self._log("warning", "No IED configured, creating default")
            self.ied = self.data_model_manager.create_default_ied()
        
        try:
            self._set_state(ServerState.STARTING)
            self._stop_event.clear()
            
            # 创建服务器socket
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind((self.config.ip_address, self.config.port))
            self._server_socket.listen(self.config.max_connections)
            self._server_socket.settimeout(1.0)
            
            # 启动接受连接线程
            self._accept_thread = threading.Thread(
                target=self._accept_connections,
                name="IEC61850-Accept",
                daemon=True
            )
            self._accept_thread.start()
            
            # 启动数据更新线程
            self._update_thread = threading.Thread(
                target=self._update_loop,
                name="IEC61850-Update",
                daemon=True
            )
            self._update_thread.start()
            
            self._set_state(ServerState.RUNNING)
            self._log("info", f"Server started on {self.config.ip_address}:{self.config.port}")
            return True
            
        except Exception as e:
            self._log("error", f"Failed to start server: {e}")
            self._set_state(ServerState.ERROR)
            return False
    
    def stop(self) -> bool:
        """
        停止服务器
        
        Returns:
            是否成功停止
        """
        if self.state == ServerState.STOPPED:
            return True
        
        try:
            self._set_state(ServerState.STOPPING)
            self._stop_event.set()
            
            # 断开所有客户端
            with self._client_lock:
                for client in list(self._clients.values()):
                    self._disconnect_client(client.id)
            
            # 关闭服务器socket
            if self._server_socket:
                self._server_socket.close()
                self._server_socket = None
            
            # 等待线程结束
            if self._accept_thread and self._accept_thread.is_alive():
                self._accept_thread.join(timeout=2.0)
            
            if self._update_thread and self._update_thread.is_alive():
                self._update_thread.join(timeout=2.0)
            
            self._set_state(ServerState.STOPPED)
            self._log("info", "Server stopped")
            return True
            
        except Exception as e:
            self._log("error", f"Error stopping server: {e}")
            self._set_state(ServerState.ERROR)
            return False
    
    def restart(self) -> bool:
        """重启服务器"""
        self.stop()
        time.sleep(0.5)
        return self.start()
    
    # ========================================================================
    # IED管理
    # ========================================================================
    
    def load_ied(self, ied: IED):
        """加载IED数据模型"""
        self.ied = ied
        self.data_model_manager.ieds[ied.name] = ied
        self._log("info", f"Loaded IED: {ied.name}")
    
    def load_ied_from_yaml(self, yaml_path: str) -> bool:
        """从YAML文件加载IED"""
        ied = self.data_model_manager.load_from_yaml(yaml_path)
        if ied:
            self.ied = ied
            return True
        return False
    
    def get_data_value(self, reference: str) -> Optional[Any]:
        """获取数据点值"""
        if not self.ied:
            return None
        
        da = self.ied.get_data_attribute(reference)
        return da.value if da else None
    
    def set_data_value(self, reference: str, value: Any) -> bool:
        """设置数据点值"""
        if not self.ied:
            return False
        
        da = self.ied.get_data_attribute(reference)
        if da:
            old_value = da.value
            if da.set_value(value):
                self._notify_data_change(reference, old_value, value)
                return True
        return False
    
    # ========================================================================
    # 网络处理
    # ========================================================================
    
    def _accept_connections(self):
        """接受客户端连接的线程"""
        while not self._stop_event.is_set():
            try:
                if self._server_socket:
                    try:
                        client_socket, address = self._server_socket.accept()
                        self._handle_new_connection(client_socket, address)
                    except socket.timeout:
                        continue
            except Exception as e:
                if not self._stop_event.is_set():
                    self._log("error", f"Accept error: {e}")
    
    def _handle_new_connection(self, client_socket: socket.socket, address: Tuple[str, int]):
        """处理新连接"""
        client_id = f"{address[0]}:{address[1]}"
        
        with self._client_lock:
            if len(self._clients) >= self.config.max_connections:
                self._log("warning", f"Max connections reached, rejecting {client_id}")
                client_socket.close()
                return
            
            client = ClientConnection(
                id=client_id,
                address=address,
                socket=client_socket,
            )
            self._clients[client_id] = client
        
        self._log("info", f"Client connected: {client_id}")
        self._notify_connection_change(client_id, True)
        
        # 启动客户端处理线程
        thread = threading.Thread(
            target=self._handle_client,
            args=(client,),
            name=f"IEC61850-Client-{client_id}",
            daemon=True
        )
        thread.start()
    
    def _handle_client(self, client: ClientConnection):
        """处理客户端通信"""
        try:
            client.socket.settimeout(30.0)
            
            while not self._stop_event.is_set():
                try:
                    # 接收消息头
                    header = client.socket.recv(4)
                    if not header:
                        break
                    
                    if len(header) < 4:
                        continue
                    
                    msg_type, msg_len = struct.unpack(">BH", header[:3])
                    
                    # 接收消息体
                    if msg_len > 0:
                        data = client.socket.recv(msg_len)
                    else:
                        data = b""
                    
                    # 处理消息
                    response = self._process_message(client, msg_type, data)
                    
                    # 发送响应
                    if response:
                        client.socket.sendall(response)
                    
                    client.last_activity = datetime.now()
                    
                except socket.timeout:
                    # 发送心跳
                    self._send_heartbeat(client)
                except Exception as e:
                    self._log("error", f"Client {client.id} error: {e}")
                    break
                    
        finally:
            self._disconnect_client(client.id)
    
    def _process_message(self, client: ClientConnection, msg_type: int, data: bytes) -> Optional[bytes]:
        """处理客户端消息"""
        try:
            if msg_type == MessageType.GET_SERVER_DIRECTORY.value:
                return self._handle_get_server_directory()
            
            elif msg_type == MessageType.GET_LOGICAL_DEVICE_DIRECTORY.value:
                ld_name = data.decode('utf-8') if data else ""
                return self._handle_get_ld_directory(ld_name)
            
            elif msg_type == MessageType.GET_LOGICAL_NODE_DIRECTORY.value:
                path = data.decode('utf-8') if data else ""
                return self._handle_get_ln_directory(path)
            
            elif msg_type == MessageType.GET_DATA_VALUES.value:
                references = json.loads(data.decode('utf-8')) if data else []
                return self._handle_get_data_values(references)
            
            elif msg_type == MessageType.SET_DATA_VALUES.value:
                updates = json.loads(data.decode('utf-8')) if data else {}
                return self._handle_set_data_values(updates)
            
            elif msg_type == MessageType.OPERATE.value:
                control_data = json.loads(data.decode('utf-8')) if data else {}
                return self._handle_operate(control_data)
            
            elif msg_type == MessageType.ENABLE_REPORTING.value:
                report_config = json.loads(data.decode('utf-8')) if data else {}
                return self._handle_enable_reporting(client, report_config)
            
            elif msg_type == MessageType.HEARTBEAT.value:
                return self._create_response(MessageType.HEARTBEAT, b"")
            
            elif msg_type == MessageType.DISCONNECT.value:
                return None
            
            else:
                self._log("warning", f"Unknown message type: {msg_type}")
                return self._create_error_response(f"Unknown message type: {msg_type}")
                
        except Exception as e:
            self._log("error", f"Error processing message: {e}")
            return self._create_error_response(str(e))
    
    # ========================================================================
    # 消息处理器
    # ========================================================================
    
    def _handle_get_server_directory(self) -> bytes:
        """处理获取服务器目录请求"""
        if not self.ied:
            return self._create_error_response("No IED configured")
        
        directory = {
            "ied_name": self.ied.name,
            "manufacturer": self.ied.manufacturer,
            "model": self.ied.model,
            "revision": self.ied.revision,
            "logical_devices": list(self.ied.logical_devices.keys()),
        }
        
        return self._create_response(
            MessageType.RESPONSE_OK,
            json.dumps(directory).encode('utf-8')
        )
    
    def _handle_get_ld_directory(self, ld_name: str) -> bytes:
        """处理获取逻辑设备目录请求"""
        if not self.ied:
            return self._create_error_response("No IED configured")
        
        ld = self.ied.get_logical_device(ld_name)
        if not ld:
            return self._create_error_response(f"Logical device not found: {ld_name}")
        
        directory = {
            "name": ld.name,
            "description": ld.description,
            "logical_nodes": list(ld.logical_nodes.keys()),
        }
        
        return self._create_response(
            MessageType.RESPONSE_OK,
            json.dumps(directory).encode('utf-8')
        )
    
    def _handle_get_ln_directory(self, path: str) -> bytes:
        """处理获取逻辑节点目录请求"""
        if not self.ied:
            return self._create_error_response("No IED configured")
        
        # 解析路径: LD/LN
        parts = path.split("/")
        if len(parts) != 2:
            return self._create_error_response(f"Invalid path: {path}")
        
        ld_name, ln_name = parts
        
        ld = self.ied.get_logical_device(ld_name)
        if not ld:
            return self._create_error_response(f"Logical device not found: {ld_name}")
        
        ln = ld.get_logical_node(ln_name)
        if not ln:
            return self._create_error_response(f"Logical node not found: {ln_name}")
        
        directory = {
            "name": ln.name,
            "class": ln.ln_class,
            "description": ln.description,
            "data_objects": {
                do.name: {
                    "cdc": do.cdc,
                    "description": do.description,
                    "attributes": list(do.attributes.keys()),
                }
                for do in ln.data_objects.values()
            },
        }
        
        return self._create_response(
            MessageType.RESPONSE_OK,
            json.dumps(directory).encode('utf-8')
        )
    
    def _handle_get_data_values(self, references: List[str]) -> bytes:
        """处理获取数据值请求"""
        if not self.ied:
            return self._create_error_response("No IED configured")
        
        values = {}
        for ref in references:
            da = self.ied.get_data_attribute(ref)
            if da:
                values[ref] = {
                    "value": da.value,
                    "quality": da.quality,
                    "timestamp": da.timestamp.isoformat() if da.timestamp else None,
                }
            else:
                values[ref] = {"error": "Not found"}
        
        return self._create_response(
            MessageType.RESPONSE_OK,
            json.dumps(values).encode('utf-8')
        )
    
    def _handle_set_data_values(self, updates: Dict[str, Any]) -> bytes:
        """处理设置数据值请求"""
        if not self.ied:
            return self._create_error_response("No IED configured")
        
        results = {}
        for ref, value in updates.items():
            success = self.set_data_value(ref, value)
            results[ref] = "OK" if success else "Failed"
        
        return self._create_response(
            MessageType.RESPONSE_OK,
            json.dumps(results).encode('utf-8')
        )
    
    def _handle_operate(self, control_data: Dict) -> bytes:
        """处理控制操作请求"""
        reference = control_data.get("reference", "")
        value = control_data.get("value")
        
        self._log("info", f"Control operation: {reference} = {value}")
        
        success = self.set_data_value(reference, value)
        
        result = {
            "reference": reference,
            "success": success,
            "timestamp": datetime.now().isoformat(),
        }
        
        return self._create_response(
            MessageType.RESPONSE_OK,
            json.dumps(result).encode('utf-8')
        )
    
    def _handle_enable_reporting(self, client: ClientConnection, config: Dict) -> bytes:
        """处理启用报告请求"""
        references = config.get("references", [])
        
        with self._client_lock:
            client.subscriptions.update(references)
        
        self._log("info", f"Client {client.id} subscribed to: {references}")
        
        return self._create_response(
            MessageType.RESPONSE_OK,
            json.dumps({"subscribed": references}).encode('utf-8')
        )
    
    # ========================================================================
    # 工具方法
    # ========================================================================
    
    def _create_response(self, msg_type: MessageType, data: bytes) -> bytes:
        """创建响应消息"""
        header = struct.pack(">BH", msg_type.value, len(data))
        return header + data
    
    def _create_error_response(self, error_msg: str) -> bytes:
        """创建错误响应"""
        error_data = json.dumps({"error": error_msg}).encode('utf-8')
        return self._create_response(MessageType.RESPONSE_ERROR, error_data)
    
    def _send_heartbeat(self, client: ClientConnection):
        """发送心跳"""
        try:
            heartbeat = self._create_response(MessageType.HEARTBEAT, b"")
            client.socket.sendall(heartbeat)
        except Exception:
            pass
    
    def _disconnect_client(self, client_id: str):
        """断开客户端"""
        with self._client_lock:
            client = self._clients.pop(client_id, None)
            if client:
                try:
                    client.socket.close()
                except Exception:
                    pass
                self._log("info", f"Client disconnected: {client_id}")
                self._notify_connection_change(client_id, False)
    
    # ========================================================================
    # 数据更新
    # ========================================================================
    
    def _update_loop(self):
        """数据更新循环"""
        import random
        
        while not self._stop_event.is_set():
            try:
                if self.config.enable_random_values and self.ied:
                    self._simulate_data_update()
                
                # 发送报告到订阅的客户端
                if self.config.enable_reporting:
                    self._send_reports()
                
            except Exception as e:
                self._log("error", f"Update loop error: {e}")
            
            # 等待下一个更新周期
            self._stop_event.wait(self.config.update_interval_ms / 1000.0)
    
    def _simulate_data_update(self):
        """模拟数据更新"""
        import random
        
        if not self.ied:
            return
        
        # 更新测量值
        for ld in self.ied.logical_devices.values():
            for ln in ld.logical_nodes.values():
                if ln.ln_class == "MMXU":
                    # 更新功率
                    totw = ln.get_data_object("TotW")
                    if totw:
                        mag_attr = totw.get_attribute("mag")
                        if mag_attr:
                            new_value = mag_attr.value + random.uniform(-10, 10)
                            mag_attr.set_value(new_value)
                    
                    # 更新频率
                    hz = ln.get_data_object("Hz")
                    if hz:
                        mag_attr = hz.get_attribute("mag")
                        if mag_attr:
                            new_value = 50.0 + random.uniform(-0.1, 0.1)
                            mag_attr.set_value(new_value)
    
    def _send_reports(self):
        """发送报告到订阅客户端"""
        # TODO: 实现报告逻辑
        pass
    
    # ========================================================================
    # 回调和事件
    # ========================================================================
    
    def _set_state(self, state: ServerState):
        """设置服务器状态"""
        self.state = state
        for callback in self._state_callbacks:
            try:
                callback(state)
            except Exception as e:
                logger.error(f"State callback error: {e}")
    
    def _notify_connection_change(self, client_id: str, connected: bool):
        """通知连接变化"""
        for callback in self._connection_callbacks:
            try:
                callback(client_id, connected)
            except Exception as e:
                logger.error(f"Connection callback error: {e}")
    
    def _notify_data_change(self, reference: str, old_value: Any, new_value: Any):
        """通知数据变化"""
        for callback in self._data_callbacks:
            try:
                callback(reference, old_value, new_value)
            except Exception as e:
                logger.error(f"Data callback error: {e}")
    
    def _log(self, level: str, message: str):
        """记录日志"""
        getattr(logger, level)(message)
        for callback in self._log_callbacks:
            try:
                callback(level, message)
            except Exception:
                pass
    
    # ========================================================================
    # 公共API
    # ========================================================================
    
    def on_state_change(self, callback: Callable[[ServerState], None]):
        """注册状态变化回调"""
        self._state_callbacks.append(callback)
    
    def on_connection_change(self, callback: Callable[[str, bool], None]):
        """注册连接变化回调"""
        self._connection_callbacks.append(callback)
    
    def on_data_change(self, callback: Callable[[str, Any, Any], None]):
        """注册数据变化回调"""
        self._data_callbacks.append(callback)
    
    def on_log(self, callback: Callable[[str, str], None]):
        """注册日志回调"""
        self._log_callbacks.append(callback)
    
    def get_connected_clients(self) -> List[Dict]:
        """获取已连接客户端列表"""
        with self._client_lock:
            return [
                {
                    "id": c.id,
                    "address": c.address,
                    "connected_at": c.connected_at.isoformat(),
                    "subscriptions": list(c.subscriptions),
                }
                for c in self._clients.values()
            ]
    
    def get_status(self) -> Dict:
        """获取服务器状态"""
        return {
            "state": self.state.name,
            "address": f"{self.config.ip_address}:{self.config.port}",
            "ied_name": self.ied.name if self.ied else None,
            "client_count": len(self._clients),
            "config": {
                "update_interval_ms": self.config.update_interval_ms,
                "enable_random_values": self.config.enable_random_values,
                "enable_reporting": self.config.enable_reporting,
            }
        }
