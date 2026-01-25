"""
IEC61850 Client Implementation
==============================

实现IEC61850客户端功能, 使用libiec61850的Python绑定(pyiec61850):
- 连接到IED服务器
- 浏览数据模型
- 读取/写入数据值
- 控制操作
- 报告订阅

使用pyiec61850库实现标准MMS协议。
"""

from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple
from queue import Queue, Empty

from loguru import logger

try:
    import pyiec61850 as iec61850
    PYIEC61850_AVAILABLE = True
except ImportError as e:
    logger.warning(f"pyiec61850 not available: {e}")
    PYIEC61850_AVAILABLE = False

class ClientState(Enum):
    """客户端状态"""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    DISCONNECTING = auto()
    ERROR = auto()

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
    IEC61850客户端 - 使用pyiec61850库实现真实MMS协议
    
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
        self._ied_connection = None  # pyiec61850 IedConnection
        self._server_directory: Optional[ServerDirectory] = None
        
        # 线程
        self._polling_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
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
        if not PYIEC61850_AVAILABLE:
            self._log("error", "pyiec61850 library not available")
            self._set_state(ClientState.ERROR)
            return False
        
        if self.state == ClientState.CONNECTED:
            self._log("warning", "Already connected")
            return False
        
        self._connection = ConnectionInfo(host=host, port=port, name=name)
        
        try:
            self._set_state(ClientState.CONNECTING)
            self._stop_event.clear()
            
            # 创建连接
            self._ied_connection = iec61850.IedConnection_create()
            
            # 设置超时
            iec61850.IedConnection_setConnectTimeout(
                self._ied_connection, 
                self.config.timeout_ms
            )
            iec61850.IedConnection_setRequestTimeout(
                self._ied_connection, 
                self.config.timeout_ms
            )
            
            # 连接到服务器
            error = iec61850.IedConnection_connect(
                self._ied_connection, 
                host, 
                port
            )
            
            if error != iec61850.IED_ERROR_OK:
                error_str = iec61850.IedClientError_toString(error)
                raise Exception(f"Connection failed: {error_str}")
            
            # 检查连接状态
            state = iec61850.IedConnection_getState(self._ied_connection)
            if state != iec61850.IED_STATE_CONNECTED:
                raise Exception("Connection state is not CONNECTED")
            
            # 获取服务器目录
            self._server_directory = self._get_server_directory()
            
            if self._server_directory:
                self._set_state(ClientState.CONNECTED)
                self._log("info", f"Connected to {host}:{port}")
                
                # 启动轮询线程
                if self.config.enable_reporting and self._subscriptions:
                    self._start_polling()
                
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
            
            self._stop_event.set()
            
            # 等待轮询线程结束
            if self._polling_thread and self._polling_thread.is_alive():
                self._polling_thread.join(timeout=2.0)
            
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
        if self._ied_connection:
            try:
                # 关闭连接
                iec61850.IedConnection_close(self._ied_connection)
                iec61850.IedConnection_destroy(self._ied_connection)
            except Exception as e:
                logger.debug(f"Cleanup error: {e}")
            self._ied_connection = None
        
        self._server_directory = None
        self._cached_values.clear()
    
    def _start_polling(self):
        """启动轮询线程"""
        if self._polling_thread and self._polling_thread.is_alive():
            return
        
        self._polling_thread = threading.Thread(
            target=self._polling_loop,
            name="IEC61850-Client-Poll",
            daemon=True
        )
        self._polling_thread.start()
    
    def _polling_loop(self):
        """轮询数据更新"""
        while not self._stop_event.is_set():
            try:
                if self._subscriptions and self.state == ClientState.CONNECTED:
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
        if not self._ied_connection:
            return None
        
        try:
            # 获取逻辑设备列表
            result = iec61850.IedConnection_getLogicalDeviceList(self._ied_connection)
            
            if isinstance(result, tuple):
                device_list, error = result
            else:
                device_list = result
                error = iec61850.IED_ERROR_OK
            
            if error != iec61850.IED_ERROR_OK:
                return None
            
            # 遍历逻辑设备
            logical_devices = []
            if device_list:
                device = iec61850.LinkedList_getNext(device_list)
                while device:
                    ld_name = iec61850.toCharP(device.data)
                    logical_devices.append(ld_name)
                    device = iec61850.LinkedList_getNext(device)
                iec61850.LinkedList_destroy(device_list)
            
            return ServerDirectory(
                ied_name="IED",  # pyiec61850 不直接提供IED名称
                logical_devices=logical_devices,
            )
            
        except Exception as e:
            self._log("error", f"Failed to get server directory: {e}")
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
        if not self._ied_connection:
            return None
        
        try:
            result = iec61850.IedConnection_getLogicalDeviceDirectory(
                self._ied_connection, ld_name
            )
            
            if isinstance(result, tuple):
                ln_list, error = result
            else:
                ln_list = result
                error = iec61850.IED_ERROR_OK
            
            if error != iec61850.IED_ERROR_OK:
                return None
            
            logical_nodes = []
            if ln_list:
                ln = iec61850.LinkedList_getNext(ln_list)
                while ln:
                    ln_name = iec61850.toCharP(ln.data)
                    logical_nodes.append(ln_name)
                    ln = iec61850.LinkedList_getNext(ln)
                iec61850.LinkedList_destroy(ln_list)
            
            return {
                "name": ld_name,
                "logical_nodes": logical_nodes,
            }
            
        except Exception as e:
            self._log("error", f"Failed to get LD directory: {e}")
            return None
    
    def get_logical_node_directory(self, ld_name: str, ln_name: str) -> Optional[Dict]:
        """获取逻辑节点目录"""
        if not self._ied_connection:
            return None
        
        try:
            ln_ref = f"{ld_name}/{ln_name}"
            
            # 获取数据对象
            result = iec61850.IedConnection_getLogicalNodeDirectory(
                self._ied_connection, 
                ln_ref,
                iec61850.ACSI_CLASS_DATA_OBJECT
            )
            
            if isinstance(result, tuple):
                do_list, error = result
            else:
                do_list = result
                error = iec61850.IED_ERROR_OK
            
            if error != iec61850.IED_ERROR_OK:
                return None
            
            data_objects = []
            if do_list:
                do = iec61850.LinkedList_getNext(do_list)
                while do:
                    do_name = iec61850.toCharP(do.data)
                    data_objects.append(do_name)
                    do = iec61850.LinkedList_getNext(do)
                iec61850.LinkedList_destroy(do_list)
            
            return {
                "name": ln_name,
                "data_objects": data_objects,
            }
            
        except Exception as e:
            self._log("error", f"Failed to get LN directory: {e}")
            return None
    
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
            reference: 数据引用路径 (格式: LD/LN.DO.DA)
            
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
        if not self._ied_connection or self.state != ClientState.CONNECTED:
            return {}
        
        result = {}
        for ref in references:
            try:
                dv = self._read_single_value(ref)
                if dv:
                    result[ref] = dv
                    self._cached_values[ref] = dv
            except Exception as e:
                result[ref] = DataValue(reference=ref, value=None, error=str(e))
        
        return result
    
    def _read_single_value(self, reference: str) -> Optional[DataValue]:
        """读取单个值"""
        if not self._ied_connection:
            return None
        
        try:
            # 尝试不同的功能约束
            fcs = [
                iec61850.IEC61850_FC_ST,
                iec61850.IEC61850_FC_MX,
                iec61850.IEC61850_FC_SP,
                iec61850.IEC61850_FC_CF,
            ]
            
            for fc in fcs:
                try:
                    result = iec61850.IedConnection_readObject(
                        self._ied_connection,
                        reference,
                        fc
                    )
                    
                    if isinstance(result, tuple):
                        mms_value, error = result
                    else:
                        mms_value = result
                        error = iec61850.IED_ERROR_OK
                    
                    if error == iec61850.IED_ERROR_OK and mms_value:
                        value = self._mms_value_to_python(mms_value)
                        iec61850.MmsValue_delete(mms_value)
                        
                        return DataValue(
                            reference=reference,
                            value=value,
                            timestamp=datetime.now(),
                        )
                except:
                    continue
            
            return None
            
        except Exception as e:
            self._log("error", f"Failed to read {reference}: {e}")
            return None
    
    def _mms_value_to_python(self, mms_value) -> Any:
        """将MMS值转换为Python值"""
        try:
            mms_type = iec61850.MmsValue_getType(mms_value)
            
            if mms_type == iec61850.MMS_BOOLEAN:
                return iec61850.MmsValue_getBoolean(mms_value)
            elif mms_type == iec61850.MMS_INTEGER:
                return iec61850.MmsValue_toInt32(mms_value)
            elif mms_type == iec61850.MMS_UNSIGNED:
                return iec61850.MmsValue_toUint32(mms_value)
            elif mms_type == iec61850.MMS_FLOAT:
                return iec61850.MmsValue_toFloat(mms_value)
            elif mms_type == iec61850.MMS_VISIBLE_STRING:
                return iec61850.MmsValue_toString(mms_value)
            elif mms_type == iec61850.MMS_BIT_STRING:
                return iec61850.MmsValue_getBitStringAsInteger(mms_value)
            elif mms_type == iec61850.MMS_UTC_TIME:
                ms_time = iec61850.MmsValue_getUtcTimeInMs(mms_value)
                return datetime.fromtimestamp(ms_time / 1000.0)
            elif mms_type == iec61850.MMS_STRUCTURE:
                # 递归处理结构体
                size = iec61850.MmsValue_getArraySize(mms_value)
                result = {}
                for i in range(size):
                    element = iec61850.MmsValue_getElement(mms_value, i)
                    result[f"element_{i}"] = self._mms_value_to_python(element)
                return result
            elif mms_type == iec61850.MMS_ARRAY:
                size = iec61850.MmsValue_getArraySize(mms_value)
                result = []
                for i in range(size):
                    element = iec61850.MmsValue_getElement(mms_value, i)
                    result.append(self._mms_value_to_python(element))
                return result
            else:
                return None
                
        except Exception as e:
            logger.debug(f"MMS value conversion error: {e}")
            return None
    
    def write_value(self, reference: str, value: Any) -> bool:
        """
        写入单个数据值
        
        Args:
            reference: 数据引用路径
            value: 要写入的值
            
        Returns:
            是否成功写入
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
        if not self._ied_connection or self.state != ClientState.CONNECTED:
            return {ref: False for ref in updates}
        
        result = {}
        for ref, value in updates.items():
            try:
                success = self._write_single_value(ref, value)
                result[ref] = success
            except Exception as e:
                self._log("error", f"Failed to write {ref}: {e}")
                result[ref] = False
        
        return result
    
    def _write_single_value(self, reference: str, value: Any) -> bool:
        """写入单个值"""
        if not self._ied_connection:
            return False
        
        try:
            # 尝试不同的功能约束
            fcs = [
                iec61850.IEC61850_FC_SP,  # 设定点优先
                iec61850.IEC61850_FC_CF,
                iec61850.IEC61850_FC_ST,
            ]
            
            for fc in fcs:
                try:
                    if isinstance(value, bool):
                        error = iec61850.IedConnection_writeBooleanValue(
                            self._ied_connection, reference, fc, value
                        )
                    elif isinstance(value, int):
                        error = iec61850.IedConnection_writeInt32Value(
                            self._ied_connection, reference, fc, value
                        )
                    elif isinstance(value, float):
                        error = iec61850.IedConnection_writeFloatValue(
                            self._ied_connection, reference, fc, value
                        )
                    elif isinstance(value, str):
                        error = iec61850.IedConnection_writeVisibleStringValue(
                            self._ied_connection, reference, fc, value
                        )
                    else:
                        continue
                    
                    if error == iec61850.IED_ERROR_OK:
                        return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            self._log("error", f"Write error: {e}")
            return False
    
    # ========================================================================
    # 控制操作
    # ========================================================================
    
    def operate(self, reference: str, value: Any, **kwargs) -> bool:
        """
        执行控制操作
        
        Args:
            reference: 控制点引用
            value: 控制值
            **kwargs: 其他参数
            
        Returns:
            是否成功
        """
        if not self._ied_connection or self.state != ClientState.CONNECTED:
            return False
        
        try:
            # 创建控制对象
            control = iec61850.ControlObjectClient_create(
                reference, 
                self._ied_connection
            )
            
            if not control:
                self._log("error", f"Failed to create control object for {reference}")
                return False
            
            try:
                # 创建控制值
                if isinstance(value, bool):
                    mms_value = iec61850.MmsValue_newBoolean(value)
                elif isinstance(value, int):
                    mms_value = iec61850.MmsValue_newIntegerFromInt32(value)
                elif isinstance(value, float):
                    mms_value = iec61850.MmsValue_newFloat(value)
                else:
                    self._log("error", f"Unsupported control value type: {type(value)}")
                    return False
                
                # 执行操作
                success = iec61850.ControlObjectClient_operate(
                    control, mms_value, 0
                )
                
                iec61850.MmsValue_delete(mms_value)
                
                return success
                
            finally:
                iec61850.ControlObjectClient_destroy(control)
                
        except Exception as e:
            self._log("error", f"Control operation failed: {e}")
            return False
    
    def select(self, reference: str) -> bool:
        """
        选择控制点 (SBO模式)
        
        Args:
            reference: 控制点引用
            
        Returns:
            是否成功选择
        """
        if not self._ied_connection or self.state != ClientState.CONNECTED:
            return False
        
        try:
            control = iec61850.ControlObjectClient_create(
                reference, 
                self._ied_connection
            )
            
            if not control:
                return False
            
            try:
                success = iec61850.ControlObjectClient_select(control)
                return success
            finally:
                iec61850.ControlObjectClient_destroy(control)
                
        except Exception as e:
            self._log("error", f"Select failed: {e}")
            return False
    
    def cancel(self, reference: str) -> bool:
        """
        取消控制操作
        
        Args:
            reference: 控制点引用
            
        Returns:
            是否成功取消
        """
        if not self._ied_connection or self.state != ClientState.CONNECTED:
            return False
        
        try:
            control = iec61850.ControlObjectClient_create(
                reference, 
                self._ied_connection
            )
            
            if not control:
                return False
            
            try:
                success = iec61850.ControlObjectClient_cancel(control)
                return success
            finally:
                iec61850.ControlObjectClient_destroy(control)
                
        except Exception as e:
            self._log("error", f"Cancel failed: {e}")
            return False
    
    # ========================================================================
    # 订阅
    # ========================================================================
    
    def subscribe(self, reference: str, callback: Callable[[str, Any], None]) -> bool:
        """
        订阅数据变化
        
        Args:
            reference: 数据引用
            callback: 变化回调函数
            
        Returns:
            是否成功订阅
        """
        self._subscriptions[reference] = callback
        
        # 如果已连接，启动轮询
        if self.state == ClientState.CONNECTED:
            self._start_polling()
        
        return True
    
    def unsubscribe(self, reference: str) -> bool:
        """
        取消订阅
        
        Args:
            reference: 数据引用
            
        Returns:
            是否成功取消
        """
        if reference in self._subscriptions:
            del self._subscriptions[reference]
            return True
        return False
    
    def get_cached_value(self, reference: str) -> Optional[DataValue]:
        """获取缓存的值"""
        return self._cached_values.get(reference)
    
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
    
    # ========================================================================
    # 公共API
    # ========================================================================
    
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
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        if self._ied_connection:
            try:
                state = iec61850.IedConnection_getState(self._ied_connection)
                return state == iec61850.IED_STATE_CONNECTED
            except:
                pass
        return False
