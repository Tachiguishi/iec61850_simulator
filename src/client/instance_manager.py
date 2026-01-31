"""
Client Instance Manager
=======================

管理多个IEC61850 Client实例
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml
from loguru import logger

from client.client_proxy import IEC61850ClientProxy, ClientConfig, ClientState, DataValue


@dataclass
class ClientInstance:
    """客户端实例信息"""
    id: str
    name: str
    config: ClientConfig
    proxy: IEC61850ClientProxy
    target_host: str = ""
    target_port: int = 102
    created_at: datetime = field(default_factory=datetime.now)
    
    @property
    def state(self) -> ClientState:
        return self.proxy.state
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state.name,
            "target_host": self.target_host,
            "target_port": self.target_port,
            "created_at": self.created_at.isoformat(),
        }


class ClientInstanceManager:
    """
    客户端实例管理器
    
    支持同时运行多个IEC61850 Client实例，每个实例可以：
    - 连接到不同的IED服务器
    - 独立进行数据读写操作
    - 有独立的生命周期状态
    """
    
    def __init__(self, socket_path: str, timeout_ms: int = 3000):
        self._socket_path = socket_path
        self._timeout_ms = timeout_ms
        self._instances: Dict[str, ClientInstance] = {}
        
        # 回调列表
        self._instance_added_callbacks: List[Callable[[ClientInstance], None]] = []
        self._instance_removed_callbacks: List[Callable[[str], None]] = []
        self._instance_state_callbacks: List[Callable[[str, ClientState], None]] = []
        self._data_callbacks: List[Callable[[str, str, Any], None]] = []  # instance_id, reference, value
        self._log_callbacks: List[Callable[[str, str, str], None]] = []  # instance_id, level, message
    
    # =========================================================================
    # 回调注册
    # =========================================================================
    
    def on_instance_added(self, callback: Callable[[ClientInstance], None]) -> None:
        """注册实例添加回调"""
        self._instance_added_callbacks.append(callback)
    
    def on_instance_removed(self, callback: Callable[[str], None]) -> None:
        """注册实例移除回调"""
        self._instance_removed_callbacks.append(callback)
    
    def on_instance_state_change(self, callback: Callable[[str, ClientState], None]) -> None:
        """注册实例状态变化回调"""
        self._instance_state_callbacks.append(callback)
    
    def on_data_change(self, callback: Callable[[str, str, Any], None]) -> None:
        """注册数据变化回调"""
        self._data_callbacks.append(callback)
    
    def on_log(self, callback: Callable[[str, str, str], None]) -> None:
        """注册日志回调"""
        self._log_callbacks.append(callback)
    
    # =========================================================================
    # 实例管理
    # =========================================================================
    
    def create_instance(
        self,
        name: str,
        config: Optional[ClientConfig] = None,
        instance_id: Optional[str] = None
    ) -> ClientInstance:
        """
        创建新的客户端实例
        
        Args:
            name: 实例名称
            config: 客户端配置，如果为None则使用默认配置
            instance_id: 实例ID，如果为None则自动生成
        
        Returns:
            创建的客户端实例
        """
        if instance_id is None:
            instance_id = str(uuid.uuid4())[:8]
        
        if config is None:
            config = ClientConfig()
        
        proxy = IEC61850ClientProxy(config, self._socket_path, self._timeout_ms)
        proxy.instance_id = instance_id  # 为proxy添加实例ID
        
        # 转发状态变化回调
        def on_state_change(state: ClientState):
            for callback in self._instance_state_callbacks:
                callback(instance_id, state)
        proxy.on_state_change(on_state_change)
        
        # 转发数据变化回调
        def on_data_change(reference: str, value: Any):
            for callback in self._data_callbacks:
                callback(instance_id, reference, value)
        proxy.on_data_change(on_data_change)
        
        # 转发日志回调
        def on_log(level: str, message: str):
            for callback in self._log_callbacks:
                callback(instance_id, level, message)
        proxy.on_log(on_log)
        
        instance = ClientInstance(
            id=instance_id,
            name=name,
            config=config,
            proxy=proxy,
        )
        
        self._instances[instance_id] = instance
        
        # 触发回调
        for callback in self._instance_added_callbacks:
            callback(instance)
        
        self._log(instance_id, "info", f"客户端实例 '{name}' 已创建 (ID: {instance_id})")
        
        return instance
    
    def remove_instance(self, instance_id: str) -> bool:
        """
        移除客户端实例
        
        如果实例已连接，会先断开连接。
        
        Args:
            instance_id: 实例ID
        
        Returns:
            是否成功移除
        """
        instance = self._instances.get(instance_id)
        if not instance:
            return False
        
        # 如果已连接，先断开
        if instance.state == ClientState.CONNECTED:
            instance.proxy.disconnect()
        
        del self._instances[instance_id]
        
        # 触发回调
        for callback in self._instance_removed_callbacks:
            callback(instance_id)
        
        self._log(instance_id, "info", f"客户端实例 '{instance.name}' 已移除")
        
        return True
    
    def get_instance(self, instance_id: str) -> Optional[ClientInstance]:
        """获取指定实例"""
        return self._instances.get(instance_id)
    
    def get_all_instances(self) -> List[ClientInstance]:
        """获取所有实例"""
        return list(self._instances.values())
    
    def get_connected_instances(self) -> List[ClientInstance]:
        """获取所有已连接的实例"""
        return [inst for inst in self._instances.values() if inst.state == ClientState.CONNECTED]
    
    # =========================================================================
    # 连接操作
    # =========================================================================
    
    def connect_instance(self, instance_id: str, host: str, port: int = 102) -> bool:
        """
        连接指定实例到服务器
        
        Args:
            instance_id: 实例ID
            host: 服务器IP地址
            port: 服务器端口
        
        Returns:
            是否成功连接
        """
        instance = self._instances.get(instance_id)
        if not instance:
            self._log(instance_id, "error", f"实例 {instance_id} 不存在")
            return False
        
        instance.target_host = host
        instance.target_port = port
        
        return instance.proxy.connect(host, port, instance.name)
    
    def disconnect_instance(self, instance_id: str) -> bool:
        """断开指定实例的连接"""
        instance = self._instances.get(instance_id)
        if not instance:
            return False
        
        return instance.proxy.disconnect()
    
    def disconnect_all_instances(self) -> None:
        """断开所有实例的连接"""
        for instance in self._instances.values():
            if instance.state == ClientState.CONNECTED:
                instance.proxy.disconnect()
    
    # =========================================================================
    # 数据操作
    # =========================================================================
    
    def browse_model(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """浏览指定实例的数据模型"""
        instance = self._instances.get(instance_id)
        if not instance:
            return None
        
        return instance.proxy.browse_data_model()
    
    def read_value(self, instance_id: str, reference: str) -> Optional[DataValue]:
        """读取指定实例的数据值"""
        instance = self._instances.get(instance_id)
        if not instance:
            return None
        
        return instance.proxy.read_value(reference)
    
    def read_values(self, instance_id: str, references: List[str]) -> Dict[str, DataValue]:
        """批量读取指定实例的数据值"""
        instance = self._instances.get(instance_id)
        if not instance:
            return {}
        
        return instance.proxy.read_values(references)
    
    def write_value(self, instance_id: str, reference: str, value: Any) -> bool:
        """写入指定实例的数据值"""
        instance = self._instances.get(instance_id)
        if not instance:
            return False
        
        return instance.proxy.write_value(reference, value)
    
    # =========================================================================
    # 快捷方法
    # =========================================================================
    
    def create_and_connect(
        self,
        name: str,
        host: str,
        port: int = 102,
        config: Optional[ClientConfig] = None
    ) -> Optional[ClientInstance]:
        """
        创建并连接一个实例
        
        Args:
            name: 实例名称
            host: 服务器IP地址
            port: 服务器端口
            config: 客户端配置
        
        Returns:
            创建的实例，如果连接失败返回None
        """
        instance = self.create_instance(name, config)
        
        if instance.proxy.connect(host, port, name):
            instance.target_host = host
            instance.target_port = port
            return instance
        else:
            self.remove_instance(instance.id)
            return None
    
    def get_instance_count(self) -> int:
        """获取实例数量"""
        return len(self._instances)
    
    def get_connected_count(self) -> int:
        """获取已连接的实例数量"""
        return len(self.get_connected_instances())
    
    # =========================================================================
    # 内部方法
    # =========================================================================
    
    def _log(self, instance_id: str, level: str, message: str) -> None:
        """记录日志"""
        for callback in self._log_callbacks:
            callback(instance_id, level, message)
        
        if level == "error":
            logger.error(f"[{instance_id}] {message}")
        elif level == "warning":
            logger.warning(f"[{instance_id}] {message}")
        else:
            logger.info(f"[{instance_id}] {message}")
    
    # =========================================================================
    # 持久化
    # =========================================================================
    
    def save_to_file(self, file_path: str | Path) -> bool:
        """
        保存实例配置到YAML文件
        
        Args:
            file_path: 配置文件路径
        
        Returns:
            是否保存成功
        """
        try:
            instances_data = []
            for instance in self._instances.values():
                instance_data = {
                    "id": instance.id,
                    "name": instance.name,
                    "target_host": instance.target_host,
                    "target_port": instance.target_port,
                    "config": {
                        "timeout_ms": instance.config.timeout_ms,
                        "retry_count": instance.config.retry_count,
                        "retry_interval_ms": instance.config.retry_interval_ms,
                        "polling_interval_ms": instance.config.polling_interval_ms,
                    },
                    "created_at": instance.created_at.isoformat(),
                }
                instances_data.append(instance_data)
            
            data = {
                "version": "1.0",
                "type": "client_instances",
                "instances": instances_data,
            }
            
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
            
            logger.info(f"保存 {len(instances_data)} 个客户端实例配置到 {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存实例配置失败: {e}")
            return False
    
    def load_from_file(self, file_path: str | Path, auto_connect: bool = False) -> int:
        """
        从YAML文件加载实例配置
        
        Args:
            file_path: 配置文件路径
            auto_connect: 是否自动连接加载的实例
        
        Returns:
            成功加载的实例数量
        """
        try:
            path = Path(file_path)
            if not path.exists():
                logger.warning(f"配置文件不存在: {file_path}")
                return 0
            
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if not data or data.get("type") != "client_instances":
                logger.error("无效的客户端实例配置文件")
                return 0
            
            instances_data = data.get("instances", [])
            loaded_count = 0
            
            for inst_data in instances_data:
                try:
                    config_data = inst_data.get("config", {})
                    config = ClientConfig(
                        timeout_ms=config_data.get("timeout_ms", 5000),
                        retry_count=config_data.get("retry_count", 3),
                        retry_interval_ms=config_data.get("retry_interval_ms", 1000),
                        polling_interval_ms=config_data.get("polling_interval_ms", 1000),
                    )
                    
                    instance = self.create_instance(
                        name=inst_data.get("name", "Client"),
                        config=config,
                        instance_id=inst_data.get("id"),
                    )
                    
                    instance.target_host = inst_data.get("target_host", "127.0.0.1")
                    instance.target_port = inst_data.get("target_port", 102)
                    
                    if auto_connect:
                        self.connect_instance(
                            instance.id,
                            instance.target_host,
                            instance.target_port
                        )
                    
                    loaded_count += 1
                    
                except Exception as e:
                    logger.error(f"加载实例失败: {e}")
                    continue
            
            logger.info(f"从 {file_path} 加载了 {loaded_count} 个客户端实例")
            return loaded_count
            
        except Exception as e:
            logger.error(f"加载实例配置失败: {e}")
            return 0
