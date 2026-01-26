"""
IEC61850 Server Implementation
==============================

实现IEC61850服务端功能，使用libiec61850的Python绑定(pyiec61850)：
- 真实MMS协议服务器
- 数据点管理
- 客户端连接管理
- 报告和GOOSE发布

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
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from loguru import logger

# 添加pyiec61850库路径
# PYIEC61850_PATH = os.path.join(
#     os.path.dirname(__file__), 
#     "..", "..", "deps", "libiec61850", "build", "pyiec61850"
# )
# sys.path.insert(0, PYIEC61850_PATH)

try:
    import pyiec61850 as iec61850
    PYIEC61850_AVAILABLE = True
except ImportError as e:
    logger.warning(f"pyiec61850 not available: {e}")
    PYIEC61850_AVAILABLE = False

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
    connected_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    subscriptions: Set[str] = field(default_factory=set)
    
    def __hash__(self):
        return hash(self.id)


class IEC61850Server:
    """
    IEC61850服务端 - 使用pyiec61850库实现真实MMS协议
    
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
        
        # pyiec61850 对象
        self._ied_model = None
        self._ied_server = None
        self._model_nodes: Dict[str, Any] = {}  # 存储数据属性节点引用
        
        # 客户端跟踪
        self._clients: Dict[str, ClientConnection] = {}
        self._client_lock = threading.Lock()
        
        # 线程
        self._update_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # 回调
        self._state_callbacks: List[Callable[[ServerState], None]] = []
        self._connection_callbacks: List[Callable[[str, bool], None]] = []
        self._data_callbacks: List[Callable[[str, Any, Any], None]] = []
        self._log_callbacks: List[Callable[[str, str], None]] = []
        
    # ========================================================================
    # 生命周期管理
    # ========================================================================
    
    def start(self) -> bool:
        """
        启动服务器
        
        Returns:
            是否成功启动
        """
        if not PYIEC61850_AVAILABLE:
            self._log("error", "pyiec61850 library not available")
            self._set_state(ServerState.ERROR)
            return False
        
        if self.state == ServerState.RUNNING:
            self._log("warning", "Server is already running")
            return False
        
        if self.ied is None:
            self._log("warning", "No IED configured, creating default")
            self.ied = self.data_model_manager.create_default_ied()
        
        try:
            self._set_state(ServerState.STARTING)
            self._stop_event.clear()
            
            # 创建IED模型
            self._create_ied_model()
            
            # 创建服务器配置
            server_config = iec61850.IedServerConfig_create()
            iec61850.IedServerConfig_setMaxMmsConnections(server_config, self.config.max_connections)
            iec61850.IedServerConfig_setEdition(server_config, iec61850.IEC_61850_EDITION_2)
            
            # 创建并启动服务器
            self._ied_server = iec61850.IedServer_createWithConfig(
                self._ied_model, None, server_config
            )
            
            # 设置服务器标识
            if self.ied:
                iec61850.IedServer_setServerIdentity(
                    self._ied_server,
                    self.ied.manufacturer or "IEC61850 Simulator",
                    self.ied.model or "Virtual IED",
                    self.ied.revision or "1.0.0"
                )
            
            # 启动服务器
            iec61850.IedServer_start(self._ied_server, self.config.port)
            
            if not iec61850.IedServer_isRunning(self._ied_server):
                raise Exception("Failed to start IED server")
            
            # 启动数据更新线程
            self._update_thread = threading.Thread(
                target=self._update_loop,
                name="IEC61850-Update",
                daemon=True
            )
            self._update_thread.start()
            
            # 清理配置对象
            iec61850.IedServerConfig_destroy(server_config)
            
            self._set_state(ServerState.RUNNING)
            self._log("info", f"Server started on port {self.config.port}")
            return True
            
        except Exception as e:
            self._log("error", f"Failed to start server: {e}")
            self._cleanup()
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
            
            # 等待更新线程结束
            if self._update_thread and self._update_thread.is_alive():
                self._update_thread.join(timeout=2.0)
            
            # 停止并销毁服务器
            self._cleanup()
            
            self._set_state(ServerState.STOPPED)
            self._log("info", "Server stopped")
            return True
            
        except Exception as e:
            self._log("error", f"Error stopping server: {e}")
            self._set_state(ServerState.ERROR)
            return False
    
    def _cleanup(self):
        """清理资源"""
        if self._ied_server:
            try:
                iec61850.IedServer_stop(self._ied_server)
                iec61850.IedServer_destroy(self._ied_server)
            except Exception as e:
                logger.error(f"Error destroying server: {e}")
            self._ied_server = None
        
        if self._ied_model:
            try:
                iec61850.IedModel_destroy(self._ied_model)
            except Exception as e:
                logger.error(f"Error destroying model: {e}")
            self._ied_model = None
        
        self._model_nodes.clear()
        self._clients.clear()
    
    def restart(self) -> bool:
        """重启服务器"""
        self.stop()
        time.sleep(0.5)
        return self.start()
    
    # ========================================================================
    # IED模型创建
    # ========================================================================
    def load_model(self, ied: IED):
        """加载IED数据模型"""
        self.ied = ied
        self._create_ied_model()

    def _create_ied_model(self):
        """从Python数据模型创建pyiec61850 IED模型"""
        if not self.ied:
            raise Exception("No IED data model configured")
        
        # 创建IED模型
        self._ied_model = iec61850.IedModel_create(self.ied.name)
        
        # 创建逻辑设备
        for ld_name, ld in self.ied.logical_devices.items():
            self._create_logical_device(ld)
    
    def _create_logical_device(self, ld: LogicalDevice):
        """创建逻辑设备"""
        # 创建LD
        ld_node = iec61850.LogicalDevice_create(ld.name, self._ied_model)
        
        # 创建逻辑节点
        for ln_name, ln in ld.logical_nodes.items():
            self._create_logical_node(ln, ld_node, ld.name)
    
    def _create_logical_node(self, ln: LogicalNode, ld_node, ld_name: str):
        """创建逻辑节点"""
        ln_node = iec61850.LogicalNode_create(ln.name, ld_node)
        
        # 创建数据对象
        for do_name, do in ln.data_objects.items():
            self._create_data_object(do, iec61850.toModelNode(ln_node), ld_name, ln.name)
    
    def _create_data_object(self, do: DataObject, parent_node, ld_name: str, ln_name: str):
        """创建数据对象"""
        do_node = iec61850.DataObject_create(do.name, parent_node, 0)
        
        # 创建数据属性
        for da_name, da in do.attributes.items():
            self._create_data_attribute(da, iec61850.toModelNode(do_node), ld_name, ln_name, do.name)
    
    def _create_data_attribute(self, da: DataAttribute, parent_node, ld_name: str, ln_name: str, do_name: str):
        """创建数据属性"""
        # 映射数据类型
        da_type = self._map_data_type(da.data_type)
        
        # 映射功能约束
        fc = self._map_fc(da.fc)
        
        # 触发选项
        trigger_options = 0
        if da.data_type != DataType.QUALITY:
            trigger_options = iec61850.TRG_OPT_DATA_CHANGED | iec61850.TRG_OPT_DATA_UPDATE
        
        # 创建属性
        da_node = iec61850.DataAttribute_create(
            da.name, 
            parent_node, 
            da_type, 
            fc, 
            trigger_options, 
            0,  # 非数组
            None  # 无短地址
        )
        
        # 存储节点引用用于后续值更新
        ref = f"{ld_name}/{ln_name}.{do_name}.{da.name}"
        self._model_nodes[ref] = da_node
        
        # 设置初始值
        if da.value is not None:
            self._set_initial_value(da_node, da.value, da_type)
    
    def _map_data_type(self, data_type: DataType) -> int:
        """映射数据类型到pyiec61850类型"""
        type_map = {
            DataType.BOOLEAN: iec61850.IEC61850_BOOLEAN,
            DataType.INT8: iec61850.IEC61850_INT8,
            DataType.INT16: iec61850.IEC61850_INT16,
            DataType.INT32: iec61850.IEC61850_INT32,
            DataType.INT64: iec61850.IEC61850_INT64,
            DataType.INT128: iec61850.IEC61850_INT128,
            DataType.INT8U: iec61850.IEC61850_INT8U,
            DataType.INT16U: iec61850.IEC61850_INT16U,
            DataType.INT24U: iec61850.IEC61850_INT24U,
            DataType.INT32U: iec61850.IEC61850_INT32U,
            DataType.FLOAT32: iec61850.IEC61850_FLOAT32,
            DataType.FLOAT64: iec61850.IEC61850_FLOAT64,
            DataType.ENUM: iec61850.IEC61850_ENUMERATED,
            DataType.OCTET_STRING_64: iec61850.IEC61850_OCTET_STRING_64,
            # DataType.OCTET_STRING_6: iec61850.IEC61850_OCTET_STRING_6,
            # DataType.OCTET_STRING_8: iec61850.IEC61850_OCTET_STRING_8,
            # DataType.VISIBLE_STRING_32: iec61850.IEC61850_VISIBLE_STRING_32,
            # DataType.VISIBLE_STRING_64: iec61850.IEC61850_VISIBLE_STRING_64,
            # DataType.VISIBLE_STRING_65: iec61850.IEC61850_VISIBLE_STRING_65,
            # DataType.VISIBLE_STRING_129: iec61850.IEC61850_VISIBLE_STRING_129,
            # DataType.VISIBLE_STRING_255: iec61850.IEC61850_VISIBLE_STRING_255,
            DataType.UNICODE_STRING_255: iec61850.IEC61850_UNICODE_STRING_255,
            DataType.TIMESTAMP: iec61850.IEC61850_TIMESTAMP,
            DataType.QUALITY: iec61850.IEC61850_QUALITY,
            # DataType.CHECK: iec61850.IEC61850_CHECK,
            # DataType.CODEDENUM: iec61850.IEC61850_CODEDENUM,
            # DataType.GENERIC_BITSTRING: iec61850.IEC61850_GENERIC_BITSTRING,
            # DataType.CONSTRUCTED: iec61850.IEC61850_CONSTRUCTED,
            # DataType.ENTRY_TIME: iec61850.IEC61850_ENTRY_TIME,
            # DataType.PHYCOMADDR: iec61850.IEC61850_PHYCOMADDR,
            # DataType.CURRENCY: iec61850.IEC61850_CURRENCY,
            # DataType.OPTFLDS: iec61850.IEC61850_OPTFLDS,
            # DataType.TRGOPS: iec61850.IEC61850_TRGOPS,
        }
        return type_map.get(data_type, iec61850.IEC61850_INT32)
    
    def _map_fc(self, fc: FunctionalConstraint) -> int:
        """映射功能约束到pyiec61850 FC"""
        fc_map = {
            FunctionalConstraint.ST: iec61850.IEC61850_FC_ST,
            FunctionalConstraint.MX: iec61850.IEC61850_FC_MX,
            FunctionalConstraint.SP: iec61850.IEC61850_FC_SP,
            FunctionalConstraint.SV: iec61850.IEC61850_FC_SV,
            FunctionalConstraint.CF: iec61850.IEC61850_FC_CF,
            FunctionalConstraint.DC: iec61850.IEC61850_FC_DC,
            FunctionalConstraint.SG: iec61850.IEC61850_FC_SG,
            FunctionalConstraint.SE: iec61850.IEC61850_FC_SE,
            FunctionalConstraint.SR: iec61850.IEC61850_FC_SR,
            FunctionalConstraint.OR: iec61850.IEC61850_FC_OR,
            FunctionalConstraint.BL: iec61850.IEC61850_FC_BL,
            FunctionalConstraint.EX: iec61850.IEC61850_FC_EX,
            FunctionalConstraint.CO: iec61850.IEC61850_FC_CO,
        }
        return fc_map.get(fc, iec61850.IEC61850_FC_ST)
    
    def _set_initial_value(self, da_node, value: Any, da_type: int):
        """设置数据属性的初始值"""
        try:
            mms_value = da_node.mmsValue
            if mms_value is None:
                return
            
            if da_type == iec61850.IEC61850_BOOLEAN:
                iec61850.MmsValue_setBoolean(mms_value, bool(value))
            elif da_type in [iec61850.IEC61850_INT8, iec61850.IEC61850_INT16, 
                            iec61850.IEC61850_INT32]:
                iec61850.MmsValue_setInt32(mms_value, int(value))
            elif da_type == iec61850.IEC61850_INT64:
                iec61850.MmsValue_setInt64(mms_value, int(value))
            elif da_type in [iec61850.IEC61850_INT8U, iec61850.IEC61850_INT16U,
                            iec61850.IEC61850_INT32U]:
                iec61850.MmsValue_setUint32(mms_value, int(value))
            elif da_type == iec61850.IEC61850_FLOAT32:
                iec61850.MmsValue_setFloat(mms_value, float(value))
            elif da_type == iec61850.IEC61850_FLOAT64:
                iec61850.MmsValue_setDouble(mms_value, float(value))
            elif da_type in [iec61850.IEC61850_VISIBLE_STRING_64, 
                            iec61850.IEC61850_VISIBLE_STRING_255]:
                iec61850.MmsValue_setVisibleString(mms_value, str(value))
        except Exception as e:
            logger.debug(f"Could not set initial value: {e}")
    
    # ========================================================================
    # IED管理
    # ========================================================================
    
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
        if not self.ied or not self._ied_server:
            return False
        
        da = self.ied.get_data_attribute(reference)
        if da:
            old_value = da.value
            if da.set_value(value):
                # 更新pyiec61850服务器中的值
                self._update_server_value(reference, value)
                self._notify_data_change(reference, old_value, value)
                return True
        return False
    
    def _update_server_value(self, reference: str, value: Any):
        """更新pyiec61850服务器中的数据值"""
        if not self._ied_server:
            return
        
        # 查找数据属性节点
        da_node = self._model_nodes.get(reference)
        if da_node is None:
            return
        
        try:
            # 锁定数据模型以进行更新
            iec61850.IedServer_lockDataModel(self._ied_server)
            
            # 根据类型更新值
            da_type = iec61850.DataAttribute_getType(da_node)
            
            if da_type == iec61850.IEC61850_BOOLEAN:
                iec61850.IedServer_updateBooleanAttributeValue(
                    self._ied_server, da_node, bool(value)
                )
            elif da_type in [iec61850.IEC61850_INT8, iec61850.IEC61850_INT16, 
                            iec61850.IEC61850_INT32]:
                iec61850.IedServer_updateInt32AttributeValue(
                    self._ied_server, da_node, int(value)
                )
            elif da_type == iec61850.IEC61850_INT64:
                iec61850.IedServer_updateInt64AttributeValue(
                    self._ied_server, da_node, int(value)
                )
            elif da_type in [iec61850.IEC61850_INT8U, iec61850.IEC61850_INT16U,
                            iec61850.IEC61850_INT32U]:
                iec61850.IedServer_updateUnsignedAttributeValue(
                    self._ied_server, da_node, int(value)
                )
            elif da_type == iec61850.IEC61850_FLOAT32:
                iec61850.IedServer_updateFloatAttributeValue(
                    self._ied_server, da_node, float(value)
                )
            elif da_type == iec61850.IEC61850_FLOAT64:
                iec61850.IedServer_updateFloatAttributeValue(
                    self._ied_server, da_node, float(value)
                )
            elif da_type in [iec61850.IEC61850_VISIBLE_STRING_64, 
                            iec61850.IEC61850_VISIBLE_STRING_255]:
                iec61850.IedServer_updateVisibleStringAttributeValue(
                    self._ied_server, da_node, str(value)
                )
            
            # 解锁数据模型
            iec61850.IedServer_unlockDataModel(self._ied_server)
            
        except Exception as e:
            logger.error(f"Failed to update server value: {e}")
            try:
                iec61850.IedServer_unlockDataModel(self._ied_server)
            except:
                pass
    
    # ========================================================================
    # 数据更新
    # ========================================================================
    
    def _update_loop(self):
        """数据更新循环"""
        import random
        
        while not self._stop_event.is_set():
            try:
                if self.config.enable_random_values and self.ied and self._ied_server:
                    self._simulate_data_update()
                
                # 更新连接客户端数量
                if self._ied_server:
                    num_connections = iec61850.IedServer_getNumberOfOpenConnections(self._ied_server)
                    self._update_client_tracking(num_connections)
                
            except Exception as e:
                self._log("error", f"Update loop error: {e}")
            
            # 等待下一个更新周期
            self._stop_event.wait(self.config.update_interval_ms / 1000.0)
    
    def _simulate_data_update(self):
        """模拟数据更新"""
        import random
        
        if not self.ied or not self._ied_server:
            return
        
        try:
            iec61850.IedServer_lockDataModel(self._ied_server)
            
            # 更新测量值
            for ld in self.ied.logical_devices.values():
                for ln in ld.logical_nodes.values():
                    if ln.ln_class == "MMXU":
                        # 更新功率
                        totw = ln.get_data_object("TotW")
                        if totw:
                            mag_attr = totw.get_attribute("mag")
                            if mag_attr:
                                new_value = (mag_attr.value or 0) + random.uniform(-10, 10)
                                mag_attr.set_value(new_value)
                                
                                ref = f"{ld.name}/{ln.name}.TotW.mag"
                                da_node = self._model_nodes.get(ref)
                                if da_node:
                                    iec61850.IedServer_updateFloatAttributeValue(
                                        self._ied_server, da_node, float(new_value)
                                    )
                        
                        # 更新频率
                        hz = ln.get_data_object("Hz")
                        if hz:
                            mag_attr = hz.get_attribute("mag")
                            if mag_attr:
                                new_value = 50.0 + random.uniform(-0.1, 0.1)
                                mag_attr.set_value(new_value)
                                
                                ref = f"{ld.name}/{ln.name}.Hz.mag"
                                da_node = self._model_nodes.get(ref)
                                if da_node:
                                    iec61850.IedServer_updateFloatAttributeValue(
                                        self._ied_server, da_node, float(new_value)
                                    )
            
            iec61850.IedServer_unlockDataModel(self._ied_server)
            
        except Exception as e:
            logger.error(f"Simulation update error: {e}")
            try:
                iec61850.IedServer_unlockDataModel(self._ied_server)
            except:
                pass
    
    def _update_client_tracking(self, num_connections: int):
        """更新客户端跟踪信息"""
        # 简化的客户端跟踪 - pyiec61850不提供详细的客户端信息
        # 我们只跟踪连接数量变化
        current_count = len(self._clients)
        
        if num_connections > current_count:
            # 新连接
            for i in range(num_connections - current_count):
                client_id = f"client_{datetime.now().timestamp()}_{i}"
                self._clients[client_id] = ClientConnection(
                    id=client_id,
                    address=("unknown", 0),
                )
                self._notify_connection_change(client_id, True)
        elif num_connections < current_count:
            # 断开连接
            clients_to_remove = list(self._clients.keys())[:(current_count - num_connections)]
            for client_id in clients_to_remove:
                del self._clients[client_id]
                self._notify_connection_change(client_id, False)
    
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
        num_connections = 0
        if self._ied_server:
            try:
                num_connections = iec61850.IedServer_getNumberOfOpenConnections(self._ied_server)
            except:
                num_connections = len(self._clients)
        
        return {
            "state": self.state.name,
            "address": f"{self.config.ip_address}:{self.config.port}",
            "ied_name": self.ied.name if self.ied else None,
            "client_count": num_connections,
            "config": {
                "update_interval_ms": self.config.update_interval_ms,
                "enable_random_values": self.config.enable_random_values,
                "enable_reporting": self.config.enable_reporting,
            }
        }
    
    def is_running(self) -> bool:
        """检查服务器是否正在运行"""
        if self._ied_server:
            return iec61850.IedServer_isRunning(self._ied_server)
        return False
