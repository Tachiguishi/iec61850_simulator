"""
Log Widget
==========

日志显示控件
"""

from __future__ import annotations

from typing import Optional
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QComboBox, QLabel, QCheckBox
)


class LogWidget(QWidget):
    """
    日志显示控件
    
    功能：
    - 显示不同级别的日志
    - 日志过滤
    - 自动滚动
    - 导出日志
    """
    
    log_exported = pyqtSignal(str)
    
    # 日志级别颜色
    LEVEL_COLORS = {
        "debug": QColor("#808080"),
        "info": QColor("#000000"),
        "success": QColor("#008000"),
        "warning": QColor("#FFA500"),
        "error": QColor("#FF0000"),
        "critical": QColor("#8B0000"),
    }
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._auto_scroll = True
        self._filter_level = "debug"
        self._max_lines = 5000
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # 工具栏
        toolbar = QHBoxLayout()
        
        # 标题
        title = QLabel("📋 日志")
        title.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        toolbar.addWidget(title)
        
        toolbar.addStretch()
        
        # 级别过滤
        toolbar.addWidget(QLabel("级别:"))
        self.level_combo = QComboBox()
        self.level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.level_combo.setCurrentText("DEBUG")
        self.level_combo.currentTextChanged.connect(self._on_level_changed)
        toolbar.addWidget(self.level_combo)
        
        # 自动滚动
        self.auto_scroll_check = QCheckBox("自动滚动")
        self.auto_scroll_check.setChecked(True)
        self.auto_scroll_check.stateChanged.connect(
            lambda state: setattr(self, '_auto_scroll', state == Qt.CheckState.Checked.value)
        )
        toolbar.addWidget(self.auto_scroll_check)
        
        # 清除按钮
        clear_btn = QPushButton("清除")
        clear_btn.clicked.connect(self.clear)
        toolbar.addWidget(clear_btn)
        
        # 导出按钮
        export_btn = QPushButton("导出")
        export_btn.clicked.connect(self._export_log)
        toolbar.addWidget(export_btn)
        
        layout.addLayout(toolbar)
        
        # 日志文本框
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #f8f8f8;
                border: 1px solid #ddd;
            }
        """)
        layout.addWidget(self.log_text)
    
    def append_log(self, level: str, message: str, timestamp: Optional[datetime] = None):
        """
        添加日志
        
        Args:
            level: 日志级别 (debug, info, warning, error, critical)
            message: 日志消息
            timestamp: 时间戳
        """
        level = level.lower()
        
        # 级别过滤
        level_order = {"debug": 0, "info": 1, "success": 1, "warning": 2, "error": 3, "critical": 4}
        filter_order = level_order.get(self._filter_level, 0)
        msg_order = level_order.get(level, 0)
        
        if msg_order < filter_order:
            return
        
        # 格式化时间戳
        if timestamp is None:
            timestamp = datetime.now()
        time_str = timestamp.strftime("%H:%M:%S.%f")[:-3]
        
        # 格式化消息
        level_str = level.upper().ljust(8)
        formatted_msg = f"[{time_str}] [{level_str}] {message}"
        
        # 设置颜色
        color = self.LEVEL_COLORS.get(level, QColor("#000000"))
        
        # 添加到文本框
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        format = QTextCharFormat()
        format.setForeground(color)
        
        cursor.insertText(formatted_msg + "\n", format)
        
        # 限制行数
        self._limit_lines()
        
        # 自动滚动
        if self._auto_scroll:
            scrollbar = self.log_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
    
    def _limit_lines(self):
        """限制日志行数"""
        document = self.log_text.document()
        if document.lineCount() > self._max_lines:
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            
            # 删除前1000行
            for _ in range(1000):
                cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor)
            
            cursor.removeSelectedText()
    
    def clear(self):
        """清除日志"""
        self.log_text.clear()
    
    def _on_level_changed(self, level: str):
        """级别过滤变化"""
        self._filter_level = level.lower()
    
    def _export_log(self):
        """导出日志"""
        from PyQt6.QtWidgets import QFileDialog
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出日志", f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt);;All Files (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.toPlainText())
                self.log_exported.emit(file_path)
                self.append_log("info", f"日志已导出到: {file_path}")
            except Exception as e:
                self.append_log("error", f"导出失败: {e}")
    
    def get_text(self) -> str:
        """获取日志文本"""
        return self.log_text.toPlainText()
    
    def set_max_lines(self, max_lines: int):
        """设置最大行数"""
        self._max_lines = max_lines
