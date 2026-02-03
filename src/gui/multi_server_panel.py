"""
Multi-Instance Server Panel
============================

支持多个IEC61850 Server实例的管理面板
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QStackedWidget, QLabel, QMessageBox, QFileDialog,
    QPushButton, QComboBox, QSpinBox, QGroupBox, QGridLayout
)

sys.path.insert(0, str(Path(__file__).parent.parent))

from gui.instance_list_widget import InstanceListWidget
from gui.server_panel import ServerPanel
from server.instance_manager import ServerInstanceManager, ServerInstance
from server.server_proxy import ServerConfig, ServerState


class MultiServerPanel(QWidget):
    """
    多实例服务器面板
    
    功能：
    - 管理多个Server实例
    - 每个实例独立配置
    - 实例间独立的数据模型
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
        
        self.instance_manager = ServerInstanceManager(socket_path, timeout_ms)
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
        
        # 左侧：实例列表和全局网络配置
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(4, 4, 4, 4)
        
        # 全局网络接口配置
        self.network_group = QGroupBox("全局网络接口")
        network_layout = QGridLayout()
        
        network_layout.addWidget(QLabel("网络接口:"), 0, 0)
        self.interface_combo = QComboBox()
        self.interface_combo.setToolTip("选择网络接口用于IP配置（对所有实例生效）")
        network_layout.addWidget(self.interface_combo, 0, 1)
        
        network_layout.addWidget(QLabel("前缀长度:"), 1, 0)
        self.prefix_len_input = QSpinBox()
        self.prefix_len_input.setRange(1, 32)
        self.prefix_len_input.setValue(24)
        self.prefix_len_input.setToolTip("IP地址的前缀长度（CIDR格式）")
        network_layout.addWidget(self.prefix_len_input, 1, 1)
        
        self.set_interface_btn = QPushButton("应用配置")
        self.set_interface_btn.clicked.connect(self._set_network_interface)
        network_layout.addWidget(self.set_interface_btn, 2, 0, 1, 2)
        
        self.network_group.setLayout(network_layout)
        left_layout.addWidget(self.network_group)
        
        # 实例列表
        self.instance_list = InstanceListWidget("server")
        left_layout.addWidget(self.instance_list)
        
        # 统计信息
        self.stats_label = QLabel("实例: 0 | 运行中: 0")
        self.stats_label.setStyleSheet("color: #666; font-size: 11px;")
        left_layout.addWidget(self.stats_label)
        
        left_panel.setMinimumWidth(250)
        left_panel.setMaximumWidth(350)
        
        # 加载网络接口列表
        self._load_network_interfaces()
        
        # 右侧：实例详情（使用StackedWidget切换不同实例的配置界面）
        self.detail_stack = QStackedWidget()
        
        # 空白占位页面
        empty_page = QWidget()
        empty_layout = QVBoxLayout(empty_page)
        empty_label = QLabel("请选择或创建一个服务器实例")
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
        self._instance_panels: Dict[str, ServerPanel] = {}
    
    def _connect_signals(self):
        """连接信号"""
        self.instance_list.instance_created.connect(self._on_create_instance)
        self.instance_list.instance_removed.connect(self._on_remove_instance)
        self.instance_list.instance_started.connect(self._on_start_instance)
        self.instance_list.instance_stopped.connect(self._on_stop_instance)
        self.instance_list.instance_selected.connect(self._on_select_instance)
    
    # =========================================================================
    # 实例操作
    # =========================================================================
    
    def _on_create_instance(self, config: Dict):
        """创建实例"""
        try:
            server_config = ServerConfig(
                ip_address=config.get("ip_address", "0.0.0.0"),
                port=config.get("port", 102),
                max_connections=config.get("max_connections", 10),
            )
            
            instance = self.instance_manager.create_instance(
                name=config.get("name", "Server"),
                config=server_config,
            )
            
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
    
    def _on_start_instance(self, instance_id: str):
        """启动实例"""
        self.instance_manager.start_instance(instance_id)
    
    def _on_stop_instance(self, instance_id: str):
        """停止实例"""
        self.instance_manager.stop_instance(instance_id)
    
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
    
    def _on_instance_added(self, instance: ServerInstance):
        """实例添加回调"""
        details = f"{instance.config.ip_address}:{instance.config.port}"
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
    
    def _on_instance_state_change(self, instance_id: str, state: ServerState):
        """实例状态变化回调"""
        self.instance_list.update_instance_state(instance_id, state.name)
        self._update_stats()
    
    def _on_instance_log(self, instance_id: str, level: str, message: str):
        """实例日志回调"""
        instance = self.instance_manager.get_instance(instance_id)
        name = instance.name if instance else instance_id
        self.log_message.emit(level, f"[{name}] {message}")
    
    # =========================================================================
    # 网络接口管理
    # =========================================================================
    
    def _load_network_interfaces(self):
        """加载网络接口列表"""
        # 需要从实例管理器获取一个代理来调用后端
        # 使用第一个实例的proxy，如果没有则创建临时的
        proxy = None
        for instance in self.instance_manager.get_all_instances():
            proxy = instance.proxy
            break
        
        if not proxy:
            # 创建临时proxy用于查询
            from server.server_proxy import IEC61850ServerProxy, ServerConfig
            ipc_config = self.config.get("ipc", {})
            socket_path = ipc_config.get("socket_path", "/tmp/iec61850_simulator.sock")
            timeout_ms = ipc_config.get("request_timeout_ms", 3000)
            proxy = IEC61850ServerProxy(ServerConfig(), socket_path, timeout_ms)
        
        interfaces, current = proxy.get_network_interfaces()
        
        self.interface_combo.clear()
        self.interface_combo.addItem("(未选择)", None)
        
        for iface in interfaces:
            name = iface.get("name", "")
            is_up = iface.get("is_up", False)
            addresses = iface.get("addresses", [])
            
            # 显示网卡名称、状态和IP地址
            status = "UP" if is_up else "DOWN"
            addr_str = ", ".join(addresses[:2]) if addresses else "无IP"
            display_text = f"{name} [{status}] - {addr_str}"
            
            self.interface_combo.addItem(display_text, name)
        
        # 设置当前选择
        if current:
            current_name = current.get("name", "")
            prefix_len = current.get("prefix_len", 24)
            
            # 在下拉框中选中当前接口
            for i in range(self.interface_combo.count()):
                if self.interface_combo.itemData(i) == current_name:
                    self.interface_combo.setCurrentIndex(i)
                    break
            
            self.prefix_len_input.setValue(prefix_len)
            self.log_message.emit("info", f"当前全局网络接口: {current_name} (prefix_len: {prefix_len})")
        else:
            self.log_message.emit("info", "未配置全局网络接口")
    
    def _set_network_interface(self):
        """设置网络接口"""
        selected_index = self.interface_combo.currentIndex()
        if selected_index <= 0:  # 第一项是"(未选择)"
            QMessageBox.warning(self, "警告", "请选择一个网络接口")
            return
        
        interface_name = self.interface_combo.itemData(selected_index)
        prefix_len = self.prefix_len_input.value()
        
        if not interface_name:
            return
        
        # 使用任意一个实例的proxy调用后端
        proxy = None
        for instance in self.instance_manager.instances.values():
            proxy = instance.proxy
            break
        
        if not proxy:
            # 创建临时proxy
            from server.server_proxy import IEC61850ServerProxy, ServerConfig
            ipc_config = self.config.get("ipc", {})
            socket_path = ipc_config.get("socket_path", "/tmp/iec61850_simulator.sock")
            timeout_ms = ipc_config.get("request_timeout_ms", 3000)
            proxy = IEC61850ServerProxy(ServerConfig(), socket_path, timeout_ms)
        
        # 调用后端设置接口
        if proxy.set_network_interface(interface_name, prefix_len):
            QMessageBox.information(
                self, 
                "成功", 
                f"已设置全局网络接口: {interface_name}\n子网掩码位数: {prefix_len}\n\n"
                "此配置对所有服务器实例生效。\n"
                "当服务器使用非 0.0.0.0 或 127.* 的IP地址时，\n"
                "系统会自动在此接口上配置相应的IP地址。"
            )
            self.log_message.emit("info", f"全局网络接口已设置: {interface_name} (/{prefix_len})")
        else:
            QMessageBox.critical(self, "错误", "设置网络接口失败")
    
    # =========================================================================
    # 面板管理
    # =========================================================================
    
    def _create_instance_panel(self, instance: ServerInstance):
        """为实例创建配置面板"""
        # 创建单独的配置副本
        instance_config = dict(self.config)
        instance_config["server"] = {
            "network": {
                "ip_address": instance.config.ip_address,
                "port": instance.config.port,
                "max_connections": instance.config.max_connections,
            },
            "simulation": {
                "update_interval_ms": instance.config.update_interval_ms,
                "enable_random_values": instance.config.enable_random_values,
            },
            "reporting": {
                "enabled": instance.config.enable_reporting,
            }
        }
        
        panel = ServerPanel(instance_config, self)
        panel.server = instance.proxy
        panel.log_message.connect(
            lambda level, msg, iid=instance.id: self._on_instance_log(iid, level, msg)
        )
        
        self._instance_panels[instance.id] = panel
        self.detail_stack.addWidget(panel)
        
        # 自动选中新创建的实例
        self.instance_list.select_instance(instance.id)
    
    def _update_stats(self):
        """更新统计信息"""
        total = self.instance_manager.get_instance_count()
        running = self.instance_manager.get_running_count()
        self.stats_label.setText(f"实例: {total} | 运行中: {running}")
    
    # =========================================================================
    # 公共方法
    # =========================================================================
    
    def start_all(self):
        """启动所有实例"""
        for instance in self.instance_manager.get_all_instances():
            if instance.state == ServerState.STOPPED:
                self.instance_manager.start_instance(instance.id)
    
    def stop_all(self):
        """停止所有实例"""
        self.instance_manager.stop_all_instances()
    
    def get_current_instance(self) -> Optional[ServerInstance]:
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
    
    def start_server(self) -> bool:
        """启动当前选中的服务器实例（兼容单实例接口）"""
        instance = self.get_current_instance()
        if instance:
            return self.instance_manager.start_instance(instance.id)
        return False
    
    def stop_server(self):
        """停止当前选中的服务器实例（兼容单实例接口）"""
        instance = self.get_current_instance()
        if instance:
            self.instance_manager.stop_instance(instance.id)
    
    def refresh_data(self):
        """刷新当前选中实例的数据（兼容单实例接口）"""
        panel = self._instance_panels.get(self._current_instance_id)
        if panel and hasattr(panel, 'refresh_data'):
            panel.refresh_data()
    
    def save_instances(self, file_path: str) -> bool:
        """保存所有实例配置到文件"""
        return self.instance_manager.save_to_file(file_path)
    
    def load_instances(self, file_path: str, auto_start: bool = False) -> int:
        """从文件加载实例配置"""
        count = self.instance_manager.load_from_file(file_path, auto_start)
        # 为加载的实例创建面板
        for instance in self.instance_manager.get_all_instances():
            if instance.id not in self._instance_panels:
                self._create_instance_panel(instance)
        return count
    
    def import_from_scd(self, base_port: int = 102, auto_start: bool = False) -> int:
        """
        打开文件对话框导入SCD文件中的IED
        
        Args:
            base_port: 起始端口号
            auto_start: 是否自动启动导入的实例
        
        Returns:
            导入的实例数量
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择SCD文件",
            "",
            "SCD Files (*.scd *.icd *.cid);;XML Files (*.xml);;All Files (*)"
        )
        
        if not file_path:
            return 0
        
        instances = self.instance_manager.import_from_scd(file_path, base_port, auto_start)
        
        # 为导入的实例创建面板
        for instance in instances:
            self._create_instance_panel(instance)
        
        if instances:
            QMessageBox.information(
                self,
                "导入成功",
                f"成功从SCD文件导入 {len(instances)} 个IED实例"
            )
        else:
            QMessageBox.warning(
                self,
                "导入失败",
                "未能从SCD文件导入任何IED"
            )
        
        return len(instances)
