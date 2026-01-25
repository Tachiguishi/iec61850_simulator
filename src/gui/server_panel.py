"""
Server Panel
============

服务端模式GUI面板
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QSpinBox, QCheckBox, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QTextEdit, QComboBox, QFrame, QMessageBox,
    QFileDialog
)

sys.path.insert(0, str(Path(__file__).parent.parent))

from gui.data_tree_widget import DataTreeWidget
from server.iec61850_server import IEC61850Server, ServerConfig, ServerState
from core.data_model import DataModelManager


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
        
        self._init_ui()
        self._init_server()
        self._setup_timers()
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        
        # 主分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧 - 配置和控制
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)
        
        # 右侧 - 数据视图
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)
        
        splitter.setSizes([400, 800])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        layout.addWidget(splitter)
    
    def _create_left_panel(self) -> QWidget:
        """创建左侧面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 服务器配置组
        config_group = QGroupBox("服务器配置")
        config_layout = QGridLayout(config_group)
        
        # IP地址
        config_layout.addWidget(QLabel("IP地址:"), 0, 0)
        self.ip_input = QLineEdit("0.0.0.0")
        self.ip_input.setPlaceholderText("0.0.0.0")
        config_layout.addWidget(self.ip_input, 0, 1)
        
        # 端口
        config_layout.addWidget(QLabel("端口:"), 1, 0)
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(102)
        config_layout.addWidget(self.port_input, 1, 1)
        
        # 最大连接数
        config_layout.addWidget(QLabel("最大连接:"), 2, 0)
        self.max_conn_input = QSpinBox()
        self.max_conn_input.setRange(1, 100)
        self.max_conn_input.setValue(10)
        config_layout.addWidget(self.max_conn_input, 2, 1)
        
        # 更新间隔
        config_layout.addWidget(QLabel("更新间隔(ms):"), 3, 0)
        self.update_interval_input = QSpinBox()
        self.update_interval_input.setRange(100, 10000)
        self.update_interval_input.setValue(1000)
        self.update_interval_input.setSingleStep(100)
        config_layout.addWidget(self.update_interval_input, 3, 1)
        
        # 启用随机值
        self.random_values_check = QCheckBox("启用随机值仿真")
        self.random_values_check.setChecked(False)
        config_layout.addWidget(self.random_values_check, 4, 0, 1, 2)
        
        # 启用报告
        self.reporting_check = QCheckBox("启用报告功能")
        self.reporting_check.setChecked(True)
        config_layout.addWidget(self.reporting_check, 5, 0, 1, 2)
        
        layout.addWidget(config_group)
        
        # 控制按钮组
        control_group = QGroupBox("服务控制")
        control_layout = QVBoxLayout(control_group)
        
        btn_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("▶ 启动服务")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        self.start_btn.clicked.connect(self.start_server)
        btn_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("⏹ 停止服务")
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        self.stop_btn.clicked.connect(self.stop_server)
        btn_layout.addWidget(self.stop_btn)
        
        control_layout.addLayout(btn_layout)
        
        # 状态显示
        self.status_label = QLabel("状态: 已停止")
        self.status_label.setStyleSheet("font-weight: bold; color: #6c757d;")
        control_layout.addWidget(self.status_label)
        
        layout.addWidget(control_group)
        
        # IED配置组
        ied_group = QGroupBox("IED数据模型")
        ied_layout = QVBoxLayout(ied_group)
        
        # IED名称
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("IED名称:"))
        self.ied_name_input = QLineEdit("SimulatedIED")
        name_layout.addWidget(self.ied_name_input)
        ied_layout.addLayout(name_layout)
        
        # 数据模型操作按钮
        model_btn_layout = QHBoxLayout()
        
        load_model_btn = QPushButton("📂 加载模型")
        load_model_btn.clicked.connect(self._load_data_model)
        model_btn_layout.addWidget(load_model_btn)
        
        create_default_btn = QPushButton("🔧 创建默认")
        create_default_btn.clicked.connect(self._create_default_model)
        model_btn_layout.addWidget(create_default_btn)
        
        export_model_btn = QPushButton("💾 导出模型")
        export_model_btn.clicked.connect(self._export_data_model)
        model_btn_layout.addWidget(export_model_btn)
        
        ied_layout.addLayout(model_btn_layout)
        
        layout.addWidget(ied_group)
        
        # 客户端连接组
        client_group = QGroupBox("客户端连接")
        client_layout = QVBoxLayout(client_group)
        
        self.client_table = QTableWidget()
        self.client_table.setColumnCount(3)
        self.client_table.setHorizontalHeaderLabels(["地址", "连接时间", "订阅数"])
        self.client_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.client_table.setMaximumHeight(150)
        client_layout.addWidget(self.client_table)
        
        # 客户端计数
        self.client_count_label = QLabel("连接数: 0")
        client_layout.addWidget(self.client_count_label)
        
        layout.addWidget(client_group)
        
        layout.addStretch()
        
        return panel
    
    def _create_right_panel(self) -> QWidget:
        """创建右侧面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 标签页
        tabs = QTabWidget()
        
        # 数据浏览标签
        data_tab = QWidget()
        data_layout = QVBoxLayout(data_tab)
        
        self.data_tree = DataTreeWidget()
        self.data_tree.value_changed.connect(self._on_value_changed)
        self.data_tree.item_selected.connect(self._on_item_selected)
        data_layout.addWidget(self.data_tree)
        
        tabs.addTab(data_tab, "📊 数据浏览")
        
        # 数据编辑标签
        edit_tab = QWidget()
        edit_layout = QVBoxLayout(edit_tab)
        
        # 引用选择
        ref_layout = QHBoxLayout()
        ref_layout.addWidget(QLabel("数据引用:"))
        self.ref_input = QLineEdit()
        self.ref_input.setPlaceholderText("如: SimulatedIEDPROT/PTOC1.Op.general")
        ref_layout.addWidget(self.ref_input)
        edit_layout.addLayout(ref_layout)
        
        # 值编辑
        value_layout = QHBoxLayout()
        value_layout.addWidget(QLabel("值:"))
        self.value_input = QLineEdit()
        value_layout.addWidget(self.value_input)
        
        set_value_btn = QPushButton("设置值")
        set_value_btn.clicked.connect(self._set_value)
        value_layout.addWidget(set_value_btn)
        edit_layout.addLayout(value_layout)
        
        # 快捷操作
        quick_group = QGroupBox("快捷操作")
        quick_layout = QGridLayout(quick_group)
        
        # 断路器控制
        quick_layout.addWidget(QLabel("断路器 XCBR1:"), 0, 0)
        xcbr_on_btn = QPushButton("合闸")
        xcbr_on_btn.clicked.connect(lambda: self._quick_set("XCBR1.Pos.stVal", 2))
        quick_layout.addWidget(xcbr_on_btn, 0, 1)
        xcbr_off_btn = QPushButton("分闸")
        xcbr_off_btn.clicked.connect(lambda: self._quick_set("XCBR1.Pos.stVal", 1))
        quick_layout.addWidget(xcbr_off_btn, 0, 2)
        
        # 保护动作
        quick_layout.addWidget(QLabel("保护 PTOC1:"), 1, 0)
        ptoc_trip_btn = QPushButton("触发动作")
        ptoc_trip_btn.clicked.connect(lambda: self._quick_set("PTOC1.Op.general", True))
        quick_layout.addWidget(ptoc_trip_btn, 1, 1)
        ptoc_reset_btn = QPushButton("复归")
        ptoc_reset_btn.clicked.connect(lambda: self._quick_set("PTOC1.Op.general", False))
        quick_layout.addWidget(ptoc_reset_btn, 1, 2)
        
        edit_layout.addWidget(quick_group)
        edit_layout.addStretch()
        
        tabs.addTab(edit_tab, "✏️ 数据编辑")
        
        # 仿真设置标签
        sim_tab = QWidget()
        sim_layout = QVBoxLayout(sim_tab)
        
        # 测量值仿真
        meas_group = QGroupBox("测量值仿真")
        meas_layout = QGridLayout(meas_group)
        
        meas_layout.addWidget(QLabel("有功功率 TotW:"), 0, 0)
        self.totw_input = QSpinBox()
        self.totw_input.setRange(-10000, 10000)
        self.totw_input.setValue(1000)
        meas_layout.addWidget(self.totw_input, 0, 1)
        
        meas_layout.addWidget(QLabel("无功功率 TotVAr:"), 1, 0)
        self.totvar_input = QSpinBox()
        self.totvar_input.setRange(-10000, 10000)
        self.totvar_input.setValue(200)
        meas_layout.addWidget(self.totvar_input, 1, 1)
        
        meas_layout.addWidget(QLabel("频率 Hz:"), 2, 0)
        self.hz_input = QLineEdit("50.0")
        meas_layout.addWidget(self.hz_input, 2, 1)
        
        apply_meas_btn = QPushButton("应用测量值")
        apply_meas_btn.clicked.connect(self._apply_measurements)
        meas_layout.addWidget(apply_meas_btn, 3, 0, 1, 2)
        
        sim_layout.addWidget(meas_group)
        sim_layout.addStretch()
        
        tabs.addTab(sim_tab, "🎛️ 仿真设置")
        
        layout.addWidget(tabs)
        
        # 选中项详情
        detail_group = QGroupBox("选中项详情")
        detail_layout = QVBoxLayout(detail_group)
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMaximumHeight(100)
        detail_layout.addWidget(self.detail_text)
        
        layout.addWidget(detail_group)
        
        return panel
    
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
        self.ip_input.setText(config.ip_address)
        self.port_input.setValue(config.port)
        self.max_conn_input.setValue(config.max_connections)
        self.update_interval_input.setValue(config.update_interval_ms)
        self.random_values_check.setChecked(config.enable_random_values)
        self.reporting_check.setChecked(config.enable_reporting)
    
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
        self.server.config.ip_address = self.ip_input.text()
        self.server.config.port = self.port_input.value()
        self.server.config.max_connections = self.max_conn_input.value()
        self.server.config.update_interval_ms = self.update_interval_input.value()
        self.server.config.enable_random_values = self.random_values_check.isChecked()
        self.server.config.enable_reporting = self.reporting_check.isChecked()
        
        # 确保有IED
        if not self.server.ied:
            self._create_default_model()
        
        if self.server.start():
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
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
            
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self._disable_config_inputs(False)
            
            # 停止定时器
            self.refresh_timer.stop()
            self.client_timer.stop()
    
    def _disable_config_inputs(self, disabled: bool):
        """禁用/启用配置输入"""
        self.ip_input.setDisabled(disabled)
        self.port_input.setDisabled(disabled)
        self.max_conn_input.setDisabled(disabled)
        self.ied_name_input.setDisabled(disabled)
    
    # ========================================================================
    # 数据模型管理
    # ========================================================================
    
    def _create_default_model(self):
        """创建默认数据模型"""
        name = self.ied_name_input.text() or "SimulatedIED"
        ied = self.data_model_manager.create_default_ied(name)
        
        if self.server:
            self.server.load_ied(ied)
        
        self._update_data_tree()
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
                self.ied_name_input.setText(ied.name)
                self._update_data_tree()
                self.log_message.emit("info", f"已加载IED: {ied.name}")
            else:
                QMessageBox.critical(self, "错误", "加载数据模型失败")
    
    def _export_data_model(self):
        """导出数据模型"""
        if not self.server or not self.server.ied:
            QMessageBox.warning(self, "警告", "没有可导出的数据模型")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出数据模型", f"{self.server.ied.name}.yaml",
            "YAML Files (*.yaml *.yml);;All Files (*)"
        )
        
        if file_path:
            if self.data_model_manager.export_to_yaml(self.server.ied, file_path):
                self.log_message.emit("info", f"已导出数据模型到: {file_path}")
            else:
                QMessageBox.critical(self, "错误", "导出失败")
    
    def _update_data_tree(self):
        """更新数据树"""
        if self.server and self.server.ied:
            self.data_tree.load_ied(self.server.ied.to_dict())
    
    # ========================================================================
    # 数据操作
    # ========================================================================
    
    def _set_value(self):
        """设置数据值"""
        ref = self.ref_input.text().strip()
        value_str = self.value_input.text().strip()
        
        if not ref or not value_str:
            return
        
        # 转换值
        try:
            if value_str.lower() in ("true", "false"):
                value = value_str.lower() == "true"
            elif "." in value_str:
                value = float(value_str)
            else:
                value = int(value_str)
        except ValueError:
            value = value_str
        
        if self.server:
            if self.server.set_data_value(ref, value):
                self.log_message.emit("info", f"已设置 {ref} = {value}")
            else:
                self.log_message.emit("error", f"设置失败: {ref}")
    
    def _quick_set(self, partial_ref: str, value):
        """快捷设置"""
        if self.server and self.server.ied:
            # 构建完整引用
            ied_name = self.server.ied.name
            full_ref = f"{ied_name}PROT/{partial_ref}"
            
            if self.server.set_data_value(full_ref, value):
                self.log_message.emit("info", f"已设置 {partial_ref} = {value}")
    
    def _apply_measurements(self):
        """应用测量值"""
        if not self.server or not self.server.ied:
            return
        
        ied_name = self.server.ied.name
        
        # 设置有功功率
        totw_ref = f"{ied_name}MEAS/MMXU1.TotW.mag"
        self.server.set_data_value(totw_ref, float(self.totw_input.value()))
        
        # 设置频率
        try:
            hz_value = float(self.hz_input.text())
            hz_ref = f"{ied_name}MEAS/MMXU1.Hz.mag"
            self.server.set_data_value(hz_ref, hz_value)
        except ValueError:
            pass
        
        self.log_message.emit("info", "已应用测量值")
    
    def _on_value_changed(self, reference: str, value):
        """处理树形控件的值变化"""
        if self.server:
            self.server.set_data_value(reference, value)
    
    def _on_item_selected(self, reference: str):
        """处理选中项变化"""
        self.ref_input.setText(reference)
        
        if self.server:
            value = self.server.get_data_value(reference)
            if value is not None:
                self.value_input.setText(str(value))
            
            # 显示详情
            da = self.server.ied.get_data_attribute(reference) if self.server.ied else None
            if da:
                self.detail_text.setText(
                    f"引用: {reference}\n"
                    f"类型: {da.data_type.value}\n"
                    f"值: {da.value}\n"
                    f"质量: {da.quality}\n"
                    f"时间戳: {da.timestamp}"
                )
    
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
        
        self.client_table.setRowCount(len(clients))
        for i, client in enumerate(clients):
            self.client_table.setItem(i, 0, QTableWidgetItem(client["id"]))
            self.client_table.setItem(i, 1, QTableWidgetItem(
                client["connected_at"].split("T")[1][:8] if "T" in client["connected_at"] else ""
            ))
            self.client_table.setItem(i, 2, QTableWidgetItem(str(len(client["subscriptions"]))))
        
        self.client_count_label.setText(f"连接数: {len(clients)}")
    
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
        self.status_label.setText(f"状态: {text}")
        self.status_label.setStyleSheet(f"font-weight: bold; color: {color};")
    
    def _on_connection_changed(self, client_id: str, connected: bool):
        """连接变化回调"""
        action = "连接" if connected else "断开"
        self.log_message.emit("info", f"客户端{action}: {client_id}")
    
    def _on_data_changed(self, reference: str, old_value, new_value):
        """数据变化回调"""
        self.data_tree.update_value(reference, new_value)
