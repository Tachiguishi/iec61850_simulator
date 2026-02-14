"""
Multi-Instance Server Panel
============================

支持多个IEC61850 Server实例的管理面板
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
from loguru import logger

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QObject, QThread
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QStackedWidget, QLabel, QMessageBox, QFileDialog, QProgressDialog,
    QDialog, QFormLayout, QLineEdit, QSpinBox, QCheckBox, QDialogButtonBox
)

sys.path.insert(0, str(Path(__file__).parent.parent))

from gui.instance_list_widget import InstanceListWidget
from gui.server_panel import ServerPanel
from core.scd_parser import SCDParser
from server.instance_manager import ServerInstanceManager, ServerInstance
from server.server_proxy import ServerConfig, ServerState


class _SCDParseWorker(QObject):
    parsed = pyqtSignal(list)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, scd_path: str):
        super().__init__()
        self._scd_path = scd_path
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            parser = SCDParser()
            ieds = parser.parse(self._scd_path)
            if not self._cancelled:
                self.parsed.emit(ieds)
        except Exception as exc:
            if not self._cancelled:
                self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class _ModelLoadWorker(QObject):
    progress = pyqtSignal(int, int)
    failed = pyqtSignal(str)
    finished = pyqtSignal(int, int)

    def __init__(self, instances: list[ServerInstance], auto_start: bool):
        super().__init__()
        self._instances = instances
        self._auto_start = auto_start
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def _load_one(self, instance: ServerInstance) -> None:
        instance.proxy.load_model(instance.id, instance.ied)
        if self._auto_start:
            instance.proxy.start(instance.id, instance.ied)

    def run(self) -> None:
        total = len(self._instances)
        if total == 0:
            self.finished.emit(0, 0)
            return

        done = 0
        try:
            with ThreadPoolExecutor(max_workers=min(8, total)) as executor:
                future_map = {
                    executor.submit(self._load_one, instance): instance.id
                    for instance in self._instances
                }

                for future in as_completed(future_map):
                    if self._cancelled:
                        for pending in future_map:
                            pending.cancel()
                        break
                    try:
                        future.result()
                    except Exception as exc:
                        self.failed.emit(str(exc))
                    done += 1
                    self.progress.emit(done, total)
        finally:
            self.finished.emit(done, total)


class _ServerConfigDialog(QDialog):
    """服务器配置编辑对话框"""

    def __init__(self, config: ServerConfig, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("服务器配置")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.ip_input = QLineEdit(config.ip_address)
        form.addRow("IP地址:", self.ip_input)

        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(config.port)
        form.addRow("端口:", self.port_input)

        self.max_conn_input = QSpinBox()
        self.max_conn_input.setRange(1, 100)
        self.max_conn_input.setValue(config.max_connections)
        form.addRow("最大连接:", self.max_conn_input)

        self.update_interval_input = QSpinBox()
        self.update_interval_input.setRange(100, 10000)
        self.update_interval_input.setSingleStep(100)
        self.update_interval_input.setValue(config.update_interval_ms)
        form.addRow("更新间隔(ms):", self.update_interval_input)

        self.random_values_check = QCheckBox("启用随机值仿真")
        self.random_values_check.setChecked(config.enable_random_values)
        form.addRow("", self.random_values_check)

        self.reporting_check = QCheckBox("启用报告功能")
        self.reporting_check.setChecked(config.enable_reporting)
        form.addRow("", self.reporting_check)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_config(self) -> dict:
        return {
            "ip_address": self.ip_input.text().strip() or "0.0.0.0",
            "port": self.port_input.value(),
            "max_connections": self.max_conn_input.value(),
            "update_interval_ms": self.update_interval_input.value(),
            "enable_random_values": self.random_values_check.isChecked(),
            "enable_reporting": self.reporting_check.isChecked(),
        }


class MultiServerPanel(QWidget):
    """
    多实例服务器面板
    
    功能：
    - 管理多个Server实例
    - 每个实例独立配置
    - 实例间独立的数据模型
    - 统一的实例列表视图
    """
    
    log_message = pyqtSignal(str, str)  # level, message
    _instance_added_signal = pyqtSignal(object)
    _instance_removed_signal = pyqtSignal(str)
    _instance_state_signal = pyqtSignal(str, object)
    _instance_log_signal = pyqtSignal(str, str, str)
    
    def __init__(self, config: Dict, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.config = config
        self._current_instance_id: Optional[str] = None
        
        # 初始化实例管理器
        ipc_config = config.get("ipc", {})
        socket_path = ipc_config.get("socket_path", "/tmp/iec61850_simulator.sock")
        timeout_ms = ipc_config.get("request_timeout_ms", 3000)
        
        self.instance_manager = ServerInstanceManager(socket_path, timeout_ms)
        self._setup_manager_callbacks()
        
        self._init_ui()
        self._connect_signals()
    
    def _setup_manager_callbacks(self):
        """设置实例管理器回调"""
        self._instance_added_signal.connect(self._on_instance_added)
        self._instance_removed_signal.connect(self._on_instance_removed)
        self._instance_state_signal.connect(self._on_instance_state_change)
        self._instance_log_signal.connect(self._on_instance_log)

        self.instance_manager.on_instance_added(
            lambda instance: self._instance_added_signal.emit(instance)
        )
        self.instance_manager.on_instance_removed(
            lambda instance_id: self._instance_removed_signal.emit(instance_id)
        )
        self.instance_manager.on_instance_state_change(
            lambda instance_id, state: self._instance_state_signal.emit(instance_id, state)
        )
        self.instance_manager.on_log(
            lambda instance_id, level, message: self._instance_log_signal.emit(instance_id, level, message)
        )
    
    def _init_ui(self):
        """初始化UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 左侧：实例列表
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(4, 4, 4, 4)
        
        # 实例列表
        self.instance_list = InstanceListWidget("server")
        left_layout.addWidget(self.instance_list)
        
        # 统计信息
        self.stats_label = QLabel("实例: 0 | 运行中: 0")
        self.stats_label.setStyleSheet("color: #666; font-size: 11px;")
        left_layout.addWidget(self.stats_label)
        
        left_panel.setMinimumWidth(250)
        left_panel.setMaximumWidth(360)
        
        # 右侧：实例详情（使用StackedWidget切换不同实例的配置界面）
        self.detail_stack = QStackedWidget()
        
        # 空白占位页面
        empty_page = QWidget()
        empty_layout = QVBoxLayout(empty_page)
        empty_label = QLabel("请选择或创建一个服务器实例")
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_label.setStyleSheet("color: #888; font-size: 14px;")
        empty_layout.addWidget(empty_label)
        self.detail_stack.addWidget(empty_page)

        # 共享详情面板（仅创建一个）
        self.shared_panel = ServerPanel(self.config, self)
        self.shared_panel.model_loaded.connect(self._on_model_loaded)
        self.shared_panel.log_message.connect(
            lambda level, msg: self.log_message.emit(level, msg)
        )
        self.detail_stack.addWidget(self.shared_panel)
        
        # 分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.detail_stack)
        splitter.setSizes([360, 720])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        
        layout.addWidget(splitter)
        
        # 默认显示空白页
        self.detail_stack.setCurrentIndex(0)
    
    def _connect_signals(self):
        """连接信号"""
        self.instance_list.instance_created.connect(self._on_create_instance)
        self.instance_list.instance_removed.connect(self._on_remove_instance)
        self.instance_list.instance_started.connect(self._on_start_instance)
        self.instance_list.instance_stopped.connect(self._on_stop_instance)
        self.instance_list.instance_config_requested.connect(self._on_config_instance)
        self.instance_list.instance_selected.connect(self._on_select_instance)
    
    # =========================================================================
    # 实例操作
    # =========================================================================
    
    def _on_create_instance(self, config: Dict):
        """创建实例"""
        try:
            scl_file_path = config.get("scl_file_path")
            if scl_file_path:
                self._import_from_scd_file(scl_file_path)
                return
            
        except ValueError as e:
            QMessageBox.warning(self, "创建失败", str(e))
    
    def _on_remove_instance(self, instance_id: str):
        """移除实例"""
        instance = self.instance_manager.get_instance(instance_id)
        if not instance:
            return
        
        reply = QMessageBox.question(
            self, "确认移除",
            f"确定要移除实例 '{instance.name}' 吗?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.instance_manager.remove_instance(instance_id)
    
    def _on_start_instance(self, instance_id: str):
        """启动实例"""
        self.instance_manager.start_instance(instance_id)
    
    def _on_stop_instance(self, instance_id: str):
        """停止实例"""
        self.instance_manager.stop_instance(instance_id)

    def _on_config_instance(self, instance_id: str):
        """配置实例"""
        instance = self.instance_manager.get_instance(instance_id)
        if not instance:
            return

        dialog = _ServerConfigDialog(instance.config, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_config = dialog.get_config()
        instance.config.ip_address = new_config["ip_address"]
        instance.config.port = new_config["port"]
        instance.config.max_connections = new_config["max_connections"]
        instance.config.update_interval_ms = new_config["update_interval_ms"]
        instance.config.enable_random_values = new_config["enable_random_values"]
        instance.config.enable_reporting = new_config["enable_reporting"]

        instance.proxy.config.ip_address = new_config["ip_address"]
        instance.proxy.config.port = new_config["port"]
        instance.proxy.config.max_connections = new_config["max_connections"]
        instance.proxy.config.update_interval_ms = new_config["update_interval_ms"]
        instance.proxy.config.enable_random_values = new_config["enable_random_values"]
        instance.proxy.config.enable_reporting = new_config["enable_reporting"]

        self.instance_list.update_instance_details(
            instance_id,
            f"{instance.config.ip_address}:{instance.config.port}"
        )

        if instance.state == ServerState.RUNNING:
            self.log_message.emit("warning", f"实例 {instance.name} 正在运行，配置修改将在下次启动时完全生效")
        else:
            self.log_message.emit("info", f"实例 {instance.name} 配置已更新")
    
    def _on_select_instance(self, instance_id: str):
        """选择实例"""
        self._current_instance_id = instance_id

        instance = self.instance_manager.get_instance(instance_id)
        if not instance:
            self.detail_stack.setCurrentIndex(0)
            return

        self.shared_panel.bind_instance(
            server_proxy=instance.proxy,
            instance_id=instance.id,
            ied=instance.ied,
            state=instance.state,
        )
        self.detail_stack.setCurrentWidget(self.shared_panel)
    
    # =========================================================================
    # 实例管理器回调
    # =========================================================================
    
    def _on_instance_added(self, instance: ServerInstance):
        """实例添加回调"""
        details = f"{instance.config.ip_address}:{instance.config.port}"
        self.instance_list.add_instance(
            instance.id,
            instance.name,
            instance.state.name,
            details
        )
        self._update_stats()
        if self._current_instance_id is None:
            self.instance_list.select_instance(instance.id)
    
    def _on_instance_removed(self, instance_id: str):
        """实例移除回调"""
        self.instance_list.remove_instance(instance_id)

        # 如果移除的是当前选中的，切换到空白页
        if self._current_instance_id == instance_id:
            self._current_instance_id = None
            self.detail_stack.setCurrentIndex(0)
        
        self._update_stats()
    
    def _on_instance_state_change(self, instance_id: str, state: ServerState):
        """实例状态变化回调"""
        self.instance_list.update_instance_state(instance_id, state.name)
        self._update_stats()
    
    def _on_instance_log(self, instance_id: str, level: str, message: str):
        """实例日志回调"""
        instance = self.instance_manager.get_instance(instance_id)
        name = instance.name if instance else instance_id
        self.log_message.emit(level, f"[{name}] {message}")
    
    # =========================================================================
    # 面板管理
    # =========================================================================
    
    def _on_model_loaded(self, ied) -> None:
        """同步面板加载的IED到实例缓存"""
        if not self._current_instance_id:
            return
        instance = self.instance_manager.get_instance(self._current_instance_id)
        if instance:
            instance.ied = ied
    
    def _update_stats(self):
        """更新统计信息"""
        total = self.instance_manager.get_instance_count()
        running = self.instance_manager.get_running_count()
        self.stats_label.setText(f"实例: {total} | 运行中: {running}")
    
    # =========================================================================
    # 公共方法
    # =========================================================================
    
    def start_all(self):
        """启动所有实例"""
        for instance in self.instance_manager.get_all_instances():
            if instance.state == ServerState.STOPPED:
                self.instance_manager.start_instance(instance.id)
    
    def stop_all(self):
        """停止所有实例"""
        self.instance_manager.stop_all_instances()
    
    def get_current_instance(self) -> Optional[ServerInstance]:
        """获取当前选中的实例"""
        if self._current_instance_id:
            return self.instance_manager.get_instance(self._current_instance_id)
        return None
    
    def get_all_instances(self):
        """获取所有实例"""
        return self.instance_manager.get_all_instances()
    
    # =========================================================================
    # 兼容性方法（与单实例面板接口一致）
    # =========================================================================
    
    def start_server(self) -> bool:
        """启动当前选中的服务器实例（兼容单实例接口）"""
        instance = self.get_current_instance()
        if instance:
            return self.instance_manager.start_instance(instance.id)
        return False
    
    def stop_server(self):
        """停止当前选中的服务器实例（兼容单实例接口）"""
        instance = self.get_current_instance()
        if instance:
            self.instance_manager.stop_instance(instance.id)
    
    def refresh_data(self):
        """刷新当前选中实例的数据（兼容单实例接口）"""
        if self._current_instance_id and hasattr(self.shared_panel, 'refresh_data'):
            self.shared_panel.refresh_data()
    
    def save_instances(self, file_path: str) -> bool:
        """保存所有实例配置到文件"""
        return self.instance_manager.save_to_file(file_path)
    
    def load_instances(self, file_path: str, auto_start: bool = False) -> int:
        """从文件加载实例配置"""
        count = self.instance_manager.load_from_file(file_path, auto_start)
        if self._current_instance_id is None:
            instances = self.instance_manager.get_all_instances()
            if instances:
                self.instance_list.select_instance(instances[0].id)
        return count


    def _import_from_scd_file(self, file_path: str, base_port: int = 102, auto_start: bool = False) -> int:
        """从SCD/CID文件导入IED并创建实例"""

        logger.info(f"Importing IEDs from SCD file: {file_path}")

        self._parse_progress = QProgressDialog("正在解析SCD文件...", "", 0, 0, self)
        self._parse_progress.setCancelButton(None)
        self._parse_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._parse_progress.show()

        self._parse_thread = QThread(self)
        self._parse_worker = _SCDParseWorker(file_path)
        self._parse_worker.moveToThread(self._parse_thread)
        self._parse_thread.started.connect(self._parse_worker.run)
        self._parse_worker.parsed.connect(
            lambda ieds: self._on_scd_parsed(ieds, file_path, base_port, auto_start)
        )
        self._parse_worker.failed.connect(self._on_scd_parse_failed)
        self._parse_worker.finished.connect(self._parse_thread.quit)
        self._parse_worker.finished.connect(self._parse_worker.deleteLater)
        self._parse_thread.finished.connect(self._parse_thread.deleteLater)
        self._parse_thread.start()

        return 0

    def _on_scd_parse_failed(self, message: str) -> None:
        if hasattr(self, "_parse_progress") and self._parse_progress:
            self._parse_progress.close()
            self._parse_progress = None
        self._parse_worker = None
        self._parse_thread = None
        QMessageBox.warning(self, "导入失败", f"解析SCD文件失败: {message}")

    def _on_scd_parsed(self, ieds: list, file_path: str, base_port: int, auto_start: bool) -> None:
        if hasattr(self, "_parse_progress") and self._parse_progress:
            self._parse_progress.close()
            self._parse_progress = None
        self._parse_worker = None
        self._parse_thread = None

        if not ieds:
            QMessageBox.warning(self, "导入失败", "未能从SCD文件导入任何IED")
            return

        instances: list[ServerInstance] = []

        for ied in ieds:
            try:
                listen_ip = ied.get_listen_ip()
                current_port = base_port + self.instance_manager.count_server_in_use(listen_ip)

                config = ServerConfig(
                    ip_address=listen_ip,
                    port=current_port,
                )

                instance = self.instance_manager.create_instance(
                    name=ied.name,
                    config=config,
                )

                instance.ied = ied
                instance.scl_file_path = str(file_path)
                instances.append(instance)
            except Exception as exc:
                self.log_message.emit("error", f"导入IED失败: {exc}")
                continue

        self._start_model_load(instances, auto_start)

    def _start_model_load(self, instances: list[ServerInstance], auto_start: bool) -> None:
        if not instances:
            QMessageBox.warning(self, "导入失败", "未能创建任何IED实例")
            return

        logger.info(f"Starting to load models for {len(instances)} IED instances...")
        self._load_progress = QProgressDialog("正在加载IED模型...", "取消", 0, len(instances), self)
        self._load_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._load_progress.setValue(0)

        self._load_thread = QThread(self)
        self._load_worker = _ModelLoadWorker(instances, auto_start)
        self._load_worker.moveToThread(self._load_thread)
        self._load_thread.started.connect(self._load_worker.run)
        self._load_worker.progress.connect(self._on_load_progress)
        self._load_worker.failed.connect(lambda msg: self.log_message.emit("error", f"加载IED失败: {msg}"))
        self._load_worker.finished.connect(self._on_load_finished)
        self._load_worker.finished.connect(self._load_thread.quit)
        self._load_worker.finished.connect(self._load_worker.deleteLater)
        self._load_thread.finished.connect(self._load_thread.deleteLater)
        self._load_progress.canceled.connect(self._load_worker.cancel)
        self._load_thread.start()

    def _on_load_progress(self, done: int, total: int) -> None:
        if hasattr(self, "_load_progress") and self._load_progress:
            self._load_progress.setMaximum(total)
            self._load_progress.setValue(done)

    def _on_load_finished(self, done: int, total: int) -> None:
        if hasattr(self, "_load_progress") and self._load_progress:
            self._load_progress.close()
            self._load_progress = None
        self._load_worker = None
        self._load_thread = None

        if done > 0:
            QMessageBox.information(
                self,
                "导入成功",
                f"成功从SCD文件导入 {done} 个IED实例"
            )
        else:
            QMessageBox.warning(
                self,
                "导入失败",
                "未能从SCD文件导入任何IED"
            )
