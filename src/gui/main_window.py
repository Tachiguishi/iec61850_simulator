"""
Main Window
===========

IEC61850仿真器主窗口，支持服务端/客户端模式切换
使用UI文件进行界面绘制
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QButtonGroup,
    QMessageBox, QLabel, QFileDialog
)
from PyQt6 import uic

import yaml
from loguru import logger

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from gui.server_panel import ServerPanel
from gui.client_panel import ClientPanel
from gui.log_widget import LogWidget

# UI文件路径
UI_DIR = Path(__file__).parent / "ui"


# 模式按钮样式
MODE_BUTTON_STYLE = """
    QPushButton {
        background-color: #f0f0f0;
        border: 2px solid #c0c0c0;
        border-radius: 8px;
        padding: 10px 20px;
        color: #333;
    }
    QPushButton:hover {
        background-color: #e0e0e0;
        border-color: #a0a0a0;
    }
    QPushButton:checked {
        background-color: #0078d4;
        border-color: #0066b8;
        color: white;
    }
    QPushButton:checked:hover {
        background-color: #006cc1;
    }
"""


class MainWindow(QMainWindow):
    """
    IEC61850仿真器主窗口
    
    功能：
    - 服务端/客户端模式切换
    - 工具栏和状态栏
    - 日志面板
    - 配置管理
    """
    
    mode_changed = pyqtSignal(str)  # "server" 或 "client"
    
    def __init__(self):
        super().__init__()
        
        self.settings = QSettings("IEC61850Simulator", "MainWindow")
        self.config = self._load_config()
        self.current_mode = "server"
        
        # 加载UI文件
        uic.loadUi(UI_DIR / "main_window.ui", self)
        
        self._init_ui()
        self._init_panels()
        self._connect_signals()
        self._init_statusbar_widgets()
        self._restore_geometry()
        self._setup_logging()
    
    def _load_config(self) -> dict:
        """加载配置文件"""
        config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
        try:
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
        
        return {
            "application": {"name": "IEC61850 Simulator", "version": "1.0.0"},
            "gui": {"window": {"width": 1400, "height": 900}}
        }
    
    def _init_ui(self):
        """初始化UI附加设置"""
        app_config = self.config.get("application", {})
        self.setWindowTitle(f"{app_config.get('name', 'IEC61850 Simulator')} v{app_config.get('version', '1.0.0')}")
        
        gui_config = self.config.get("gui", {}).get("window", {})
        self.resize(gui_config.get("width", 1400), gui_config.get("height", 900))
        
        # 设置模式按钮样式
        self.serverModeBtn.setStyleSheet(MODE_BUTTON_STYLE)
        self.clientModeBtn.setStyleSheet(MODE_BUTTON_STYLE)
        
        # 按钮组（互斥选择）
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.serverModeBtn, 0)
        self.mode_group.addButton(self.clientModeBtn, 1)
        
        # 设置分割器大小
        self.mainSplitter.setSizes([600, 200])
        self.mainSplitter.setStretchFactor(0, 3)
        self.mainSplitter.setStretchFactor(1, 1)
    
    def _init_panels(self):
        """初始化功能面板"""
        # 服务端面板
        self.server_panel = ServerPanel(self.config)
        self.panelStack.addWidget(self.server_panel)
        
        # 客户端面板
        self.client_panel = ClientPanel(self.config)
        self.panelStack.addWidget(self.client_panel)
        
        # 日志面板
        self.log_widget = LogWidget()
        layout = QVBoxLayout(self.logWidgetContainer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.log_widget)
        
        # 连接面板日志
        self.server_panel.log_message.connect(
            lambda level, msg: self.log_widget.append_log(level, msg)
        )
        self.client_panel.log_message.connect(
            lambda level, msg: self.log_widget.append_log(level, msg)
        )
    
    def _connect_signals(self):
        """连接信号"""
        # 模式切换
        self.mode_group.buttonClicked.connect(self._on_mode_changed)
        
        # 菜单操作
        self.actionLoadConfig.triggered.connect(self._on_load_config)
        self.actionSaveConfig.triggered.connect(self._on_save_config)
        self.actionExit.triggered.connect(self.close)
        self.actionShowLog.triggered.connect(self._toggle_log_panel)
        self.actionClearLog.triggered.connect(self.log_widget.clear)
        self.actionAbout.triggered.connect(self._show_about)
        
        # 工具栏操作
        self.actionStart.triggered.connect(self._on_start)
        self.actionStop.triggered.connect(self._on_stop)
        self.actionRefresh.triggered.connect(self._on_refresh)
    
    def _init_statusbar_widgets(self):
        """初始化状态栏控件"""
        # 模式标签
        self.mode_status_label = QLabel("模式: 服务端")
        self.statusbar.addWidget(self.mode_status_label)
        
        # 分隔符
        separator = QLabel(" | ")
        self.statusbar.addWidget(separator)
        
        # 状态标签
        self.status_label = QLabel("就绪")
        self.statusbar.addWidget(self.status_label)
        
        # 右侧信息
        self.info_label = QLabel()
        self.statusbar.addPermanentWidget(self.info_label)
    
    def _restore_geometry(self):
        """恢复窗口几何位置"""
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
    
    def _setup_logging(self):
        """设置日志"""
        def log_handler(message):
            record = message.record
            level = record["level"].name.lower()
            text = record["message"]
            self.log_widget.append_log(level, text)
        
        logger.add(log_handler, format="{message}", level="DEBUG")
    
    # ========================================================================
    # 事件处理
    # ========================================================================
    
    def _on_mode_changed(self, button):
        """模式切换"""
        if button == self.serverModeBtn:
            self.current_mode = "server"
            self.panelStack.setCurrentIndex(0)
            self.mode_status_label.setText("模式: 服务端")
            self.actionStart.setText("▶ 启动服务")
            self.actionStop.setText("⏹ 停止服务")
            self.modeDescLabel.setText("仿真IED设备，提供MMS服务端功能")
        else:
            self.current_mode = "client"
            self.panelStack.setCurrentIndex(1)
            self.mode_status_label.setText("模式: 客户端")
            self.actionStart.setText("▶ 连接")
            self.actionStop.setText("⏹ 断开")
            self.modeDescLabel.setText("连接到IED设备，进行数据读写和控制")
        
        self.mode_changed.emit(self.current_mode)
        logger.info(f"Switched to {self.current_mode} mode")
    
    def _on_start(self):
        """启动/连接"""
        if self.current_mode == "server":
            if self.server_panel.start_server():
                self.actionStart.setEnabled(False)
                self.actionStop.setEnabled(True)
                self.status_label.setText("服务运行中")
        else:
            if self.client_panel.connect():
                self.actionStart.setEnabled(False)
                self.actionStop.setEnabled(True)
                self.status_label.setText("已连接")
    
    def _on_stop(self):
        """停止/断开"""
        if self.current_mode == "server":
            self.server_panel.stop_server()
        else:
            self.client_panel.disconnect()
        
        self.actionStart.setEnabled(True)
        self.actionStop.setEnabled(False)
        self.status_label.setText("就绪")
    
    def _on_refresh(self):
        """刷新数据"""
        if self.current_mode == "server":
            self.server_panel.refresh_data()
        else:
            self.client_panel.refresh_data()
    
    def _toggle_log_panel(self, checked: bool):
        """切换日志面板显示"""
        self.logWidgetContainer.setVisible(checked)
    
    def _on_load_config(self):
        """加载配置"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "加载配置文件", "", "YAML Files (*.yaml *.yml);;All Files (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.config = yaml.safe_load(f)
                logger.info(f"Loaded config from {file_path}")
                QMessageBox.information(self, "成功", "配置加载成功！")
            except Exception as e:
                logger.error(f"Failed to load config: {e}")
                QMessageBox.critical(self, "错误", f"加载配置失败: {e}")
    
    def _on_save_config(self):
        """保存配置"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存配置文件", "", "YAML Files (*.yaml *.yml);;All Files (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)
                logger.info(f"Saved config to {file_path}")
                QMessageBox.information(self, "成功", "配置保存成功！")
            except Exception as e:
                logger.error(f"Failed to save config: {e}")
                QMessageBox.critical(self, "错误", f"保存配置失败: {e}")
    
    def _show_about(self):
        """显示关于对话框"""
        app_config = self.config.get("application", {})
        QMessageBox.about(
            self,
            "关于",
            f"""<h2>{app_config.get('name', 'IEC61850 Simulator')}</h2>
            <p>版本: {app_config.get('version', '1.0.0')}</p>
            <p>基于PyQt6的IEC61850协议仿真器</p>
            <p>支持服务端（IED仿真）和客户端（SCADA）两种模式</p>
            <hr>
            <p>功能特性:</p>
            <ul>
                <li>IEC61850数据模型管理</li>
                <li>MMS协议仿真</li>
                <li>实时数据监控</li>
                <li>控制操作支持</li>
            </ul>
            """
        )
    
    def closeEvent(self, event: QCloseEvent):
        """关闭事件"""
        # 停止服务/断开连接
        if self.current_mode == "server":
            self.server_panel.stop_server()
        else:
            self.client_panel.disconnect()
        
        # 保存窗口几何位置
        self.settings.setValue("geometry", self.saveGeometry())
        
        event.accept()
    
    def set_status(self, message: str):
        """设置状态栏消息"""
        self.status_label.setText(message)
    
    def set_info(self, message: str):
        """设置右侧信息"""
        self.info_label.setText(message)
