"""
Client Panel
============

客户端模式GUI面板
使用UI文件进行界面绘制
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QListWidgetItem
)
from PyQt6 import uic

sys.path.insert(0, str(Path(__file__).parent.parent))

from gui.data_tree_widget import DataTreeWidget
from client.iec61850_client import IEC61850Client, ClientConfig, ClientState

# UI文件路径
UI_DIR = Path(__file__).parent / "ui"


class ConnectionDialog(QDialog):
    """连接对话框"""
    
    def __init__(self, saved_servers: List[Dict], parent=None):
        super().__init__(parent)
        
        self.saved_servers = saved_servers
        
        # 加载UI文件
        uic.loadUi(UI_DIR / "connection_dialog.ui", self)
        
        # 填充保存的服务器列表
        for server in saved_servers:
            item = QListWidgetItem(f"{server['name']} ({server['ip']}:{server['port']})")
            item.setData(Qt.ItemDataRole.UserRole, server)
            self.serverList.addItem(item)
        
        # 连接信号
        self.serverList.itemDoubleClicked.connect(self._on_server_selected)
    
    def _on_server_selected(self, item: QListWidgetItem):
        """选择已保存的服务器"""
        server = item.data(Qt.ItemDataRole.UserRole)
        if server:
            self.nameInput.setText(server.get("name", ""))
            self.ipInput.setText(server.get("ip", ""))
            self.portInput.setValue(server.get("port", 102))
    
    def get_connection_info(self) -> Dict:
        """获取连接信息"""
        return {
            "name": self.nameInput.text(),
            "ip": self.ipInput.text(),
            "port": self.portInput.value(),
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
        self.saved_servers: List[Dict] = []
        
        # 加载UI文件
        uic.loadUi(UI_DIR / "client_panel.ui", self)
        
        self._init_ui()
        self._init_client()
        self._connect_signals()
        self._setup_timers()
    
    def _init_ui(self):
        """初始化UI附加设置"""
        # 设置分割器大小
        self.mainSplitter.setSizes([400, 800])
        self.mainSplitter.setStretchFactor(0, 1)
        self.mainSplitter.setStretchFactor(1, 2)
        
        # 设置数据表格表头
        self.dataTable.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        
        # 设置订阅表格表头
        self.subscribeTable.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        
        # 添加DataTreeWidget到树标签页
        self.data_tree = DataTreeWidget()
        self.treeTabLayout.addWidget(self.data_tree)
    
    def _connect_signals(self):
        """连接信号"""
        # 连接按钮
        self.connectBtn.clicked.connect(self.connect)
        self.disconnectBtn.clicked.connect(self.disconnect)
        self.savedServersBtn.clicked.connect(self._show_connection_dialog)
        
        # 浏览操作
        self.browseBtn.clicked.connect(self._browse_data_model)
        self.refreshBtn.clicked.connect(self._read_all_data)
        
        # 读写操作
        self.readBtn.clicked.connect(self._read_value)
        self.writeBtn.clicked.connect(self._write_value)
        
        # 订阅操作
        self.subscribeBtn.clicked.connect(self._subscribe)
        self.unsubscribeBtn.clicked.connect(self._unsubscribe)
        
        # 数据树信号
        self.data_tree.value_changed.connect(self._on_value_changed)
        self.data_tree.item_selected.connect(self._on_item_selected)
        self.data_tree.item_double_clicked.connect(self._on_item_double_clicked)
    
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
        self.timeoutInput.setValue(config.timeout_ms)
    
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
        
        ip = self.ipInput.text().strip()
        port = self.portInput.value()
        
        if not ip:
            QMessageBox.warning(self, "警告", "请输入IP地址")
            return False
        
        # 更新配置
        self.client.config.timeout_ms = self.timeoutInput.value()
        self.client.config.auto_reconnect = self.autoReconnectCheck.isChecked()
        
        if self.client.connect(ip, port, "连接"):
            self.connectBtn.setEnabled(False)
            self.disconnectBtn.setEnabled(True)
            self.browseBtn.setEnabled(True)
            self.refreshBtn.setEnabled(True)
            self.readBtn.setEnabled(True)
            self.writeBtn.setEnabled(True)
            self.subscribeBtn.setEnabled(True)
            self.unsubscribeBtn.setEnabled(True)
            self._disable_conn_inputs(True)
            
            # 浏览数据模型
            self._browse_data_model()
            
            return True
        
        QMessageBox.critical(self, "错误", f"连接失败: {ip}:{port}")
        return False
    
    def disconnect(self):
        """断开连接"""
        if self.client:
            self.client.disconnect()
            
            self.connectBtn.setEnabled(True)
            self.disconnectBtn.setEnabled(False)
            self.browseBtn.setEnabled(False)
            self.refreshBtn.setEnabled(False)
            self.readBtn.setEnabled(False)
            self.writeBtn.setEnabled(False)
            self.subscribeBtn.setEnabled(False)
            self.unsubscribeBtn.setEnabled(False)
            self._disable_conn_inputs(False)
            
            # 清空数据
            self.data_tree.tree.clear()
            
            # 停止轮询
            self.polling_timer.stop()
    
    def _disable_conn_inputs(self, disabled: bool):
        """禁用/启用连接输入"""
        self.ipInput.setDisabled(disabled)
        self.portInput.setDisabled(disabled)
    
    def _show_connection_dialog(self):
        """显示连接对话框"""
        dialog = ConnectionDialog(self.saved_servers, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            info = dialog.get_connection_info()
            self.ipInput.setText(info["ip"])
            self.portInput.setValue(info["port"])
    
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
    
    def _read_value(self):
        """读取单个值"""
        ref = self.refInput.text().strip()
        if not ref or not self.client:
            return
        
        dv = self.client.read_value(ref)
        if dv:
            if dv.error:
                self.resultLabel.setText(f"错误: {dv.error}")
            else:
                self.resultLabel.setText(f"值: {dv.value}, 质量: {dv.quality}")
                self.data_tree.update_value(ref, dv.value, dv.quality)
    
    def _write_value(self):
        """写入值"""
        ref = self.refInput.text().strip()
        value_str = self.valueInput.text().strip()
        
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
            self.resultLabel.setText(f"写入成功: {ref} = {value}")
            self.log_message.emit("info", f"写入成功: {ref} = {value}")
        else:
            self.resultLabel.setText(f"写入失败: {ref}")
            self.log_message.emit("error", f"写入失败: {ref}")
    
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
        self.refInput.setText(reference)
    
    def _on_item_double_clicked(self, reference: str):
        """处理双击项"""
        self._read_value()
    
    # ========================================================================
    # 订阅
    # ========================================================================
    
    def _subscribe(self):
        """订阅数据"""
        report_id = self.reportIdCombo.currentText()
        if not report_id:
            return
        
        self.log_message.emit("info", f"订阅: {report_id}")
    
    def _unsubscribe(self):
        """取消订阅"""
        self.log_message.emit("info", "取消订阅")
    
    def _poll_data(self):
        """轮询数据"""
        pass
    
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
        self.statusLabel.setText(f"状态: {text}")
        self.statusLabel.setStyleSheet(f"color: {color}; font-size: 11px;")
    
    def _on_data_changed(self, reference: str, value):
        """数据变化回调"""
        self.data_tree.update_value(reference, value)
