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
from PyQt6.QtGui import QCloseEvent, QActionGroup
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QMessageBox, QLabel, QFileDialog, QDialog, QComboBox,
    QSpinBox, QDialogButtonBox, QFormLayout
)
from PyQt6 import uic

import yaml
from loguru import logger

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from gui.server_panel import ServerPanel
from gui.client_panel import ClientPanel
from gui.multi_server_panel import MultiServerPanel
from gui.multi_client_panel import MultiClientPanel
from gui.log_widget import LogWidget
from backend.core_process import CoreProcessManager
from server.server_proxy import IEC61850ServerProxy, ServerConfig

# UI文件路径
UI_DIR = Path(__file__).parent / "ui"


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
        
        self._network_proxy = None

        self._init_ui()
        self._init_panels()
        self._connect_signals()
        self._init_statusbar_widgets()
        self._restore_geometry()
        self._setup_logging()
        self._init_core_process()
    
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
        
        # 模式菜单组（互斥选择）
        self.mode_action_group = QActionGroup(self)
        self.mode_action_group.setExclusive(True)
        self.mode_action_group.addAction(self.actionModeServer)
        self.mode_action_group.addAction(self.actionModeClient)
        self.actionModeServer.setChecked(True)
        
        # 设置分割器大小
        self.mainSplitter.setSizes([600, 200])
        self.mainSplitter.setStretchFactor(0, 3)
        self.mainSplitter.setStretchFactor(1, 1)
    
    def _init_panels(self):
        """初始化功能面板"""
        # 检查是否启用多实例模式
        multi_instance = self.config.get("gui", {}).get("multi_instance", True)
        
        if multi_instance:
            # 多实例服务端面板
            self.server_panel = MultiServerPanel(self.config)
            self.panelStack.addWidget(self.server_panel)
            
            # 多实例客户端面板
            self.client_panel = MultiClientPanel(self.config)
            self.panelStack.addWidget(self.client_panel)
        else:
            # 单实例服务端面板
            self.server_panel = ServerPanel(self.config)
            self.panelStack.addWidget(self.server_panel)
            
            # 单实例客户端面板
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
        self.actionModeServer.triggered.connect(lambda: self._switch_mode("server"))
        self.actionModeClient.triggered.connect(lambda: self._switch_mode("client"))
        
        # 菜单操作
        self.actionLoadConfig.triggered.connect(self._on_load_config)
        self.actionSaveConfig.triggered.connect(self._on_save_config)
        self.actionExit.triggered.connect(self.close)
        # 日志显示切换
        self.actionShowLog.triggered.connect(self._toggle_log_panel)
        self.actionClearLog.triggered.connect(self.log_widget.clear)
        # 关于
        self.actionAbout.triggered.connect(self._show_about)
        # 网卡选择
        self.actionNetworkInterface.triggered.connect(self._open_network_interface_dialog)
        
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

    def _init_core_process(self):
        """初始化并启动通信核心进程"""
        project_root = Path(__file__).parent.parent.parent
        self.core_process = CoreProcessManager(self.config, project_root, self)

        self.core_process.output.connect(lambda msg: self.log_widget.append_log("info", f"[core] {msg}"))
        self.core_process.error_output.connect(lambda msg: self.log_widget.append_log("error", f"[core] {msg}"))
        self.core_process.state_changed.connect(lambda state: self.info_label.setText(f"Core: {state}"))

        core_config = self.config.get("core", {})
        if core_config.get("auto_start", True):
            self.core_process.start()
    
    # ========================================================================
    # 事件处理
    # ========================================================================
    
    def _switch_mode(self, mode: str):
        """模式切换"""
        if mode == "server":
            self.current_mode = "server"
            self.panelStack.setCurrentIndex(0)
            self.mode_status_label.setText("模式: 服务端")
            self.actionStart.setText("▶ 启动服务")
            self.actionStop.setText("⏹ 停止服务")
            self.actionModeServer.setChecked(True)
        else:
            self.current_mode = "client"
            self.panelStack.setCurrentIndex(1)
            self.mode_status_label.setText("模式: 客户端")
            self.actionStart.setText("▶ 连接")
            self.actionStop.setText("⏹ 断开")
            self.actionModeClient.setChecked(True)
        
        self.mode_changed.emit(self.current_mode)
        logger.info(f"Switched to {self.current_mode} mode")

    def _get_network_proxy(self):
        """获取用于网络接口配置的代理"""
        if self._network_proxy:
            return self._network_proxy

        proxy = None
        if hasattr(self.server_panel, "server") and self.server_panel.server:
            proxy = self.server_panel.server
        elif hasattr(self.server_panel, "instance_manager"):
            for instance in self.server_panel.instance_manager.get_all_instances():
                proxy = instance.proxy
                break

        if not proxy:
            ipc_config = self.config.get("ipc", {})
            socket_path = ipc_config.get("socket_path", "/tmp/iec61850_simulator.sock")
            timeout_ms = ipc_config.get("request_timeout_ms", 3000)
            proxy = IEC61850ServerProxy(ServerConfig(), socket_path, timeout_ms)

        self._network_proxy = proxy
        return proxy

    def _open_network_interface_dialog(self):
        """打开网卡选择对话框"""
        proxy = self._get_network_proxy()
        if not proxy:
            QMessageBox.warning(self, "提示", "无法连接后端服务")
            return

        interfaces, current = proxy.get_network_interfaces()
        if not interfaces:
            QMessageBox.warning(self, "提示", "未获取到可用网卡")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("网卡选择")
        dialog.setMinimumWidth(420)

        layout = QFormLayout(dialog)
        combo = QComboBox(dialog)
        combo.addItem("(未选择)", None)

        for iface in interfaces:
            name = iface.get("name", "")
            is_up = iface.get("is_up", False)
            addresses = iface.get("addresses", [])
            status = "UP" if is_up else "DOWN"
            addr_str = ", ".join(addresses[:2]) if addresses else "无IP"
            display_text = f"{name} [{status}] - {addr_str}"
            combo.addItem(display_text, name)

        prefix_spin = QSpinBox(dialog)
        prefix_spin.setRange(1, 32)
        prefix_spin.setValue(24)

        if current:
            current_name = current.get("name", "")
            prefix_len = current.get("prefix_len", 24)
            for i in range(combo.count()):
                if combo.itemData(i) == current_name:
                    combo.setCurrentIndex(i)
                    break
            prefix_spin.setValue(prefix_len)

        layout.addRow("网络接口:", combo)
        layout.addRow("前缀长度:", prefix_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            interface_name = combo.currentData()
            if not interface_name:
                QMessageBox.warning(self, "提示", "请选择一个网络接口")
                return
            prefix_len = prefix_spin.value()
            if proxy.set_network_interface(interface_name, prefix_len):
                QMessageBox.information(
                    self,
                    "设置成功",
                    f"已设置网络接口: {interface_name}\n前缀长度: {prefix_len}\n\n此配置对所有服务器实例生效。"
                )
            else:
                QMessageBox.critical(self, "错误", "设置网络接口失败")
    
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

        if hasattr(self, "core_process"):
            self.core_process.stop()
        
        # 保存窗口几何位置
        self.settings.setValue("geometry", self.saveGeometry())
        
        event.accept()
    
    def set_status(self, message: str):
        """设置状态栏消息"""
        self.status_label.setText(message)
    
    def set_info(self, message: str):
        """设置右侧信息"""
        self.info_label.setText(message)
