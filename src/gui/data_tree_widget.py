"""
Data Tree Widget
================

IEC61850数据模型树形显示控件
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Callable
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QBrush, QIcon
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QLineEdit, QPushButton, QMenu, QHeaderView, QLabel, QFrame
)


class DataTreeWidget(QWidget):
    """
    数据模型树形显示控件
    
    显示IEC61850数据模型的层次结构:
    IED -> LogicalDevice -> LogicalNode -> DataObject -> DataAttribute
    
    Signals:
        item_selected: 选中项变化 (reference)
        item_double_clicked: 双击项 (reference)
        value_changed: 值修改请求 (reference, new_value)
    """
    
    item_selected = pyqtSignal(str)
    item_double_clicked = pyqtSignal(str)
    value_changed = pyqtSignal(str, object)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._data_items: Dict[str, QTreeWidgetItem] = {}
        self._expand_level = 2
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # 工具栏
        toolbar = QHBoxLayout()
        
        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索数据点...")
        self.search_input.textChanged.connect(self._on_search)
        toolbar.addWidget(self.search_input)
        
        # 展开/折叠按钮
        expand_btn = QPushButton("全部展开")
        expand_btn.clicked.connect(self._expand_all)
        toolbar.addWidget(expand_btn)
        
        collapse_btn = QPushButton("全部折叠")
        collapse_btn.clicked.connect(self._collapse_all)
        toolbar.addWidget(collapse_btn)
        
        # 刷新按钮
        refresh_btn = QPushButton("🔄")
        refresh_btn.setToolTip("刷新")
        refresh_btn.setMaximumWidth(30)
        refresh_btn.clicked.connect(lambda: self.refresh_requested.emit() if hasattr(self, 'refresh_requested') else None)
        toolbar.addWidget(refresh_btn)
        
        layout.addLayout(toolbar)
        
        # 树形控件
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["名称", "值", "类型", "质量", "时间戳"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        
        # 设置列宽
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        
        layout.addWidget(self.tree)
        
        # 状态标签
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: #666;")
        layout.addWidget(self.status_label)
    
    def load_ied(self, ied_data: Dict):
        """
        加载IED数据模型
        
        Args:
            ied_data: IED数据字典
        """
        self.tree.clear()
        self._data_items.clear()
        
        if not ied_data:
            return
        
        # 创建IED根节点
        ied_name = ied_data.get("name", "IED")
        ied_item = QTreeWidgetItem([ied_name, "", "IED", "", ""])
        ied_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "ied", "name": ied_name})
        ied_item.setFont(0, QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        self.tree.addTopLevelItem(ied_item)
        
        # 加载逻辑设备
        for ld_name, ld_data in ied_data.get("logical_devices", {}).items():
            self._add_logical_device(ied_item, ied_name, ld_name, ld_data)
        
        # 展开到指定层级
        self._expand_to_level(self._expand_level)
        
        # 更新状态
        count = len(self._data_items)
        self.status_label.setText(f"共 {count} 个数据点")
    
    def _add_logical_device(self, parent: QTreeWidgetItem, ied_name: str, 
                            ld_name: str, ld_data: Dict):
        """添加逻辑设备节点"""
        ld_item = QTreeWidgetItem([
            ld_name,
            "",
            "LD",
            "",
            ld_data.get("description", "")
        ])
        ld_item.setData(0, Qt.ItemDataRole.UserRole, {
            "type": "ld",
            "name": ld_name,
            "reference": f"{ied_name}{ld_name}"
        })
        ld_item.setFont(0, QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
        ld_item.setForeground(0, QBrush(QColor("#0066cc")))
        parent.addChild(ld_item)
        
        # 加载逻辑节点
        for ln_name, ln_data in ld_data.get("logical_nodes", {}).items():
            self._add_logical_node(ld_item, ied_name, ld_name, ln_name, ln_data)
    
    def _add_logical_node(self, parent: QTreeWidgetItem, ied_name: str,
                          ld_name: str, ln_name: str, ln_data: Dict):
        """添加逻辑节点"""
        ln_class = ln_data.get("class", "")
        ln_item = QTreeWidgetItem([
            f"{ln_name} [{ln_class}]",
            "",
            "LN",
            "",
            ln_data.get("description", "")
        ])
        ln_ref = f"{ied_name}{ld_name}/{ln_name}"
        ln_item.setData(0, Qt.ItemDataRole.UserRole, {
            "type": "ln",
            "name": ln_name,
            "class": ln_class,
            "reference": ln_ref
        })
        ln_item.setForeground(0, QBrush(QColor("#006600")))
        parent.addChild(ln_item)
        
        # 加载数据对象
        for do_name, do_data in ln_data.get("data_objects", {}).items():
            self._add_data_object(ln_item, ln_ref, do_name, do_data)
    
    def _add_data_object(self, parent: QTreeWidgetItem, ln_ref: str,
                         do_name: str, do_data: Dict):
        """添加数据对象"""
        cdc = do_data.get("cdc", "")
        do_item = QTreeWidgetItem([
            f"{do_name} ({cdc})",
            "",
            "DO",
            "",
            do_data.get("description", "")
        ])
        do_ref = f"{ln_ref}.{do_name}"
        do_item.setData(0, Qt.ItemDataRole.UserRole, {
            "type": "do",
            "name": do_name,
            "cdc": cdc,
            "reference": do_ref
        })
        do_item.setForeground(0, QBrush(QColor("#996600")))
        parent.addChild(do_item)
        
        # 加载数据属性
        for da_name, da_data in do_data.get("attributes", {}).items():
            self._add_data_attribute(do_item, do_ref, da_name, da_data)
    
    def _add_data_attribute(self, parent: QTreeWidgetItem, do_ref: str,
                            da_name: str, da_data: Dict):
        """添加数据属性"""
        da_ref = f"{do_ref}.{da_name}"
        
        value = da_data.get("value", "")
        da_type = da_data.get("type", "")
        quality = da_data.get("quality", 0)
        timestamp = da_data.get("timestamp", "")
        
        # 格式化值显示
        value_str = self._format_value(value)
        quality_str = self._format_quality(quality)
        time_str = self._format_timestamp(timestamp)
        
        da_item = QTreeWidgetItem([
            da_name,
            value_str,
            da_type,
            quality_str,
            time_str
        ])
        da_item.setData(0, Qt.ItemDataRole.UserRole, {
            "type": "da",
            "name": da_name,
            "reference": da_ref,
            "data_type": da_type,
            "value": value
        })
        
        # 根据质量设置颜色
        if quality != 0:
            da_item.setForeground(1, QBrush(QColor("#cc0000")))
        
        parent.addChild(da_item)
        self._data_items[da_ref] = da_item
    
    def update_value(self, reference: str, value: Any, quality: int = 0, 
                     timestamp: Optional[str] = None):
        """
        更新数据值
        
        Args:
            reference: 数据引用
            value: 新值
            quality: 质量标志
            timestamp: 时间戳
        """
        item = self._data_items.get(reference)
        if item:
            item.setText(1, self._format_value(value))
            item.setText(3, self._format_quality(quality))
            if timestamp:
                item.setText(4, self._format_timestamp(timestamp))
            
            # 高亮显示更新
            item.setBackground(1, QBrush(QColor("#ffffcc")))
            
            # 1秒后取消高亮
            QTimer.singleShot(1000, lambda: item.setBackground(1, QBrush()))
            
            # 更新存储的值
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data:
                data["value"] = value
                item.setData(0, Qt.ItemDataRole.UserRole, data)
    
    def update_values(self, values: Dict[str, Dict]):
        """批量更新值"""
        for ref, value_info in values.items():
            self.update_value(
                ref,
                value_info.get("value"),
                value_info.get("quality", 0),
                value_info.get("timestamp")
            )
    
    def get_selected_reference(self) -> Optional[str]:
        """获取当前选中项的引用"""
        items = self.tree.selectedItems()
        if items:
            data = items[0].data(0, Qt.ItemDataRole.UserRole)
            if data:
                return data.get("reference")
        return None
    
    def get_selected_data(self) -> Optional[Dict]:
        """获取当前选中项的数据"""
        items = self.tree.selectedItems()
        if items:
            return items[0].data(0, Qt.ItemDataRole.UserRole)
        return None
    
    def _format_value(self, value: Any) -> str:
        """格式化值显示"""
        if value is None:
            return ""
        if isinstance(value, bool):
            return "True" if value else "False"
        if isinstance(value, float):
            return f"{value:.4f}"
        return str(value)
    
    def _format_quality(self, quality: int) -> str:
        """格式化质量标志"""
        if quality == 0:
            return "Good"
        
        flags = []
        if quality & 0x01:
            flags.append("Invalid")
        if quality & 0x02:
            flags.append("Reserved")
        if quality & 0x03:
            flags.append("Questionable")
        if quality & 0x0800:
            flags.append("Test")
        
        return ", ".join(flags) if flags else "Unknown"
    
    def _format_timestamp(self, timestamp: Any) -> str:
        """格式化时间戳"""
        if not timestamp:
            return ""
        if isinstance(timestamp, datetime):
            return timestamp.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(timestamp, str):
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                return timestamp
        return str(timestamp)
    
    def _on_search(self, text: str):
        """搜索过滤"""
        text = text.lower()
        
        def filter_item(item: QTreeWidgetItem) -> bool:
            """递归过滤"""
            # 检查当前项
            match = text in item.text(0).lower() or text in item.text(1).lower()
            
            # 检查子项
            child_match = False
            for i in range(item.childCount()):
                if filter_item(item.child(i)):
                    child_match = True
            
            # 设置可见性
            item.setHidden(not (match or child_match) and bool(text))
            
            return match or child_match
        
        for i in range(self.tree.topLevelItemCount()):
            filter_item(self.tree.topLevelItem(i))
    
    def _expand_all(self):
        """全部展开"""
        self.tree.expandAll()
    
    def _collapse_all(self):
        """全部折叠"""
        self.tree.collapseAll()
    
    def _expand_to_level(self, level: int):
        """展开到指定层级"""
        def expand_item(item: QTreeWidgetItem, current_level: int):
            if current_level < level:
                item.setExpanded(True)
                for i in range(item.childCount()):
                    expand_item(item.child(i), current_level + 1)
            else:
                item.setExpanded(False)
        
        for i in range(self.tree.topLevelItemCount()):
            expand_item(self.tree.topLevelItem(i), 0)
    
    def _on_selection_changed(self):
        """选择变化"""
        ref = self.get_selected_reference()
        if ref:
            self.item_selected.emit(ref)
    
    def _on_double_click(self, item: QTreeWidgetItem, column: int):
        """双击项"""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("type") == "da":
            self.item_double_clicked.emit(data.get("reference", ""))
    
    def _show_context_menu(self, pos):
        """显示右键菜单"""
        item = self.tree.itemAt(pos)
        if not item:
            return
        
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        menu = QMenu(self)
        
        # 复制引用
        copy_ref_action = menu.addAction("复制引用")
        copy_ref_action.triggered.connect(
            lambda: self._copy_to_clipboard(data.get("reference", ""))
        )
        
        # 复制值
        if data.get("type") == "da":
            copy_value_action = menu.addAction("复制值")
            copy_value_action.triggered.connect(
                lambda: self._copy_to_clipboard(str(data.get("value", "")))
            )
            
            menu.addSeparator()
            
            # 修改值
            edit_action = menu.addAction("修改值...")
            edit_action.triggered.connect(
                lambda: self._edit_value(data.get("reference", ""), data.get("value"))
            )
        
        menu.addSeparator()
        
        # 展开/折叠
        if item.childCount() > 0:
            if item.isExpanded():
                collapse_action = menu.addAction("折叠")
                collapse_action.triggered.connect(lambda: item.setExpanded(False))
            else:
                expand_action = menu.addAction("展开")
                expand_action.triggered.connect(lambda: item.setExpanded(True))
        
        menu.exec(self.tree.mapToGlobal(pos))
    
    def _copy_to_clipboard(self, text: str):
        """复制到剪贴板"""
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
    
    def _edit_value(self, reference: str, current_value: Any):
        """编辑值"""
        from PyQt6.QtWidgets import QInputDialog
        
        new_value, ok = QInputDialog.getText(
            self,
            "修改值",
            f"引用: {reference}\n\n请输入新值:",
            text=str(current_value) if current_value is not None else ""
        )
        
        if ok:
            # 尝试转换类型
            try:
                if new_value.lower() in ("true", "false"):
                    new_value = new_value.lower() == "true"
                elif "." in new_value:
                    new_value = float(new_value)
                else:
                    new_value = int(new_value)
            except ValueError:
                pass  # 保持字符串
            
            self.value_changed.emit(reference, new_value)
