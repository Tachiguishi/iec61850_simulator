"""
IEC61850 Client Implementation
==============================

实现IEC61850客户端功能，包括：
- 连接到IED服务器
- 浏览数据模型
- 读取/写入数据值
- 控制操作
- 报告订阅
"""

from __future__ import annotations

import json
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple
from queue import Queue, Empty

from loguru import logger


class ClientState(Enum):
    """客户端状态"""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    DISCONNECTING = auto()
    ERROR = auto()


class MessageType(Enum):
    """消息类型 - 与服务端保持一致"""
    GET_SERVER_DIRECTORY = 0x01
    GET_LOGICAL_DEVICE_DIRECTORY = 0x02
    GET_LOGICAL_NODE_DIRECTORY = 0x03
    GET_DATA_VALUES = 0x04
    SET_DATA_VALUES = 0x05
    GET_DATA_DEFINITION = 0x06
    
    SELECT = 0x10
    OPERATE = 0x11
    CANCEL = 0x12
    
    ENABLE_REPORTING = 0x20
    DISABLE_REPORTING = 0x21
    GET_REPORT = 0x22
    
    RESPONSE_OK = 0x80
    RESPONSE_ERROR = 0x81
    REPORT_DATA = 0x82
    
    HEARTBEAT = 0xF0
    DISCONNECT = 0xFF


@dataclass
class ClientConfig:
    """客户端配置"""
    timeout_ms: int = 5000
    retry_count: int = 3
    retry_interval_ms: int = 1000
    polling_interval_ms: int = 1000
    enable_reporting: bool = True
    auto_reconnect: bool = True
    
    @classmethod
    def from_dict(cls, data: Dict) -> ClientConfig:
        return cls(
            timeout_ms=data.get("timeout_ms", 5000),
            retry_count=data.get("retry_count", 3),
            retry_interval_ms=data.get("retry_interval_ms", 1000),
            polling_interval_ms=data.get("polling_interval_ms", 1000),
            enable_reporting=data.get("enable_reporting", True),
            auto_reconnect=data.get("auto_reconnect", True),
        )


@dataclass
class ConnectionInfo:
    """连接信息"""
    host: str
    port: int
    name: str = ""
    
    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"


@dataclass
class ServerDirectory:
    """服务器目录信息"""
    ied_name: str = ""
    manufacturer: str = ""
    model: str = ""
    revision: str = ""
    logical_devices: List[str] = field(default_factory=list)


@dataclass
class DataValue:
    """数据值"""
    reference: str
    value: Any
    quality: int = 0
    timestamp: Optional[datetime] = None
    error: Optional[str] = None


class IEC61850Client:
    """
    IEC61850客户端
    
    提供以下功能：
    - 连接/断开IED服务器
    - 浏览服务器数据模型
    - 读取/写入数据值
    - 执行控制操作
    - 订阅报告
    """
    
    def __init__(self, config: Optional[ClientConfig] = None):
        """
        初始化客户端
        
        Args:
            config: 客户端配置
        """
        self.config = config or ClientConfig()
        self.state = ClientState.DISCONNECTED
        
        # 连接信息
        self._connection: Optional[ConnectionInfo] = None
        self._socket: Optional[socket.socket] = None
        self._server_directory: Optional[ServerDirectory] = None
        
        # 线程
        self._receive_thread: Optional[threading.Thread] = None
        self._polling_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # 响应队列
        self._response_queue: Queue = Queue()
        self._pending_requests: Dict[int, Queue] = {}
        self._request_id = 0
        self._request_lock = threading.Lock()
        
        # 订阅
        self._subscriptions: Dict[str, Callable] = {}
        
        # 缓存的数据值
        self._cached_values: Dict[str, DataValue] = {}
        
        # 回调
        self._state_callbacks: List[Callable[[ClientState], None]] = []
        self._data_callbacks: List[Callable[[str, Any], None]] = []
        self._report_callbacks: List[Callable[[Dict], None]] = []
        self._log_callbacks: List[Callable[[str, str], None]] = []
    
    # ========================================================================
    # 连接管理
    # ========================================================================
    
    def connect(self, host: str, port: int = 102, name: str = "") -> bool:
        """
        连接到IED服务器
        
        Args:
            host: 服务器IP地址
            port: 服务器端口
            name: 连接名称（可选）
            
        Returns:
            是否成功连接
        """
        if self.state == ClientState.CONNECTED:
            self._log("warning", "Already connected")
            return False
        
        self._connection = ConnectionInfo(host=host, port=port, name=name)
        
        try:
            self._set_state(ClientState.CONNECTING)
            self._stop_event.clear()
            
            # 创建socket连接
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.config.timeout_ms / 1000.0)
            self._socket.connect((host, port))
            
            # 启动接收线程
            self._receive_thread = threading.Thread(
                target=self._receive_loop,
                name="IEC61850-Client-Recv",
                daemon=True
            )
            self._receive_thread.start()
            
            # 获取服务器目录
            self._server_directory = self._get_server_directory()
            
            if self._server_directory:
                self._set_state(ClientState.CONNECTED)
                self._log("info", f"Connected to {host}:{port} - IED: {self._server_directory.ied_name}")
                
                # 启动轮询线程
                if self.config.enable_reporting:
                    self._polling_thread = threading.Thread(
                        target=self._polling_loop,
                        name="IEC61850-Client-Poll",
                        daemon=True
                    )
                    self._polling_thread.start()
                
                return True
            else:
                raise Exception("Failed to get server directory")
                
        except Exception as e:
            self._log("error", f"Connection failed: {e}")
            self._set_state(ClientState.ERROR)
            self._cleanup()
            return False
    
    def disconnect(self) -> bool:
        """
        断开连接
        
        Returns:
            是否成功断开
        """
        if self.state == ClientState.DISCONNECTED:
            return True
        
        try:
            self._set_state(ClientState.DISCONNECTING)
            
            # 发送断开消息
            if self._socket:
                try:
                    disconnect_msg = self._create_message(MessageType.DISCONNECT, b"")
                    self._socket.sendall(disconnect_msg)
                except Exception:
                    pass
            
            self._stop_event.set()
            self._cleanup()
            
            self._set_state(ClientState.DISCONNECTED)
            self._log("info", "Disconnected")
            return True
            
        except Exception as e:
            self._log("error", f"Disconnect error: {e}")
            self._set_state(ClientState.ERROR)
            return False
    
    def reconnect(self) -> bool:
        """重新连接"""
        if self._connection:
            self.disconnect()
            time.sleep(0.5)
            return self.connect(
                self._connection.host,
                self._connection.port,
                self._connection.name
            )
        return False
    
    def _cleanup(self):
        """清理资源"""
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        
        self._server_directory = None
        self._cached_values.clear()
        self._subscriptions.clear()
    
    # ========================================================================
    # 通信
    # ========================================================================
    
    def _receive_loop(self):
        """接收消息循环"""
        while not self._stop_event.is_set():
            try:
                if not self._socket:
                    break
                
                # 接收消息头
                header = self._socket.recv(4)
                if not header:
                    break
                
                if len(header) < 3:
                    continue
                
                msg_type, msg_len = struct.unpack(">BH", header[:3])
                
                # 接收消息体
                data = b""
                if msg_len > 0:
                    data = self._socket.recv(msg_len)
                
                # 处理消息
                self._handle_message(msg_type, data)
                
            except socket.timeout:
                continue
            except Exception as e:
                if not self._stop_event.is_set():
                    self._log("error", f"Receive error: {e}")
                    if self.config.auto_reconnect:
                        self._handle_disconnect()
                break
    
    def _handle_message(self, msg_type: int, data: bytes):
        """处理接收到的消息"""
        if msg_type == MessageType.RESPONSE_OK.value:
            self._response_queue.put(("ok", data))
            
        elif msg_type == MessageType.RESPONSE_ERROR.value:
            self._response_queue.put(("error", data))
            
        elif msg_type == MessageType.REPORT_DATA.value:
            self._handle_report(data)
            
        elif msg_type == MessageType.HEARTBEAT.value:
            # 响应心跳
            pass
    
    def _handle_report(self, data: bytes):
        """处理报告数据"""
        try:
            report = json.loads(data.decode('utf-8'))
            
            # 更新缓存
            for ref, value_info in report.items():
                if isinstance(value_info, dict):
                    self._cached_values[ref] = DataValue(
                        reference=ref,
                        value=value_info.get("value"),
                        quality=value_info.get("quality", 0),
                        timestamp=datetime.fromisoformat(value_info["timestamp"]) if value_info.get("timestamp") else None,
                    )
                    
                    # 触发回调
                    for callback in self._data_callbacks:
                        try:
                            callback(ref, value_info.get("value"))
                        except Exception as e:
                            logger.error(f"Data callback error: {e}")
            
            # 报告回调
            for callback in self._report_callbacks:
                try:
                    callback(report)
                except Exception as e:
                    logger.error(f"Report callback error: {e}")
                    
        except Exception as e:
            self._log("error", f"Failed to handle report: {e}")
    
    def _handle_disconnect(self):
        """处理意外断开"""
        self._set_state(ClientState.DISCONNECTED)
        
        if self.config.auto_reconnect and self._connection:
            self._log("info", "Attempting to reconnect...")
            for i in range(self.config.retry_count):
                time.sleep(self.config.retry_interval_ms / 1000.0)
                if self.reconnect():
                    return
            self._log("error", "Reconnection failed")
    
    def _send_request(self, msg_type: MessageType, data: bytes = b"") -> Optional[Dict]:
        """
        发送请求并等待响应
        
        Args:
            msg_type: 消息类型
            data: 消息数据
            
        Returns:
            响应数据字典，失败返回None
        """
        if not self._socket or self.state != ClientState.CONNECTED:
            return None
        
        try:
            # 清空响应队列
            while not self._response_queue.empty():
                try:
                    self._response_queue.get_nowait()
                except Empty:
                    break
            
            # 发送请求
            message = self._create_message(msg_type, data)
            self._socket.sendall(message)
            
            # 等待响应
            try:
                status, response_data = self._response_queue.get(
                    timeout=self.config.timeout_ms / 1000.0
                )
                
                if status == "ok":
                    return json.loads(response_data.decode('utf-8'))
                else:
                    error = json.loads(response_data.decode('utf-8'))
                    self._log("error", f"Request error: {error.get('error', 'Unknown')}")
                    return None
                    
            except Empty:
                self._log("error", "Request timeout")
                return None
                
        except Exception as e:
            self._log("error", f"Send request error: {e}")
            return None
    
    def _create_message(self, msg_type: MessageType, data: bytes) -> bytes:
        """创建消息"""
        header = struct.pack(">BH", msg_type.value, len(data))
        return header + data
    
    def _polling_loop(self):
        """轮询数据更新"""
        while not self._stop_event.is_set():
            try:
                if self._subscriptions:
                    references = list(self._subscriptions.keys())
                    values = self.read_values(references)
                    
                    for ref, value in values.items():
                        if ref in self._subscriptions:
                            try:
                                self._subscriptions[ref](ref, value)
                            except Exception as e:
                                logger.error(f"Subscription callback error: {e}")
                
            except Exception as e:
                self._log("error", f"Polling error: {e}")
            
            self._stop_event.wait(self.config.polling_interval_ms / 1000.0)
    
    # ========================================================================
    # 数据模型浏览
    # ========================================================================
    
    def _get_server_directory(self) -> Optional[ServerDirectory]:
        """获取服务器目录"""
        response = self._send_request(MessageType.GET_SERVER_DIRECTORY)
        
        if response:
            return ServerDirectory(
                ied_name=response.get("ied_name", ""),
                manufacturer=response.get("manufacturer", ""),
                model=response.get("model", ""),
                revision=response.get("revision", ""),
                logical_devices=response.get("logical_devices", []),
            )
        return None
    
    def get_server_info(self) -> Optional[Dict]:
        """获取服务器信息"""
        if self._server_directory:
            return {
                "ied_name": self._server_directory.ied_name,
                "manufacturer": self._server_directory.manufacturer,
                "model": self._server_directory.model,
                "revision": self._server_directory.revision,
            }
        return None
    
    def get_logical_devices(self) -> List[str]:
        """获取逻辑设备列表"""
        if self._server_directory:
            return self._server_directory.logical_devices
        return []
    
    def get_logical_device_directory(self, ld_name: str) -> Optional[Dict]:
        """获取逻辑设备目录"""
        response = self._send_request(
            MessageType.GET_LOGICAL_DEVICE_DIRECTORY,
            ld_name.encode('utf-8')
        )
        return response
    
    def get_logical_node_directory(self, ld_name: str, ln_name: str) -> Optional[Dict]:
        """获取逻辑节点目录"""
        path = f"{ld_name}/{ln_name}"
        response = self._send_request(
            MessageType.GET_LOGICAL_NODE_DIRECTORY,
            path.encode('utf-8')
        )
        return response
    
    def browse_data_model(self) -> Dict:
        """
        浏览完整数据模型
        
        Returns:
            完整的数据模型树
        """
        if not self._server_directory:
            return {}
        
        model = {
            "ied_name": self._server_directory.ied_name,
            "logical_devices": {}
        }
        
        for ld_name in self._server_directory.logical_devices:
            ld_dir = self.get_logical_device_directory(ld_name)
            if ld_dir:
                model["logical_devices"][ld_name] = {
                    "description": ld_dir.get("description", ""),
                    "logical_nodes": {}
                }
                
                for ln_name in ld_dir.get("logical_nodes", []):
                    ln_dir = self.get_logical_node_directory(ld_name, ln_name)
                    if ln_dir:
                        model["logical_devices"][ld_name]["logical_nodes"][ln_name] = ln_dir
        
        return model
    
    # ========================================================================
    # 数据读写
    # ========================================================================
    
    def read_value(self, reference: str) -> Optional[DataValue]:
        """
        读取单个数据值
        
        Args:
            reference: 数据引用路径
            
        Returns:
            数据值对象
        """
        values = self.read_values([reference])
        return values.get(reference)
    
    def read_values(self, references: List[str]) -> Dict[str, DataValue]:
        """
        读取多个数据值
        
        Args:
            references: 数据引用路径列表
            
        Returns:
            引用到数据值的映射
        """
        response = self._send_request(
            MessageType.GET_DATA_VALUES,
            json.dumps(references).encode('utf-8')
        )
        
        result = {}
        if response:
            for ref, value_info in response.items():
                if isinstance(value_info, dict):
                    if "error" in value_info:
                        result[ref] = DataValue(
                            reference=ref,
                            value=None,
                            error=value_info["error"]
                        )
                    else:
                        dv = DataValue(
                            reference=ref,
                            value=value_info.get("value"),
                            quality=value_info.get("quality", 0),
                            timestamp=datetime.fromisoformat(value_info["timestamp"]) if value_info.get("timestamp") else None,
                        )
                        result[ref] = dv
                        self._cached_values[ref] = dv
        
        return result
    
    def write_value(self, reference: str, value: Any) -> bool:
        """
        写入单个数据值
        
        Args:
            reference: 数据引用路径
            value: 要写入的值
            
        Returns:
            是否成功
        """
        return self.write_values({reference: value}).get(reference, False)
    
    def write_values(self, updates: Dict[str, Any]) -> Dict[str, bool]:
        """
        写入多个数据值
        
        Args:
            updates: 引用到值的映射
            
        Returns:
            引用到成功状态的映射
        """
        response = self._send_request(
            MessageType.SET_DATA_VALUES,
            json.dumps(updates).encode('utf-8')
        )
        
        result = {}
        if response:
            for ref, status in response.items():
                result[ref] = status == "OK"
        
        return result
    
    # ========================================================================
    # 控制操作
    # ========================================================================
    
    def operate(self, reference: str, value: Any) -> bool:
        """
        执行控制操作
        
        Args:
            reference: 控制点引用路径
            value: 控制值
            
        Returns:
            是否成功
        """
        control_data = {
            "reference": reference,
            "value": value,
            "timestamp": datetime.now().isoformat(),
        }
        
        response = self._send_request(
            MessageType.OPERATE,
            json.dumps(control_data).encode('utf-8')
        )
        
        if response:
            return response.get("success", False)
        return False
    
    def select_before_operate(self, reference: str) -> bool:
        """
        SBO选择操作
        
        Args:
            reference: 控制点引用路径
            
        Returns:
            是否成功选择
        """
        select_data = {
            "reference": reference,
            "timestamp": datetime.now().isoformat(),
        }
        
        response = self._send_request(
            MessageType.SELECT,
            json.dumps(select_data).encode('utf-8')
        )
        
        if response:
            return response.get("success", False)
        return False
    
    def cancel(self, reference: str) -> bool:
        """
        取消控制操作
        
        Args:
            reference: 控制点引用路径
            
        Returns:
            是否成功取消
        """
        cancel_data = {"reference": reference}
        
        response = self._send_request(
            MessageType.CANCEL,
            json.dumps(cancel_data).encode('utf-8')
        )
        
        if response:
            return response.get("success", False)
        return False
    
    # ========================================================================
    # 订阅和报告
    # ========================================================================
    
    def subscribe(self, reference: str, callback: Callable[[str, Any], None]):
        """
        订阅数据变化
        
        Args:
            reference: 数据引用路径
            callback: 回调函数 (reference, value)
        """
        self._subscriptions[reference] = callback
        
        # 通知服务器
        if self.state == ClientState.CONNECTED:
            self._send_request(
                MessageType.ENABLE_REPORTING,
                json.dumps({"references": [reference]}).encode('utf-8')
            )
    
    def unsubscribe(self, reference: str):
        """取消订阅"""
        self._subscriptions.pop(reference, None)
    
    def subscribe_all(self, references: List[str], callback: Callable[[str, Any], None]):
        """批量订阅"""
        for ref in references:
            self._subscriptions[ref] = callback
        
        if self.state == ClientState.CONNECTED:
            self._send_request(
                MessageType.ENABLE_REPORTING,
                json.dumps({"references": references}).encode('utf-8')
            )
    
    # ========================================================================
    # 回调和事件
    # ========================================================================
    
    def _set_state(self, state: ClientState):
        """设置客户端状态"""
        self.state = state
        for callback in self._state_callbacks:
            try:
                callback(state)
            except Exception as e:
                logger.error(f"State callback error: {e}")
    
    def _log(self, level: str, message: str):
        """记录日志"""
        getattr(logger, level)(message)
        for callback in self._log_callbacks:
            try:
                callback(level, message)
            except Exception:
                pass
    
    def on_state_change(self, callback: Callable[[ClientState], None]):
        """注册状态变化回调"""
        self._state_callbacks.append(callback)
    
    def on_data_change(self, callback: Callable[[str, Any], None]):
        """注册数据变化回调"""
        self._data_callbacks.append(callback)
    
    def on_report(self, callback: Callable[[Dict], None]):
        """注册报告回调"""
        self._report_callbacks.append(callback)
    
    def on_log(self, callback: Callable[[str, str], None]):
        """注册日志回调"""
        self._log_callbacks.append(callback)
    
    # ========================================================================
    # 状态查询
    # ========================================================================
    
    def is_connected(self) -> bool:
        """是否已连接"""
        return self.state == ClientState.CONNECTED
    
    def get_connection_info(self) -> Optional[Dict]:
        """获取连接信息"""
        if self._connection:
            return {
                "host": self._connection.host,
                "port": self._connection.port,
                "name": self._connection.name,
                "state": self.state.name,
            }
        return None
    
    def get_cached_value(self, reference: str) -> Optional[DataValue]:
        """获取缓存的数据值"""
        return self._cached_values.get(reference)
    
    def get_all_cached_values(self) -> Dict[str, DataValue]:
        """获取所有缓存的数据值"""
        return self._cached_values.copy()
