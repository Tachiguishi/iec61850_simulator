"""
Main Window
===========

IEC61850仿真器主窗口，支持服务端/客户端模式切换
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QSettings, QSize, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QFont, QCloseEvent
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QToolBar, QStatusBar, QLabel, QPushButton, QButtonGroup,
    QSplitter, QMessageBox, QApplication, QFrame, QSizePolicy
)

import yaml
from loguru import logger

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from gui.server_panel import ServerPanel
from gui.client_panel import ClientPanel
from gui.log_widget import LogWidget


class ModeButton(QPushButton):
    """模式选择按钮"""
    
    def __init__(self, text: str, icon_name: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setMinimumHeight(50)
        self.setMinimumWidth(150)
        self.setFont(QFont("Microsoft YaHei", 11))
        
        self.setStyleSheet("""
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
        """)


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
        
        self._init_ui()
        self._init_menu()
        self._init_toolbar()
        self._init_statusbar()
        self._restore_geometry()
        
        # 连接日志
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
        """初始化UI"""
        app_config = self.config.get("application", {})
        self.setWindowTitle(f"{app_config.get('name', 'IEC61850 Simulator')} v{app_config.get('version', '1.0.0')}")
        
        gui_config = self.config.get("gui", {}).get("window", {})
        self.resize(gui_config.get("width", 1400), gui_config.get("height", 900))
        
        # 中央widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # 模式选择区
        mode_frame = QFrame()
        mode_frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        mode_layout = QHBoxLayout(mode_frame)
        mode_layout.setContentsMargins(20, 15, 20, 15)
        
        mode_label = QLabel("选择模式:")
        mode_label.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        mode_layout.addWidget(mode_label)
        
        mode_layout.addSpacing(20)
        
        # 服务端模式按钮
        self.server_mode_btn = ModeButton("🖥️ 服务端模式")
        self.server_mode_btn.setChecked(True)
        self.server_mode_btn.setToolTip("仿真IED设备，作为MMS服务器运行")
        
        # 客户端模式按钮
        self.client_mode_btn = ModeButton("💻 客户端模式")
        self.client_mode_btn.setToolTip("连接到IED设备，读写数据点")
        
        # 按钮组（互斥选择）
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.server_mode_btn, 0)
        self.mode_group.addButton(self.client_mode_btn, 1)
        self.mode_group.buttonClicked.connect(self._on_mode_changed)
        
        mode_layout.addWidget(self.server_mode_btn)
        mode_layout.addWidget(self.client_mode_btn)
        mode_layout.addStretch()
        
        # 模式说明
        self.mode_desc_label = QLabel()
        self.mode_desc_label.setStyleSheet("color: #666; font-style: italic;")
        self._update_mode_description()
        mode_layout.addWidget(self.mode_desc_label)
        
        main_layout.addWidget(mode_frame)
        
        # 主分割器 (上: 功能面板, 下: 日志)
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 功能面板区域（堆叠窗口）
        self.panel_stack = QStackedWidget()
        
        # 服务端面板
        self.server_panel = ServerPanel(self.config)
        self.panel_stack.addWidget(self.server_panel)
        
        # 客户端面板
        self.client_panel = ClientPanel(self.config)
        self.panel_stack.addWidget(self.client_panel)
        
        self.main_splitter.addWidget(self.panel_stack)
        
        # 日志面板
        self.log_widget = LogWidget()
        self.main_splitter.addWidget(self.log_widget)
        
        # 设置分割比例
        self.main_splitter.setSizes([600, 200])
        self.main_splitter.setStretchFactor(0, 3)
        self.main_splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(self.main_splitter)
    
    def _init_menu(self):
        """初始化菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")
        
        load_config_action = QAction("加载配置(&L)...", self)
        load_config_action.setShortcut("Ctrl+O")
        load_config_action.triggered.connect(self._on_load_config)
        file_menu.addAction(load_config_action)
        
        save_config_action = QAction("保存配置(&S)...", self)
        save_config_action.setShortcut("Ctrl+S")
        save_config_action.triggered.connect(self._on_save_config)
        file_menu.addAction(save_config_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 视图菜单
        view_menu = menubar.addMenu("视图(&V)")
        
        self.show_log_action = QAction("显示日志面板(&L)", self)
        self.show_log_action.setCheckable(True)
        self.show_log_action.setChecked(True)
        self.show_log_action.triggered.connect(self._toggle_log_panel)
        view_menu.addAction(self.show_log_action)
        
        clear_log_action = QAction("清除日志(&C)", self)
        clear_log_action.triggered.connect(self.log_widget.clear)
        view_menu.addAction(clear_log_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")
        
        about_action = QAction("关于(&A)...", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _init_toolbar(self):
        """初始化工具栏"""
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)
        
        # 快速操作按钮
        self.start_action = QAction("▶ 启动", self)
        self.start_action.setToolTip("启动服务/连接")
        self.start_action.triggered.connect(self._on_start)
        toolbar.addAction(self.start_action)
        
        self.stop_action = QAction("⏹ 停止", self)
        self.stop_action.setToolTip("停止服务/断开连接")
        self.stop_action.setEnabled(False)
        self.stop_action.triggered.connect(self._on_stop)
        toolbar.addAction(self.stop_action)
        
        toolbar.addSeparator()
        
        refresh_action = QAction("🔄 刷新", self)
        refresh_action.setToolTip("刷新数据")
        refresh_action.triggered.connect(self._on_refresh)
        toolbar.addAction(refresh_action)
    
    def _init_statusbar(self):
        """初始化状态栏"""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        
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
        # 将loguru日志输出到GUI
        def log_handler(message):
            record = message.record
            level = record["level"].name.lower()
            text = record["message"]
            self.log_widget.append_log(level, text)
        
        logger.add(log_handler, format="{message}", level="DEBUG")
        
        # 连接面板日志
        self.server_panel.log_message.connect(
            lambda level, msg: self.log_widget.append_log(level, msg)
        )
        self.client_panel.log_message.connect(
            lambda level, msg: self.log_widget.append_log(level, msg)
        )
    
    # ========================================================================
    # 事件处理
    # ========================================================================
    
    def _on_mode_changed(self, button: QPushButton):
        """模式切换"""
        if button == self.server_mode_btn:
            self.current_mode = "server"
            self.panel_stack.setCurrentIndex(0)
            self.mode_status_label.setText("模式: 服务端")
            self.start_action.setText("▶ 启动服务")
            self.stop_action.setText("⏹ 停止服务")
        else:
            self.current_mode = "client"
            self.panel_stack.setCurrentIndex(1)
            self.mode_status_label.setText("模式: 客户端")
            self.start_action.setText("▶ 连接")
            self.stop_action.setText("⏹ 断开")
        
        self._update_mode_description()
        self.mode_changed.emit(self.current_mode)
        logger.info(f"Switched to {self.current_mode} mode")
    
    def _update_mode_description(self):
        """更新模式说明"""
        if self.current_mode == "server":
            self.mode_desc_label.setText("仿真IED设备，提供MMS服务端功能")
        else:
            self.mode_desc_label.setText("连接到IED设备，进行数据读写和控制")
    
    def _on_start(self):
        """启动/连接"""
        if self.current_mode == "server":
            if self.server_panel.start_server():
                self.start_action.setEnabled(False)
                self.stop_action.setEnabled(True)
                self.status_label.setText("服务运行中")
        else:
            if self.client_panel.connect():
                self.start_action.setEnabled(False)
                self.stop_action.setEnabled(True)
                self.status_label.setText("已连接")
    
    def _on_stop(self):
        """停止/断开"""
        if self.current_mode == "server":
            self.server_panel.stop_server()
        else:
            self.client_panel.disconnect()
        
        self.start_action.setEnabled(True)
        self.stop_action.setEnabled(False)
        self.status_label.setText("就绪")
    
    def _on_refresh(self):
        """刷新数据"""
        if self.current_mode == "server":
            self.server_panel.refresh_data()
        else:
            self.client_panel.refresh_data()
    
    def _toggle_log_panel(self, checked: bool):
        """切换日志面板显示"""
        self.log_widget.setVisible(checked)
    
    def _on_load_config(self):
        """加载配置"""
        from PyQt6.QtWidgets import QFileDialog
        
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
        from PyQt6.QtWidgets import QFileDialog
        
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
