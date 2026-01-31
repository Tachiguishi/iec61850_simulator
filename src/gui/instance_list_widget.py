"""
Instance List Widget
====================

可视化展示和管理多个Server/Client实例的组件
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QDialog, QLineEdit, QSpinBox, QFormLayout,
    QDialogButtonBox, QMenu, QFrame, QToolButton, QSizePolicy
)
from PyQt6.QtGui import QIcon, QAction, QColor


class InstanceCreateDialog(QDialog):
    """实例创建对话框"""
    
    def __init__(self, instance_type: str = "server", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.instance_type = instance_type
        
        if instance_type == "server":
            self.setWindowTitle("创建服务器实例")
        else:
            self.setWindowTitle("创建客户端实例")
        
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        
        # 实例名称
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("输入实例名称")
        form.addRow("名称:", self.name_input)
        
        if self.instance_type == "server":
            # 服务器特有配置
            self.ip_input = QLineEdit("0.0.0.0")
            form.addRow("IP地址:", self.ip_input)
            
            self.port_input = QSpinBox()
            self.port_input.setRange(1, 65535)
            self.port_input.setValue(102)
            form.addRow("端口:", self.port_input)
            
            self.max_conn_input = QSpinBox()
            self.max_conn_input.setRange(1, 100)
            self.max_conn_input.setValue(10)
            form.addRow("最大连接:", self.max_conn_input)
        else:
            # 客户端特有配置
            self.host_input = QLineEdit("127.0.0.1")
            form.addRow("服务器地址:", self.host_input)
            
            self.port_input = QSpinBox()
            self.port_input.setRange(1, 65535)
            self.port_input.setValue(102)
            form.addRow("服务器端口:", self.port_input)
        
        layout.addLayout(form)
        
        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def get_config(self) -> Dict[str, Any]:
        """获取配置"""
        config = {
            "name": self.name_input.text() or f"Instance-{datetime.now().strftime('%H%M%S')}",
        }
        
        if self.instance_type == "server":
            config.update({
                "ip_address": self.ip_input.text(),
                "port": self.port_input.value(),
                "max_connections": self.max_conn_input.value(),
            })
        else:
            config.update({
                "host": self.host_input.text(),
                "port": self.port_input.value(),
            })
        
        return config


class InstanceItemWidget(QFrame):
    """实例项显示组件"""
    
    # 信号
    start_clicked = pyqtSignal(str)  # instance_id
    stop_clicked = pyqtSignal(str)  # instance_id
    remove_clicked = pyqtSignal(str)  # instance_id
    selected = pyqtSignal(str)  # instance_id
    
    # 状态颜色映射
    STATE_COLORS = {
        "STOPPED": "#888888",
        "STARTING": "#FFA500",
        "RUNNING": "#00AA00",
        "STOPPING": "#FFA500",
        "ERROR": "#FF0000",
        "DISCONNECTED": "#888888",
        "CONNECTING": "#FFA500",
        "CONNECTED": "#00AA00",
        "DISCONNECTING": "#FFA500",
    }
    
    def __init__(
        self,
        instance_id: str,
        name: str,
        state: str,
        details: str = "",
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.instance_id = instance_id
        
        self._init_ui(name, state, details)
        self._update_style(state)
    
    def _init_ui(self, name: str, state: str, details: str):
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)
        
        # 状态指示器
        self.status_indicator = QLabel("●")
        self.status_indicator.setFixedWidth(20)
        layout.addWidget(self.status_indicator)
        
        # 信息区域
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        # 名称
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(self.name_label)
        
        # 详情
        self.details_label = QLabel(details)
        self.details_label.setStyleSheet("color: #666; font-size: 11px;")
        info_layout.addWidget(self.details_label)
        
        info_widget = QWidget()
        info_widget.setLayout(info_layout)
        info_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(info_widget)
        
        # 状态标签
        self.state_label = QLabel(state)
        self.state_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.state_label)
        
        # 操作按钮
        self.start_btn = QToolButton()
        self.start_btn.setText("▶")
        self.start_btn.setToolTip("启动")
        self.start_btn.clicked.connect(lambda: self.start_clicked.emit(self.instance_id))
        layout.addWidget(self.start_btn)
        
        self.stop_btn = QToolButton()
        self.stop_btn.setText("⏹")
        self.stop_btn.setToolTip("停止")
        self.stop_btn.clicked.connect(lambda: self.stop_clicked.emit(self.instance_id))
        layout.addWidget(self.stop_btn)
        
        self.remove_btn = QToolButton()
        self.remove_btn.setText("✕")
        self.remove_btn.setToolTip("移除")
        self.remove_btn.clicked.connect(lambda: self.remove_clicked.emit(self.instance_id))
        layout.addWidget(self.remove_btn)
    
    def _update_style(self, state: str):
        """更新样式"""
        color = self.STATE_COLORS.get(state, "#888888")
        self.status_indicator.setStyleSheet(f"color: {color};")
        self.state_label.setText(state)
        
        # 根据状态更新按钮可用性
        is_running = state in ("RUNNING", "CONNECTED")
        is_stopped = state in ("STOPPED", "DISCONNECTED", "ERROR")
        
        self.start_btn.setEnabled(is_stopped)
        self.stop_btn.setEnabled(is_running)
        self.remove_btn.setEnabled(is_stopped)
    
    def update_state(self, state: str):
        """更新状态"""
        self._update_style(state)
    
    def update_details(self, details: str):
        """更新详情"""
        self.details_label.setText(details)
    
    def mousePressEvent(self, event):
        """点击选择"""
        self.selected.emit(self.instance_id)
        super().mousePressEvent(event)


class InstanceListWidget(QWidget):
    """
    实例列表组件
    
    用于显示和管理多个Server或Client实例
    """
    
    # 信号
    instance_created = pyqtSignal(dict)  # config
    instance_removed = pyqtSignal(str)  # instance_id
    instance_started = pyqtSignal(str)  # instance_id
    instance_stopped = pyqtSignal(str)  # instance_id
    instance_selected = pyqtSignal(str)  # instance_id
    
    def __init__(
        self,
        instance_type: str = "server",
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.instance_type = instance_type
        self._items: Dict[str, InstanceItemWidget] = {}
        self._selected_id: Optional[str] = None
        
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # 标题和添加按钮
        header = QHBoxLayout()
        
        if self.instance_type == "server":
            title_text = "服务器实例"
        else:
            title_text = "客户端实例"
        
        title = QLabel(f"<b>{title_text}</b>")
        header.addWidget(title)
        
        header.addStretch()
        
        self.add_btn = QPushButton("+")
        self.add_btn.setFixedSize(24, 24)
        self.add_btn.setToolTip(f"添加{title_text}")
        self.add_btn.clicked.connect(self._on_add_clicked)
        header.addWidget(self.add_btn)
        
        layout.addLayout(header)
        
        # 实例列表容器
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch()
        
        layout.addWidget(self.list_container)
    
    def _on_add_clicked(self):
        """添加按钮点击"""
        dialog = InstanceCreateDialog(self.instance_type, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.get_config()
            self.instance_created.emit(config)
    
    def add_instance(
        self,
        instance_id: str,
        name: str,
        state: str,
        details: str = ""
    ):
        """添加实例到列表"""
        if instance_id in self._items:
            return
        
        item = InstanceItemWidget(instance_id, name, state, details)
        item.start_clicked.connect(self.instance_started.emit)
        item.stop_clicked.connect(self.instance_stopped.emit)
        item.remove_clicked.connect(self._on_remove_clicked)
        item.selected.connect(self._on_item_selected)
        
        # 插入到stretch之前
        self.list_layout.insertWidget(self.list_layout.count() - 1, item)
        self._items[instance_id] = item
    
    def remove_instance(self, instance_id: str):
        """从列表移除实例"""
        item = self._items.get(instance_id)
        if item:
            self.list_layout.removeWidget(item)
            item.deleteLater()
            del self._items[instance_id]
            
            if self._selected_id == instance_id:
                self._selected_id = None
    
    def update_instance_state(self, instance_id: str, state: str):
        """更新实例状态"""
        item = self._items.get(instance_id)
        if item:
            item.update_state(state)
    
    def update_instance_details(self, instance_id: str, details: str):
        """更新实例详情"""
        item = self._items.get(instance_id)
        if item:
            item.update_details(details)
    
    def get_selected_id(self) -> Optional[str]:
        """获取选中的实例ID"""
        return self._selected_id
    
    def select_instance(self, instance_id: str):
        """选中指定实例"""
        if instance_id in self._items:
            self._on_item_selected(instance_id)
    
    def clear(self):
        """清空列表"""
        for instance_id in list(self._items.keys()):
            self.remove_instance(instance_id)
    
    def _on_remove_clicked(self, instance_id: str):
        """移除按钮点击"""
        self.instance_removed.emit(instance_id)
    
    def _on_item_selected(self, instance_id: str):
        """实例被选中"""
        # 更新选中状态样式
        for iid, item in self._items.items():
            if iid == instance_id:
                item.setStyleSheet("background-color: #e0e8f0;")
            else:
                item.setStyleSheet("")
        
        self._selected_id = instance_id
        self.instance_selected.emit(instance_id)
