"""
Multi-Instance Client Panel
============================

支持多个IEC61850 Client实例的管理面板
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QStackedWidget, QLabel, QMessageBox
)

sys.path.insert(0, str(Path(__file__).parent.parent))

from gui.instance_list_widget import InstanceListWidget
from gui.client_panel import ClientPanel
from client.instance_manager import ClientInstanceManager, ClientInstance
from client.client_proxy import ClientConfig, ClientState


class MultiClientPanel(QWidget):
    """
    多实例客户端面板
    
    功能：
    - 管理多个Client实例
    - 每个实例可连接到不同的服务器
    - 独立的数据浏览和操作
    - 统一的实例列表视图
    """
    
    log_message = pyqtSignal(str, str)  # level, message
    
    def __init__(self, config: Dict, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.config = config
        self._current_instance_id: Optional[str] = None
        
        # 初始化实例管理器
        ipc_config = config.get("ipc", {})
        socket_path = ipc_config.get("socket_path", "/tmp/iec61850_simulator.sock")
        timeout_ms = ipc_config.get("request_timeout_ms", 3000)
        
        self.instance_manager = ClientInstanceManager(socket_path, timeout_ms)
        self._setup_manager_callbacks()
        
        self._init_ui()
        self._connect_signals()
    
    def _setup_manager_callbacks(self):
        """设置实例管理器回调"""
        self.instance_manager.on_instance_added(self._on_instance_added)
        self.instance_manager.on_instance_removed(self._on_instance_removed)
        self.instance_manager.on_instance_state_change(self._on_instance_state_change)
        self.instance_manager.on_log(self._on_instance_log)
    
    def _init_ui(self):
        """初始化UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 左侧：实例列表
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(4, 4, 4, 4)
        
        self.instance_list = InstanceListWidget("client")
        left_layout.addWidget(self.instance_list)
        
        # 统计信息
        self.stats_label = QLabel("实例: 0 | 已连接: 0")
        self.stats_label.setStyleSheet("color: #666; font-size: 11px;")
        left_layout.addWidget(self.stats_label)
        
        left_panel.setMinimumWidth(250)
        left_panel.setMaximumWidth(350)
        
        # 右侧：实例详情
        self.detail_stack = QStackedWidget()
        
        # 空白占位页面
        empty_page = QWidget()
        empty_layout = QVBoxLayout(empty_page)
        empty_label = QLabel("请选择或创建一个客户端实例")
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_label.setStyleSheet("color: #888; font-size: 14px;")
        empty_layout.addWidget(empty_label)
        self.detail_stack.addWidget(empty_page)
        
        # 分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.detail_stack)
        splitter.setSizes([280, 720])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        
        layout.addWidget(splitter)
        
        # 实例面板映射
        self._instance_panels: Dict[str, ClientPanel] = {}
    
    def _connect_signals(self):
        """连接信号"""
        self.instance_list.instance_created.connect(self._on_create_instance)
        self.instance_list.instance_removed.connect(self._on_remove_instance)
        self.instance_list.instance_started.connect(self._on_connect_instance)
        self.instance_list.instance_stopped.connect(self._on_disconnect_instance)
        self.instance_list.instance_selected.connect(self._on_select_instance)
    
    # =========================================================================
    # 实例操作
    # =========================================================================
    
    def _on_create_instance(self, config: Dict):
        """创建实例"""
        try:
            client_config = ClientConfig()
            
            instance = self.instance_manager.create_instance(
                name=config.get("name", "Client"),
                config=client_config,
            )
            
            # 存储目标服务器信息
            instance.target_host = config.get("host", "127.0.0.1")
            instance.target_port = config.get("port", 102)
            
            # 创建对应的面板
            self._create_instance_panel(instance)
            
        except ValueError as e:
            QMessageBox.warning(self, "创建失败", str(e))
    
    def _on_remove_instance(self, instance_id: str):
        """移除实例"""
        instance = self.instance_manager.get_instance(instance_id)
        if not instance:
            return
        
        reply = QMessageBox.question(
            self, "确认移除",
            f"确定要移除实例 '{instance.name}' 吗?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.instance_manager.remove_instance(instance_id)
    
    def _on_connect_instance(self, instance_id: str):
        """连接实例"""
        instance = self.instance_manager.get_instance(instance_id)
        if instance:
            self.instance_manager.connect_instance(
                instance_id,
                instance.target_host,
                instance.target_port
            )
    
    def _on_disconnect_instance(self, instance_id: str):
        """断开实例"""
        self.instance_manager.disconnect_instance(instance_id)
    
    def _on_select_instance(self, instance_id: str):
        """选择实例"""
        self._current_instance_id = instance_id
        
        # 切换详情面板
        panel = self._instance_panels.get(instance_id)
        if panel:
            self.detail_stack.setCurrentWidget(panel)
    
    # =========================================================================
    # 实例管理器回调
    # =========================================================================
    
    def _on_instance_added(self, instance: ClientInstance):
        """实例添加回调"""
        details = f"→ {instance.target_host}:{instance.target_port}"
        self.instance_list.add_instance(
            instance.id,
            instance.name,
            instance.state.name,
            details
        )
        self._update_stats()
    
    def _on_instance_removed(self, instance_id: str):
        """实例移除回调"""
        self.instance_list.remove_instance(instance_id)
        
        # 移除面板
        panel = self._instance_panels.pop(instance_id, None)
        if panel:
            self.detail_stack.removeWidget(panel)
            panel.deleteLater()
        
        # 如果移除的是当前选中的，切换到空白页
        if self._current_instance_id == instance_id:
            self._current_instance_id = None
            self.detail_stack.setCurrentIndex(0)
        
        self._update_stats()
    
    def _on_instance_state_change(self, instance_id: str, state: ClientState):
        """实例状态变化回调"""
        self.instance_list.update_instance_state(instance_id, state.name)
        self._update_stats()
    
    def _on_instance_log(self, instance_id: str, level: str, message: str):
        """实例日志回调"""
        instance = self.instance_manager.get_instance(instance_id)
        name = instance.name if instance else instance_id
        self.log_message.emit(level, f"[{name}] {message}")
    
    # =========================================================================
    # 面板管理
    # =========================================================================
    
    def _create_instance_panel(self, instance: ClientInstance):
        """为实例创建配置面板"""
        # 创建单独的配置副本
        instance_config = dict(self.config)
        instance_config["client"] = {
            "connection": {
                "timeout_ms": instance.config.timeout_ms,
                "retry_count": instance.config.retry_count,
                "retry_interval_ms": instance.config.retry_interval_ms,
            },
            "subscription": {
                "polling_interval_ms": instance.config.polling_interval_ms,
            },
            "saved_servers": [
                {
                    "name": "目标服务器",
                    "ip": instance.target_host,
                    "port": instance.target_port,
                }
            ]
        }
        
        panel = ClientPanel(instance_config, self)
        panel.client = instance.proxy
        panel.log_message.connect(
            lambda level, msg, iid=instance.id: self._on_instance_log(iid, level, msg)
        )
        
        # 预填充连接信息
        panel.ipInput.setText(instance.target_host)
        panel.portInput.setValue(instance.target_port)
        
        self._instance_panels[instance.id] = panel
        self.detail_stack.addWidget(panel)
        
        # 自动选中新创建的实例
        self.instance_list.select_instance(instance.id)
    
    def _update_stats(self):
        """更新统计信息"""
        total = self.instance_manager.get_instance_count()
        connected = self.instance_manager.get_connected_count()
        self.stats_label.setText(f"实例: {total} | 已连接: {connected}")
    
    # =========================================================================
    # 公共方法
    # =========================================================================
    
    def connect_all(self):
        """连接所有实例"""
        for instance in self.instance_manager.get_all_instances():
            if instance.state == ClientState.DISCONNECTED:
                self.instance_manager.connect_instance(
                    instance.id,
                    instance.target_host,
                    instance.target_port
                )
    
    def disconnect_all(self):
        """断开所有实例"""
        self.instance_manager.disconnect_all_instances()
    
    def get_current_instance(self) -> Optional[ClientInstance]:
        """获取当前选中的实例"""
        if self._current_instance_id:
            return self.instance_manager.get_instance(self._current_instance_id)
        return None
    
    def get_all_instances(self):
        """获取所有实例"""
        return self.instance_manager.get_all_instances()
    
    # =========================================================================
    # 兼容性方法（与单实例面板接口一致）
    # =========================================================================
    
    def connect(self) -> bool:
        """连接当前选中的客户端实例（兼容单实例接口）"""
        instance = self.get_current_instance()
        if instance:
            return self.instance_manager.connect_instance(
                instance.id,
                instance.target_host,
                instance.target_port
            )
        return False
    
    def disconnect(self):
        """断开当前选中的客户端实例（兼容单实例接口）"""
        instance = self.get_current_instance()
        if instance:
            self.instance_manager.disconnect_instance(instance.id)
    
    def refresh_data(self):
        """刷新当前选中实例的数据（兼容单实例接口）"""
        panel = self._instance_panels.get(self._current_instance_id)
        if panel and hasattr(panel, 'refresh_data'):
            panel.refresh_data()
    
    def save_instances(self, file_path: str) -> bool:
        """保存所有实例配置到文件"""
        return self.instance_manager.save_to_file(file_path)
    
    def load_instances(self, file_path: str, auto_connect: bool = False) -> int:
        """从文件加载实例配置"""
        count = self.instance_manager.load_from_file(file_path, auto_connect)
        # 为加载的实例创建面板
        for instance in self.instance_manager.get_all_instances():
            if instance.id not in self._instance_panels:
                self._create_instance_panel(instance)
        return count
