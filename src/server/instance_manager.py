"""
Server Instance Manager
=======================

管理多个IEC61850 Server实例
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml
from loguru import logger

from core.data_model import IED
from core.data_model_manager import DataModelManager
from core.scd_parser import SCDParser
from server.server_proxy import IEC61850ServerProxy, ServerConfig, ServerState


@dataclass
class ServerInstance:
    """服务器实例信息"""
    id: str
    name: str
    config: ServerConfig
    proxy: IEC61850ServerProxy
    ied: Optional[IED] = None
    scl_file_path: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    
    @property
    def state(self) -> ServerState:
        return self.proxy.state
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state.name,
            "ip_address": self.config.ip_address,
            "port": self.config.port,
            "created_at": self.created_at.isoformat(),
            "ied_name": self.ied.name if self.ied else None,
        }


class ServerInstanceManager:
    """
    服务器实例管理器
    
    支持同时运行多个IEC61850 Server实例，每个实例有独立的：
    - 配置（IP地址、端口等）
    - IED数据模型
    - 生命周期状态
    """
    
    def __init__(self, socket_path: str, timeout_ms: int = 3000):
        self._socket_path = socket_path
        self._timeout_ms = timeout_ms
        self._instances: Dict[str, ServerInstance] = {}
        
        # 回调列表
        self._instance_added_callbacks: List[Callable[[ServerInstance], None]] = []
        self._instance_removed_callbacks: List[Callable[[str], None]] = []
        self._instance_state_callbacks: List[Callable[[str, ServerState], None]] = []
        self._log_callbacks: List[Callable[[str, str, str], None]] = []  # instance_id, level, message
    
    # =========================================================================
    # 回调注册
    # =========================================================================
    
    def on_instance_added(self, callback: Callable[[ServerInstance], None]) -> None:
        """注册实例添加回调"""
        self._instance_added_callbacks.append(callback)
    
    def on_instance_removed(self, callback: Callable[[str], None]) -> None:
        """注册实例移除回调"""
        self._instance_removed_callbacks.append(callback)
    
    def on_instance_state_change(self, callback: Callable[[str, ServerState], None]) -> None:
        """注册实例状态变化回调"""
        self._instance_state_callbacks.append(callback)
    
    def on_log(self, callback: Callable[[str, str, str], None]) -> None:
        """注册日志回调"""
        self._log_callbacks.append(callback)
    
    # =========================================================================
    # 实例管理
    # =========================================================================
    
    def create_instance(
        self,
        name: str,
        config: Optional[ServerConfig] = None,
        instance_id: Optional[str] = None
    ) -> ServerInstance:
        """
        创建新的服务器实例
        
        Args:
            name: 实例名称
            config: 服务器配置，如果为None则使用默认配置
            instance_id: 实例ID，如果为None则自动生成
        
        Returns:
            创建的服务器实例
        """
        if instance_id is None:
            instance_id = str(uuid.uuid4())[:8]
        
        if config is None:
            config = ServerConfig()
        
        # 检查端口冲突
        for inst in self._instances.values():
            if inst.config.port == config.port and inst.state == ServerState.RUNNING:
                raise ValueError(f"端口 {config.port} 已被实例 '{inst.name}' 使用")
        
        proxy = IEC61850ServerProxy(config, self._socket_path, self._timeout_ms)
        proxy.instance_id = instance_id  # 为proxy添加实例ID
        
        # 转发状态变化回调
        def on_state_change(state: ServerState):
            for callback in self._instance_state_callbacks:
                callback(instance_id, state)
        proxy.on_state_change(on_state_change)
        
        # 转发日志回调
        def on_log(level: str, message: str):
            for callback in self._log_callbacks:
                callback(instance_id, level, message)
        proxy.on_log(on_log)
        
        instance = ServerInstance(
            id=instance_id,
            name=name,
            config=config,
            proxy=proxy,
        )
        
        self._instances[instance_id] = instance
        
        # 触发回调
        for callback in self._instance_added_callbacks:
            callback(instance)
        
        self._log(instance_id, "info", f"实例 '{name}' 已创建 (ID: {instance_id})")
        
        return instance
    
    def remove_instance(self, instance_id: str) -> bool:
        """
        移除服务器实例
        
        如果实例正在运行，会先停止它。
        
        Args:
            instance_id: 实例ID
        
        Returns:
            是否成功移除
        """
        instance = self._instances.get(instance_id)
        if not instance:
            return False
        
        # 如果正在运行，先停止
        if instance.state == ServerState.RUNNING:
            instance.proxy.stop()
        
        del self._instances[instance_id]
        
        # 触发回调
        for callback in self._instance_removed_callbacks:
            callback(instance_id)
        
        self._log(instance_id, "info", f"实例 '{instance.name}' 已移除")
        
        return True
    
    def get_instance(self, instance_id: str) -> Optional[ServerInstance]:
        """获取指定实例"""
        return self._instances.get(instance_id)
    
    def get_all_instances(self) -> List[ServerInstance]:
        """获取所有实例"""
        return list(self._instances.values())
    
    def get_running_instances(self) -> List[ServerInstance]:
        """获取所有运行中的实例"""
        return [inst for inst in self._instances.values() if inst.state == ServerState.RUNNING]
    
    # =========================================================================
    # 实例操作
    # =========================================================================
    
    def start_instance(self, instance_id: str) -> bool:
        """启动指定实例"""
        instance = self._instances.get(instance_id)
        if not instance:
            self._log(instance_id, "error", f"实例 {instance_id} 不存在")
            return False

        if not instance.ied:
            self._log(instance_id, "error", "实例未加载IED模型")
            return False

        return instance.proxy.start(instance.ied)
    
    def stop_instance(self, instance_id: str) -> bool:
        """停止指定实例"""
        instance = self._instances.get(instance_id)
        if not instance:
            return False
        
        return instance.proxy.stop()
    
    def stop_all_instances(self) -> None:
        """停止所有实例"""
        for instance in self._instances.values():
            if instance.state == ServerState.RUNNING:
                instance.proxy.stop()
    
    def load_model(self, instance_id: str, ied: IED) -> bool:
        """为指定实例加载数据模型"""
        instance = self._instances.get(instance_id)
        if not instance:
            return False
        instance.ied = ied
        instance.proxy.load_model(ied)
        return True
    
    def set_value(self, instance_id: str, reference: str, value: Any) -> bool:
        """设置指定实例的数据值"""
        instance = self._instances.get(instance_id)
        if not instance:
            return False
        
        instance.proxy.set_data_value(reference, value)
        return True
    
    def get_values(self, instance_id: str, references: List[str]) -> Dict[str, Any]:
        """获取指定实例的数据值"""
        instance = self._instances.get(instance_id)
        if not instance:
            return {}
        
        return instance.proxy.get_values(references)
    
    # =========================================================================
    # 快捷方法
    # =========================================================================
    
    def create_and_start(
        self,
        name: str,
        config: Optional[ServerConfig] = None,
        ied: Optional[IED] = None
    ) -> Optional[ServerInstance]:
        """
        创建并启动一个实例
        
        Args:
            name: 实例名称
            config: 服务器配置
            ied: IED数据模型
        
        Returns:
            创建的实例，如果启动失败返回None
        """
        instance = self.create_instance(name, config)
        
        if ied:
            instance.ied = ied
            instance.proxy.load_model(ied)
        else:
            # 创建默认模型
            dm = DataModelManager()
            instance.ied = dm.create_default_ied()
            instance.proxy.load_model(instance.ied)
        
        if instance.proxy.start(instance.ied):
            return instance
        else:
            self.remove_instance(instance.id)
            return None
    
    def get_instance_count(self) -> int:
        """获取实例数量"""
        return len(self._instances)
    
    def get_running_count(self) -> int:
        """获取运行中的实例数量"""
        return len(self.get_running_instances())
    
    # =========================================================================
    # 批量导入
    # =========================================================================
    
    def import_from_scd(
        self,
        scd_path: str | Path,
        base_port: int = 102,
        auto_start: bool = False
    ) -> List[ServerInstance]:
        """
        从SCD文件批量导入IED，为每个IED创建一个服务器实例
        
        Args:
            scd_path: SCD文件路径
            base_port: 起始端口号，后续IED依次递增
            auto_start: 是否自动启动导入的实例
        
        Returns:
            创建的实例列表
        """
        parser = SCDParser()
        ieds = parser.parse(scd_path)
        
        if not ieds:
            logger.warning(f"SCD文件中没有找到IED: {scd_path}")
            return []
        
        created_instances = []
        current_port = base_port
        
        for ied in ieds:
            try:
                # 检查端口是否被占用
                while self._is_port_in_use(current_port):
                    current_port += 1
                
                config = ServerConfig(
                    ip_address="0.0.0.0",
                    port=current_port,
                )
                
                instance = self.create_instance(
                    name=ied.name,
                    config=config,
                )
                
                # 加载IED模型
                instance.ied = ied
                instance.scl_file_path = str(scd_path)
                instance.proxy.load_model(ied)
                
                if auto_start:
                    self.start_instance(instance.id)
                
                created_instances.append(instance)
                current_port += 1
                
                self._log(instance.id, "info", f"从SCD导入IED '{ied.name}' (端口: {instance.config.port})")
                
            except Exception as e:
                logger.error(f"导入IED '{ied.name}' 失败: {e}")
                continue
        
        logger.info(f"从 {scd_path} 导入了 {len(created_instances)} 个IED")
        return created_instances
    
    def _is_port_in_use(self, port: int) -> bool:
        """检查端口是否被实例使用"""
        for inst in self._instances.values():
            if inst.config.port == port:
                return True
        return False
    
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
                    "config": {
                        "ip_address": instance.config.ip_address,
                        "port": instance.config.port,
                        "max_connections": instance.config.max_connections,
                        "update_interval_ms": instance.config.update_interval_ms,
                        "enable_random_values": instance.config.enable_random_values,
                        "enable_reporting": instance.config.enable_reporting,
                    },
                    "created_at": instance.created_at.isoformat(),
                }
                # 保存IED配置路径（如果有）
                if instance.ied and instance.scl_file_path:
                    instance_data["scl_file"] = instance.scl_file_path
                instances_data.append(instance_data)
            
            data = {
                "version": "1.0",
                "type": "server_instances",
                "instances": instances_data,
            }
            
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
            
            logger.info(f"保存 {len(instances_data)} 个服务器实例配置到 {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存实例配置失败: {e}")
            return False
    
    def load_from_file(self, file_path: str | Path, auto_start: bool = False) -> int:
        """
        从YAML文件加载实例配置
        
        Args:
            file_path: 配置文件路径
            auto_start: 是否自动启动加载的实例
        
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
            
            if not data or data.get("type") != "server_instances":
                logger.error("无效的服务器实例配置文件")
                return 0
            
            instances_data = data.get("instances", [])
            loaded_count = 0
            
            for inst_data in instances_data:
                try:
                    config_data = inst_data.get("config", {})
                    config = ServerConfig(
                        ip_address=config_data.get("ip_address", "0.0.0.0"),
                        port=config_data.get("port", 102),
                        max_connections=config_data.get("max_connections", 10),
                        update_interval_ms=config_data.get("update_interval_ms", 1000),
                        enable_random_values=config_data.get("enable_random_values", True),
                        enable_reporting=config_data.get("enable_reporting", True),
                    )
                    
                    instance = self.create_instance(
                        name=inst_data.get("name", "Server"),
                        config=config,
                        instance_id=inst_data.get("id"),
                    )
                    
                    # 加载SCL文件（如果指定）
                    scl_file = inst_data.get("scl_file")
                    if scl_file and Path(scl_file).exists():
                        dm = DataModelManager()
                        ied = dm.load_from_scl(scl_file)
                        if ied:
                            instance.ied = ied
                            instance.scl_file_path = scl_file
                            instance.proxy.load_model(ied)
                    
                    if auto_start:
                        self.start_instance(instance.id)
                    
                    loaded_count += 1
                    
                except Exception as e:
                    logger.error(f"加载实例失败: {e}")
                    continue
            
            logger.info(f"从 {file_path} 加载了 {loaded_count} 个服务器实例")
            return loaded_count
            
        except Exception as e:
            logger.error(f"加载实例配置失败: {e}")
            return 0
