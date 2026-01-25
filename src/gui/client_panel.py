"""
Client Panel
============

客户端模式GUI面板
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QSpinBox, QCheckBox, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QTextEdit, QComboBox, QFrame, QMessageBox,
    QListWidget, QListWidgetItem, QDialog, QDialogButtonBox
)

sys.path.insert(0, str(Path(__file__).parent.parent))

from gui.data_tree_widget import DataTreeWidget
from client.iec61850_client import IEC61850Client, ClientConfig, ClientState


class ConnectionDialog(QDialog):
    """连接对话框"""
    
    def __init__(self, saved_servers: List[Dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("连接到服务器")
        self.setMinimumWidth(400)
        
        self.saved_servers = saved_servers
        
        layout = QVBoxLayout(self)
        
        # 保存的服务器列表
        saved_group = QGroupBox("已保存的服务器")
        saved_layout = QVBoxLayout(saved_group)
        
        self.server_list = QListWidget()
        for server in saved_servers:
            item = QListWidgetItem(f"{server['name']} ({server['ip']}:{server['port']})")
            item.setData(Qt.ItemDataRole.UserRole, server)
            self.server_list.addItem(item)
        self.server_list.itemDoubleClicked.connect(self._on_server_selected)
        saved_layout.addWidget(self.server_list)
        
        layout.addWidget(saved_group)
        
        # 手动输入
        manual_group = QGroupBox("手动连接")
        manual_layout = QGridLayout(manual_group)
        
        manual_layout.addWidget(QLabel("名称:"), 0, 0)
        self.name_input = QLineEdit("新连接")
        manual_layout.addWidget(self.name_input, 0, 1)
        
        manual_layout.addWidget(QLabel("IP地址:"), 1, 0)
        self.ip_input = QLineEdit("127.0.0.1")
        manual_layout.addWidget(self.ip_input, 1, 1)
        
        manual_layout.addWidget(QLabel("端口:"), 2, 0)
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(102)
        manual_layout.addWidget(self.port_input, 2, 1)
        
        layout.addWidget(manual_group)
        
        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _on_server_selected(self, item: QListWidgetItem):
        """选择已保存的服务器"""
        server = item.data(Qt.ItemDataRole.UserRole)
        if server:
            self.name_input.setText(server.get("name", ""))
            self.ip_input.setText(server.get("ip", ""))
            self.port_input.setValue(server.get("port", 102))
    
    def get_connection_info(self) -> Dict:
        """获取连接信息"""
        return {
            "name": self.name_input.text(),
            "ip": self.ip_input.text(),
            "port": self.port_input.value(),
        }


class ClientPanel(QWidget):
    """
    客户端面板
    
    功能：
    - 连接到IED服务器
    - 浏览数据模型
    - 读取/写入数据
    - 控制操作
    - 数据订阅
    """
    
    log_message = pyqtSignal(str, str)  # level, message
    
    def __init__(self, config: Dict, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.config = config
        self.client: Optional[IEC61850Client] = None
        
        self._init_ui()
        self._init_client()
        self._setup_timers()
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        
        # 主分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧 - 连接和控制
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
        
        # 连接配置组
        conn_group = QGroupBox("连接配置")
        conn_layout = QGridLayout(conn_group)
        
        # IP地址
        conn_layout.addWidget(QLabel("IP地址:"), 0, 0)
        self.ip_input = QLineEdit("127.0.0.1")
        conn_layout.addWidget(self.ip_input, 0, 1)
        
        # 端口
        conn_layout.addWidget(QLabel("端口:"), 1, 0)
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(102)
        conn_layout.addWidget(self.port_input, 1, 1)
        
        # 连接名称
        conn_layout.addWidget(QLabel("连接名称:"), 2, 0)
        self.name_input = QLineEdit("测试连接")
        conn_layout.addWidget(self.name_input, 2, 1)
        
        # 超时设置
        conn_layout.addWidget(QLabel("超时(ms):"), 3, 0)
        self.timeout_input = QSpinBox()
        self.timeout_input.setRange(1000, 30000)
        self.timeout_input.setValue(5000)
        conn_layout.addWidget(self.timeout_input, 3, 1)
        
        # 自动重连
        self.auto_reconnect_check = QCheckBox("自动重连")
        self.auto_reconnect_check.setChecked(True)
        conn_layout.addWidget(self.auto_reconnect_check, 4, 0, 1, 2)
        
        # 快速连接按钮
        quick_conn_btn = QPushButton("📋 选择已保存服务器...")
        quick_conn_btn.clicked.connect(self._show_connection_dialog)
        conn_layout.addWidget(quick_conn_btn, 5, 0, 1, 2)
        
        layout.addWidget(conn_group)
        
        # 控制按钮组
        control_group = QGroupBox("连接控制")
        control_layout = QVBoxLayout(control_group)
        
        btn_layout = QHBoxLayout()
        
        self.connect_btn = QPushButton("🔗 连接")
        self.connect_btn.setMinimumHeight(40)
        self.connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        self.connect_btn.clicked.connect(self.connect)
        btn_layout.addWidget(self.connect_btn)
        
        self.disconnect_btn = QPushButton("❌ 断开")
        self.disconnect_btn.setMinimumHeight(40)
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.setStyleSheet("""
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
        self.disconnect_btn.clicked.connect(self.disconnect)
        btn_layout.addWidget(self.disconnect_btn)
        
        control_layout.addLayout(btn_layout)
        
        # 状态显示
        self.status_label = QLabel("状态: 未连接")
        self.status_label.setStyleSheet("font-weight: bold; color: #6c757d;")
        control_layout.addWidget(self.status_label)
        
        layout.addWidget(control_group)
        
        # 服务器信息组
        info_group = QGroupBox("服务器信息")
        info_layout = QVBoxLayout(info_group)
        
        self.server_info_text = QTextEdit()
        self.server_info_text.setReadOnly(True)
        self.server_info_text.setMaximumHeight(120)
        self.server_info_text.setPlaceholderText("连接后显示服务器信息...")
        info_layout.addWidget(self.server_info_text)
        
        layout.addWidget(info_group)
        
        # 数据操作组
        operation_group = QGroupBox("数据操作")
        operation_layout = QVBoxLayout(operation_group)
        
        # 读取按钮
        read_btn = QPushButton("📖 读取所有数据")
        read_btn.clicked.connect(self._read_all_data)
        operation_layout.addWidget(read_btn)
        
        # 浏览数据模型按钮
        browse_btn = QPushButton("🌲 浏览数据模型")
        browse_btn.clicked.connect(self._browse_data_model)
        operation_layout.addWidget(browse_btn)
        
        # 轮询设置
        poll_layout = QHBoxLayout()
        poll_layout.addWidget(QLabel("轮询间隔(ms):"))
        self.poll_interval_input = QSpinBox()
        self.poll_interval_input.setRange(100, 10000)
        self.poll_interval_input.setValue(1000)
        poll_layout.addWidget(self.poll_interval_input)
        
        self.polling_check = QCheckBox("启用")
        self.polling_check.stateChanged.connect(self._toggle_polling)
        poll_layout.addWidget(self.polling_check)
        
        operation_layout.addLayout(poll_layout)
        
        layout.addWidget(operation_group)
        
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
        self.data_tree.item_double_clicked.connect(self._on_item_double_clicked)
        data_layout.addWidget(self.data_tree)
        
        tabs.addTab(data_tab, "📊 数据浏览")
        
        # 数据读写标签
        rw_tab = QWidget()
        rw_layout = QVBoxLayout(rw_tab)
        
        # 读取操作
        read_group = QGroupBox("读取数据")
        read_layout = QVBoxLayout(read_group)
        
        ref_layout = QHBoxLayout()
        ref_layout.addWidget(QLabel("数据引用:"))
        self.read_ref_input = QLineEdit()
        self.read_ref_input.setPlaceholderText("如: SimulatedIEDPROT/PTOC1.Op.general")
        ref_layout.addWidget(self.read_ref_input)
        
        read_btn = QPushButton("读取")
        read_btn.clicked.connect(self._read_single_value)
        ref_layout.addWidget(read_btn)
        read_layout.addLayout(ref_layout)
        
        # 读取结果
        self.read_result_text = QTextEdit()
        self.read_result_text.setReadOnly(True)
        self.read_result_text.setMaximumHeight(80)
        read_layout.addWidget(self.read_result_text)
        
        rw_layout.addWidget(read_group)
        
        # 写入操作
        write_group = QGroupBox("写入数据")
        write_layout = QVBoxLayout(write_group)
        
        write_ref_layout = QHBoxLayout()
        write_ref_layout.addWidget(QLabel("数据引用:"))
        self.write_ref_input = QLineEdit()
        write_ref_layout.addWidget(self.write_ref_input)
        write_layout.addLayout(write_ref_layout)
        
        write_val_layout = QHBoxLayout()
        write_val_layout.addWidget(QLabel("值:"))
        self.write_value_input = QLineEdit()
        write_val_layout.addWidget(self.write_value_input)
        
        write_btn = QPushButton("写入")
        write_btn.clicked.connect(self._write_single_value)
        write_val_layout.addWidget(write_btn)
        write_layout.addLayout(write_val_layout)
        
        rw_layout.addWidget(write_group)
        rw_layout.addStretch()
        
        tabs.addTab(rw_tab, "📝 数据读写")
        
        # 控制操作标签
        control_tab = QWidget()
        control_layout = QVBoxLayout(control_tab)
        
        control_group = QGroupBox("控制操作")
        ctrl_layout = QVBoxLayout(control_group)
        
        # 控制点选择
        ctrl_ref_layout = QHBoxLayout()
        ctrl_ref_layout.addWidget(QLabel("控制点:"))
        self.control_ref_input = QLineEdit()
        self.control_ref_input.setPlaceholderText("如: SimulatedIEDPROT/XCBR1.Pos")
        ctrl_ref_layout.addWidget(self.control_ref_input)
        ctrl_layout.addLayout(ctrl_ref_layout)
        
        # 控制值
        ctrl_val_layout = QHBoxLayout()
        ctrl_val_layout.addWidget(QLabel("控制值:"))
        self.control_value_combo = QComboBox()
        self.control_value_combo.addItems(["1 (OFF/分闸)", "2 (ON/合闸)"])
        ctrl_val_layout.addWidget(self.control_value_combo)
        ctrl_layout.addLayout(ctrl_val_layout)
        
        # 控制按钮
        ctrl_btn_layout = QHBoxLayout()
        
        select_btn = QPushButton("选择 (SBO)")
        select_btn.clicked.connect(self._sbo_select)
        ctrl_btn_layout.addWidget(select_btn)
        
        operate_btn = QPushButton("执行 (Operate)")
        operate_btn.clicked.connect(self._operate)
        ctrl_btn_layout.addWidget(operate_btn)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self._cancel)
        ctrl_btn_layout.addWidget(cancel_btn)
        
        ctrl_layout.addLayout(ctrl_btn_layout)
        
        control_layout.addWidget(control_group)
        
        # 快捷控制
        quick_group = QGroupBox("快捷控制")
        quick_layout = QGridLayout(quick_group)
        
        quick_layout.addWidget(QLabel("断路器 XCBR1:"), 0, 0)
        
        xcbr_on_btn = QPushButton("合闸")
        xcbr_on_btn.clicked.connect(lambda: self._quick_control("XCBR1.Pos", 2))
        quick_layout.addWidget(xcbr_on_btn, 0, 1)
        
        xcbr_off_btn = QPushButton("分闸")
        xcbr_off_btn.clicked.connect(lambda: self._quick_control("XCBR1.Pos", 1))
        quick_layout.addWidget(xcbr_off_btn, 0, 2)
        
        control_layout.addWidget(quick_group)
        control_layout.addStretch()
        
        tabs.addTab(control_tab, "🎮 控制操作")
        
        # 订阅标签
        sub_tab = QWidget()
        sub_layout = QVBoxLayout(sub_tab)
        
        sub_group = QGroupBox("数据订阅")
        sub_grp_layout = QVBoxLayout(sub_group)
        
        # 添加订阅
        add_sub_layout = QHBoxLayout()
        add_sub_layout.addWidget(QLabel("订阅引用:"))
        self.sub_ref_input = QLineEdit()
        add_sub_layout.addWidget(self.sub_ref_input)
        
        add_sub_btn = QPushButton("添加")
        add_sub_btn.clicked.connect(self._add_subscription)
        add_sub_layout.addWidget(add_sub_btn)
        
        sub_grp_layout.addLayout(add_sub_layout)
        
        # 订阅列表
        self.subscription_list = QListWidget()
        sub_grp_layout.addWidget(self.subscription_list)
        
        # 移除订阅
        remove_sub_btn = QPushButton("移除选中")
        remove_sub_btn.clicked.connect(self._remove_subscription)
        sub_grp_layout.addWidget(remove_sub_btn)
        
        sub_layout.addWidget(sub_group)
        
        # 订阅数据显示
        sub_data_group = QGroupBox("订阅数据更新")
        sub_data_layout = QVBoxLayout(sub_data_group)
        
        self.subscription_table = QTableWidget()
        self.subscription_table.setColumnCount(4)
        self.subscription_table.setHorizontalHeaderLabels(["引用", "值", "质量", "时间"])
        self.subscription_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        sub_data_layout.addWidget(self.subscription_table)
        
        sub_layout.addWidget(sub_data_group)
        
        tabs.addTab(sub_tab, "📡 数据订阅")
        
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
    
    def _init_client(self):
        """初始化客户端"""
        client_config = self.config.get("client", {})
        
        config = ClientConfig(
            timeout_ms=client_config.get("connection", {}).get("timeout_ms", 5000),
            retry_count=client_config.get("connection", {}).get("retry_count", 3),
            retry_interval_ms=client_config.get("connection", {}).get("retry_interval_ms", 1000),
            polling_interval_ms=client_config.get("subscription", {}).get("polling_interval_ms", 1000),
            auto_reconnect=True,
        )
        
        self.client = IEC61850Client(config)
        
        # 连接回调
        self.client.on_state_change(self._on_client_state_changed)
        self.client.on_data_change(self._on_data_changed)
        self.client.on_log(lambda level, msg: self.log_message.emit(level, msg))
        
        # 获取保存的服务器列表
        self.saved_servers = client_config.get("saved_servers", [])
        
        # 更新UI
        self.timeout_input.setValue(config.timeout_ms)
        self.poll_interval_input.setValue(config.polling_interval_ms)
    
    def _setup_timers(self):
        """设置定时器"""
        # 轮询定时器
        self.polling_timer = QTimer(self)
        self.polling_timer.timeout.connect(self._poll_data)
    
    # ========================================================================
    # 连接控制
    # ========================================================================
    
    def connect(self) -> bool:
        """连接到服务器"""
        if not self.client:
            return False
        
        ip = self.ip_input.text().strip()
        port = self.port_input.value()
        name = self.name_input.text().strip()
        
        if not ip:
            QMessageBox.warning(self, "警告", "请输入IP地址")
            return False
        
        # 更新配置
        self.client.config.timeout_ms = self.timeout_input.value()
        self.client.config.auto_reconnect = self.auto_reconnect_check.isChecked()
        
        if self.client.connect(ip, port, name):
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            self._disable_conn_inputs(True)
            
            # 显示服务器信息
            self._update_server_info()
            
            # 浏览数据模型
            self._browse_data_model()
            
            return True
        
        QMessageBox.critical(self, "错误", f"连接失败: {ip}:{port}")
        return False
    
    def disconnect(self):
        """断开连接"""
        if self.client:
            self.client.disconnect()
            
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self._disable_conn_inputs(False)
            
            # 清空信息
            self.server_info_text.clear()
            self.data_tree.tree.clear()
            
            # 停止轮询
            self.polling_timer.stop()
            self.polling_check.setChecked(False)
    
    def _disable_conn_inputs(self, disabled: bool):
        """禁用/启用连接输入"""
        self.ip_input.setDisabled(disabled)
        self.port_input.setDisabled(disabled)
        self.name_input.setDisabled(disabled)
    
    def _show_connection_dialog(self):
        """显示连接对话框"""
        dialog = ConnectionDialog(self.saved_servers, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            info = dialog.get_connection_info()
            self.name_input.setText(info["name"])
            self.ip_input.setText(info["ip"])
            self.port_input.setValue(info["port"])
    
    def _update_server_info(self):
        """更新服务器信息显示"""
        if self.client and self.client.is_connected():
            info = self.client.get_server_info()
            if info:
                self.server_info_text.setText(
                    f"IED名称: {info.get('ied_name', 'N/A')}\n"
                    f"制造商: {info.get('manufacturer', 'N/A')}\n"
                    f"型号: {info.get('model', 'N/A')}\n"
                    f"版本: {info.get('revision', 'N/A')}"
                )
    
    # ========================================================================
    # 数据操作
    # ========================================================================
    
    def refresh_data(self):
        """刷新数据"""
        self._read_all_data()
    
    def _browse_data_model(self):
        """浏览数据模型"""
        if not self.client or not self.client.is_connected():
            return
        
        model = self.client.browse_data_model()
        if model:
            # 转换为data_tree需要的格式
            tree_data = {
                "name": model.get("ied_name", "IED"),
                "logical_devices": {}
            }
            
            for ld_name, ld_data in model.get("logical_devices", {}).items():
                tree_data["logical_devices"][ld_name] = {
                    "description": ld_data.get("description", ""),
                    "logical_nodes": {}
                }
                
                for ln_name, ln_data in ld_data.get("logical_nodes", {}).items():
                    tree_data["logical_devices"][ld_name]["logical_nodes"][ln_name] = {
                        "class": ln_data.get("class", ""),
                        "description": ln_data.get("description", ""),
                        "data_objects": {}
                    }
                    
                    for do_name, do_data in ln_data.get("data_objects", {}).items():
                        tree_data["logical_devices"][ld_name]["logical_nodes"][ln_name]["data_objects"][do_name] = {
                            "cdc": do_data.get("cdc", ""),
                            "description": do_data.get("description", ""),
                            "attributes": {
                                attr: {"name": attr, "type": "Unknown", "value": ""}
                                for attr in do_data.get("attributes", [])
                            }
                        }
            
            self.data_tree.load_ied(tree_data)
            self.log_message.emit("info", "数据模型加载完成")
    
    def _read_all_data(self):
        """读取所有数据"""
        if not self.client or not self.client.is_connected():
            return
        
        # 获取所有引用（简化实现）
        model = self.client.browse_data_model()
        if not model:
            return
        
        references = []
        ied_name = model.get("ied_name", "")
        
        for ld_name, ld_data in model.get("logical_devices", {}).items():
            for ln_name, ln_data in ld_data.get("logical_nodes", {}).items():
                for do_name, do_data in ln_data.get("data_objects", {}).items():
                    for attr_name in do_data.get("attributes", []):
                        ref = f"{ied_name}{ld_name}/{ln_name}.{do_name}.{attr_name}"
                        references.append(ref)
        
        if references:
            values = self.client.read_values(references)
            
            # 更新树形控件
            update_data = {}
            for ref, dv in values.items():
                update_data[ref] = {
                    "value": dv.value,
                    "quality": dv.quality,
                    "timestamp": dv.timestamp.isoformat() if dv.timestamp else None
                }
            
            self.data_tree.update_values(update_data)
            self.log_message.emit("info", f"读取了 {len(values)} 个数据点")
    
    def _read_single_value(self):
        """读取单个值"""
        ref = self.read_ref_input.text().strip()
        if not ref or not self.client:
            return
        
        dv = self.client.read_value(ref)
        if dv:
            if dv.error:
                self.read_result_text.setText(f"错误: {dv.error}")
            else:
                self.read_result_text.setText(
                    f"值: {dv.value}\n"
                    f"质量: {dv.quality}\n"
                    f"时间戳: {dv.timestamp}"
                )
                self.data_tree.update_value(ref, dv.value, dv.quality)
    
    def _write_single_value(self):
        """写入单个值"""
        ref = self.write_ref_input.text().strip()
        value_str = self.write_value_input.text().strip()
        
        if not ref or not value_str or not self.client:
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
        
        success = self.client.write_value(ref, value)
        if success:
            self.log_message.emit("info", f"写入成功: {ref} = {value}")
            QMessageBox.information(self, "成功", f"写入成功: {ref} = {value}")
        else:
            self.log_message.emit("error", f"写入失败: {ref}")
            QMessageBox.warning(self, "失败", f"写入失败: {ref}")
    
    def _on_value_changed(self, reference: str, value):
        """处理树形控件的值变化请求"""
        if self.client and self.client.is_connected():
            success = self.client.write_value(reference, value)
            if success:
                self.log_message.emit("info", f"已写入: {reference} = {value}")
            else:
                self.log_message.emit("error", f"写入失败: {reference}")
    
    def _on_item_selected(self, reference: str):
        """处理选中项变化"""
        self.read_ref_input.setText(reference)
        self.write_ref_input.setText(reference)
        self.control_ref_input.setText(reference.rsplit(".", 1)[0] if "." in reference else reference)
        self.sub_ref_input.setText(reference)
        
        # 读取并显示详情
        if self.client and self.client.is_connected():
            dv = self.client.read_value(reference)
            if dv and not dv.error:
                self.detail_text.setText(
                    f"引用: {reference}\n"
                    f"值: {dv.value}\n"
                    f"质量: {dv.quality}\n"
                    f"时间戳: {dv.timestamp}"
                )
                self.write_value_input.setText(str(dv.value) if dv.value is not None else "")
    
    def _on_item_double_clicked(self, reference: str):
        """处理双击项"""
        self._read_single_value()
    
    # ========================================================================
    # 控制操作
    # ========================================================================
    
    def _sbo_select(self):
        """SBO选择"""
        ref = self.control_ref_input.text().strip()
        if not ref or not self.client:
            return
        
        success = self.client.select_before_operate(ref)
        if success:
            self.log_message.emit("info", f"选择成功: {ref}")
        else:
            self.log_message.emit("error", f"选择失败: {ref}")
    
    def _operate(self):
        """执行控制"""
        ref = self.control_ref_input.text().strip()
        if not ref or not self.client:
            return
        
        # 获取控制值
        value_text = self.control_value_combo.currentText()
        value = 1 if "OFF" in value_text or "分闸" in value_text else 2
        
        success = self.client.operate(f"{ref}.stVal", value)
        if success:
            self.log_message.emit("info", f"控制成功: {ref} = {value}")
            QMessageBox.information(self, "成功", f"控制成功")
        else:
            self.log_message.emit("error", f"控制失败: {ref}")
            QMessageBox.warning(self, "失败", "控制失败")
    
    def _cancel(self):
        """取消控制"""
        ref = self.control_ref_input.text().strip()
        if not ref or not self.client:
            return
        
        success = self.client.cancel(ref)
        if success:
            self.log_message.emit("info", f"取消成功: {ref}")
    
    def _quick_control(self, partial_ref: str, value: int):
        """快捷控制"""
        if not self.client or not self.client.is_connected():
            QMessageBox.warning(self, "警告", "未连接到服务器")
            return
        
        # 获取IED名称
        info = self.client.get_server_info()
        if not info:
            return
        
        ied_name = info.get("ied_name", "")
        full_ref = f"{ied_name}PROT/{partial_ref}.stVal"
        
        success = self.client.operate(full_ref, value)
        if success:
            action = "合闸" if value == 2 else "分闸"
            self.log_message.emit("info", f"控制成功: {partial_ref} - {action}")
        else:
            self.log_message.emit("error", f"控制失败: {partial_ref}")
    
    # ========================================================================
    # 订阅
    # ========================================================================
    
    def _add_subscription(self):
        """添加订阅"""
        ref = self.sub_ref_input.text().strip()
        if not ref:
            return
        
        # 检查是否已存在
        for i in range(self.subscription_list.count()):
            if self.subscription_list.item(i).text() == ref:
                return
        
        self.subscription_list.addItem(ref)
        
        if self.client:
            self.client.subscribe(ref, self._on_subscription_update)
        
        self.log_message.emit("info", f"已订阅: {ref}")
    
    def _remove_subscription(self):
        """移除订阅"""
        current = self.subscription_list.currentItem()
        if current:
            ref = current.text()
            self.subscription_list.takeItem(self.subscription_list.row(current))
            
            if self.client:
                self.client.unsubscribe(ref)
            
            self.log_message.emit("info", f"已取消订阅: {ref}")
    
    def _on_subscription_update(self, reference: str, value):
        """订阅数据更新回调"""
        # 更新表格
        for row in range(self.subscription_table.rowCount()):
            if self.subscription_table.item(row, 0).text() == reference:
                self.subscription_table.setItem(row, 1, QTableWidgetItem(str(value)))
                self.subscription_table.setItem(row, 3, QTableWidgetItem(
                    datetime.now().strftime("%H:%M:%S")
                ))
                return
        
        # 添加新行
        row = self.subscription_table.rowCount()
        self.subscription_table.insertRow(row)
        self.subscription_table.setItem(row, 0, QTableWidgetItem(reference))
        self.subscription_table.setItem(row, 1, QTableWidgetItem(str(value)))
        self.subscription_table.setItem(row, 2, QTableWidgetItem("Good"))
        self.subscription_table.setItem(row, 3, QTableWidgetItem(
            datetime.now().strftime("%H:%M:%S")
        ))
    
    # ========================================================================
    # 轮询
    # ========================================================================
    
    def _toggle_polling(self, state):
        """切换轮询"""
        if state == Qt.CheckState.Checked.value:
            interval = self.poll_interval_input.value()
            self.polling_timer.start(interval)
            self.log_message.emit("info", f"启动轮询，间隔: {interval}ms")
        else:
            self.polling_timer.stop()
            self.log_message.emit("info", "停止轮询")
    
    def _poll_data(self):
        """轮询数据"""
        if not self.client or not self.client.is_connected():
            return
        
        # 读取订阅的数据
        refs = [self.subscription_list.item(i).text() 
                for i in range(self.subscription_list.count())]
        
        if refs:
            values = self.client.read_values(refs)
            for ref, dv in values.items():
                if not dv.error:
                    self._on_subscription_update(ref, dv.value)
                    self.data_tree.update_value(ref, dv.value, dv.quality)
    
    # ========================================================================
    # 回调
    # ========================================================================
    
    def _on_client_state_changed(self, state: ClientState):
        """客户端状态变化回调"""
        state_text = {
            ClientState.DISCONNECTED: ("未连接", "#6c757d"),
            ClientState.CONNECTING: ("正在连接...", "#ffc107"),
            ClientState.CONNECTED: ("已连接", "#28a745"),
            ClientState.DISCONNECTING: ("正在断开...", "#ffc107"),
            ClientState.ERROR: ("错误", "#dc3545"),
        }
        
        text, color = state_text.get(state, ("未知", "#6c757d"))
        self.status_label.setText(f"状态: {text}")
        self.status_label.setStyleSheet(f"font-weight: bold; color: {color};")
    
    def _on_data_changed(self, reference: str, value):
        """数据变化回调"""
        self.data_tree.update_value(reference, value)
