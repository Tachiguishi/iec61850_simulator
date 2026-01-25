"""
Server Panel
============

服务端模式GUI面板
使用UI文件进行界面绘制
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidgetItem, QHeaderView,
    QMessageBox, QFileDialog
)
from PyQt6 import uic

sys.path.insert(0, str(Path(__file__).parent.parent))

from gui.data_tree_widget import DataTreeWidget
from server.iec61850_server import IEC61850Server, ServerConfig, ServerState
from core.data_model import DataModelManager

# UI文件路径
UI_DIR = Path(__file__).parent / "ui"


class ServerPanel(QWidget):
    """
    服务端面板
    
    功能：
    - 服务器配置
    - IED数据模型管理
    - 数据监控
    - 客户端连接管理
    - 数据仿真
    """
    
    log_message = pyqtSignal(str, str)  # level, message
    
    def __init__(self, config: Dict, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.config = config
        self.server: Optional[IEC61850Server] = None
        self.data_model_manager = DataModelManager()
        
        # 加载UI文件
        uic.loadUi(UI_DIR / "server_panel.ui", self)
        
        self._init_ui()
        self._init_server()
        self._connect_signals()
        self._setup_timers()
    
    def _init_ui(self):
        """初始化UI附加设置"""
        # 设置分割器大小
        self.mainSplitter.setSizes([400, 800])
        self.mainSplitter.setStretchFactor(0, 1)
        self.mainSplitter.setStretchFactor(1, 2)
        
        # 设置连接表格表头
        self.connectionTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        # 设置数据表格表头
        self.dataTable.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        
        # 添加DataTreeWidget到树标签页
        self.data_tree = DataTreeWidget()
        self.treeTabLayout.addWidget(self.data_tree)
    
    def _connect_signals(self):
        """连接信号"""
        # 控制按钮
        self.startBtn.clicked.connect(self.start_server)
        self.stopBtn.clicked.connect(self.stop_server)
        
        # 模型操作
        self.loadModelBtn.clicked.connect(self._load_data_model)
        self.reloadModelBtn.clicked.connect(self._create_default_model)
        
        # 仿真脚本
        self.runScriptBtn.clicked.connect(self._run_simulation_script)
        self.stopScriptBtn.clicked.connect(self._stop_simulation_script)
        
        # 数据树信号
        self.data_tree.value_changed.connect(self._on_value_changed)
        self.data_tree.item_selected.connect(self._on_item_selected)
    
    def _init_server(self):
        """初始化服务器"""
        server_config = self.config.get("server", {})
        
        config = ServerConfig(
            ip_address=server_config.get("network", {}).get("ip_address", "0.0.0.0"),
            port=server_config.get("network", {}).get("port", 102),
            max_connections=server_config.get("network", {}).get("max_connections", 10),
            update_interval_ms=server_config.get("simulation", {}).get("update_interval_ms", 1000),
            enable_random_values=server_config.get("simulation", {}).get("enable_random_values", False),
            enable_reporting=server_config.get("reporting", {}).get("enabled", True),
        )
        
        self.server = IEC61850Server(config)
        
        # 连接回调
        self.server.on_state_change(self._on_server_state_changed)
        self.server.on_connection_change(self._on_connection_changed)
        self.server.on_data_change(self._on_data_changed)
        self.server.on_log(lambda level, msg: self.log_message.emit(level, msg))
        
        # 更新UI
        self.ipInput.setText(config.ip_address)
        self.portInput.setValue(config.port)
        self.maxConnInput.setValue(config.max_connections)
        self.updateIntervalInput.setValue(config.update_interval_ms)
        self.randomValuesCheck.setChecked(config.enable_random_values)
        self.reportingCheck.setChecked(config.enable_reporting)
    
    def _setup_timers(self):
        """设置定时器"""
        # 数据刷新定时器
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_data_view)
        
        # 客户端列表刷新定时器
        self.client_timer = QTimer(self)
        self.client_timer.timeout.connect(self._refresh_client_list)
    
    # ========================================================================
    # 服务控制
    # ========================================================================
    
    def start_server(self) -> bool:
        """启动服务器"""
        if not self.server:
            return False
        
        # 更新配置
        self.server.config.ip_address = self.ipInput.text()
        self.server.config.port = self.portInput.value()
        self.server.config.max_connections = self.maxConnInput.value()
        self.server.config.update_interval_ms = self.updateIntervalInput.value()
        self.server.config.enable_random_values = self.randomValuesCheck.isChecked()
        self.server.config.enable_reporting = self.reportingCheck.isChecked()
        
        # 确保有IED
        if not self.server.ied:
            self._create_default_model()
        
        if self.server.start():
            self.startBtn.setEnabled(False)
            self.stopBtn.setEnabled(True)
            self._disable_config_inputs(True)
            
            # 启动定时器
            self.refresh_timer.start(500)
            self.client_timer.start(2000)
            
            return True
        return False
    
    def stop_server(self):
        """停止服务器"""
        if self.server:
            self.server.stop()
            
            self.startBtn.setEnabled(True)
            self.stopBtn.setEnabled(False)
            self._disable_config_inputs(False)
            
            # 停止定时器
            self.refresh_timer.stop()
            self.client_timer.stop()
    
    def _disable_config_inputs(self, disabled: bool):
        """禁用/启用配置输入"""
        self.ipInput.setDisabled(disabled)
        self.portInput.setDisabled(disabled)
        self.maxConnInput.setDisabled(disabled)
    
    # ========================================================================
    # 数据模型管理
    # ========================================================================
    
    def _create_default_model(self):
        """创建默认数据模型"""
        name = "SimulatedIED"
        ied = self.data_model_manager.create_default_ied(name)
        
        if self.server:
            self.server.load_ied(ied)
        
        self._update_data_tree()
        self.modelInfoLabel.setText(f"已加载: {name}")
        self.log_message.emit("info", f"已创建默认IED: {name}")
    
    def _load_data_model(self):
        """加载数据模型"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "加载数据模型", "",
            "YAML Files (*.yaml *.yml);;All Files (*)"
        )
        
        if file_path:
            ied = self.data_model_manager.load_from_yaml(file_path)
            if ied:
                if self.server:
                    self.server.load_ied(ied)
                self.modelInfoLabel.setText(f"已加载: {ied.name}")
                self._update_data_tree()
                self.log_message.emit("info", f"已加载IED: {ied.name}")
            else:
                QMessageBox.critical(self, "错误", "加载数据模型失败")
    
    def _update_data_tree(self):
        """更新数据树"""
        if self.server and self.server.ied:
            self.data_tree.load_ied(self.server.ied.to_dict())
    
    # ========================================================================
    # 仿真
    # ========================================================================
    
    def _run_simulation_script(self):
        """运行仿真脚本"""
        script = self.simScriptEdit.toPlainText()
        if not script.strip():
            return
        
        self.log_message.emit("info", "仿真脚本功能待实现")
    
    def _stop_simulation_script(self):
        """停止仿真脚本"""
        self.log_message.emit("info", "停止仿真脚本")
    
    # ========================================================================
    # 数据操作
    # ========================================================================
    
    def _on_value_changed(self, reference: str, value):
        """处理树形控件的值变化"""
        if self.server:
            self.server.set_data_value(reference, value)
    
    def _on_item_selected(self, reference: str):
        """处理选中项变化"""
        pass
    
    # ========================================================================
    # 刷新和回调
    # ========================================================================
    
    def refresh_data(self):
        """刷新数据"""
        self._refresh_data_view()
    
    def _refresh_data_view(self):
        """刷新数据视图"""
        if not self.server or not self.server.ied:
            return
        
        # 收集所有值
        values = {}
        for ref in self.server.ied.get_all_references():
            da = self.server.ied.get_data_attribute(ref)
            if da:
                values[ref] = {
                    "value": da.value,
                    "quality": da.quality,
                    "timestamp": da.timestamp.isoformat() if da.timestamp else None
                }
        
        self.data_tree.update_values(values)
    
    def _refresh_client_list(self):
        """刷新客户端列表"""
        if not self.server:
            return
        
        clients = self.server.get_connected_clients()
        
        self.connectionTable.setRowCount(len(clients))
        for i, client in enumerate(clients):
            self.connectionTable.setItem(i, 0, QTableWidgetItem(client["id"]))
            self.connectionTable.setItem(i, 1, QTableWidgetItem(
                client["connected_at"].split("T")[1][:8] if "T" in client["connected_at"] else ""
            ))
            self.connectionTable.setItem(i, 2, QTableWidgetItem("已连接"))
    
    def _on_server_state_changed(self, state: ServerState):
        """服务器状态变化回调"""
        state_text = {
            ServerState.STOPPED: ("已停止", "#6c757d"),
            ServerState.STARTING: ("正在启动...", "#ffc107"),
            ServerState.RUNNING: ("运行中", "#28a745"),
            ServerState.STOPPING: ("正在停止...", "#ffc107"),
            ServerState.ERROR: ("错误", "#dc3545"),
        }
        
        text, color = state_text.get(state, ("未知", "#6c757d"))
        self.statusLabel.setText(f"状态: {text}")
        self.statusLabel.setStyleSheet(f"color: {color}; font-size: 11px;")
    
    def _on_connection_changed(self, client_id: str, connected: bool):
        """连接变化回调"""
        action = "连接" if connected else "断开"
        self.log_message.emit("info", f"客户端{action}: {client_id}")
    
    def _on_data_changed(self, reference: str, old_value, new_value):
        """数据变化回调"""
        self.data_tree.update_value(reference, new_value)
