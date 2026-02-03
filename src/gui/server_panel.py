"""
Server Panel
============

服务端模式GUI面板
使用UI文件进行界面绘制
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidgetItem, QHeaderView,
    QMessageBox, QFileDialog
)
from PyQt6 import uic

sys.path.insert(0, str(Path(__file__).parent.parent))

from gui.data_tree_widget import DataTreeWidget
from server.server_proxy import IEC61850ServerProxy, ServerConfig, ServerState
from core.data_model_manager import DataModelManager

# UI文件路径
UI_DIR = Path(__file__).parent / "ui"


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
        self.server: Optional[IEC61850ServerProxy] = None
        self.data_model_manager = DataModelManager()
        
        # 加载UI文件
        uic.loadUi(UI_DIR / "server_panel.ui", self)
        
        self._init_ui()
        self._init_server()
        self._connect_signals()
        self._setup_timers()
    
    def _init_ui(self):
        """初始化UI附加设置"""
        # 设置分割器大小
        self.mainSplitter.setSizes([400, 800])
        self.mainSplitter.setStretchFactor(0, 1)
        self.mainSplitter.setStretchFactor(1, 2)
        
        # 设置连接表格表头
        self.connectionTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        # 设置数据集分割器大小（左侧面板 : 右侧FCDA面板）
        self.datasetSplitter.setSizes([400, 800])
        
        # 设置左侧垂直分割器大小（数据集列表 : 控制块信息）
        self.leftVerticalSplitter.setSizes([300, 200])
        
        # 设置FCDA表格表头
        self.fcdaTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        # 设置控制块表格表头（属性列自适应，值列伸展）
        self.controlBlockTable.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.controlBlockTable.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        
        # 添加DataTreeWidget到树标签页
        self.data_tree = DataTreeWidget()
        self.treeTabLayout.addWidget(self.data_tree)
    
    def _connect_signals(self):
        """连接信号"""
        # 控制按钮
        self.startBtn.clicked.connect(self.start_server)
        self.stopBtn.clicked.connect(self.stop_server)
        
        # 模型操作
        self.loadModelBtn.clicked.connect(self._load_data_model)
        self.reloadModelBtn.clicked.connect(self._create_default_model)
        
        # 仿真脚本
        self.runScriptBtn.clicked.connect(self._run_simulation_script)
        self.stopScriptBtn.clicked.connect(self._stop_simulation_script)
        
        # 数据树信号
        self.data_tree.value_changed.connect(self._on_value_changed)
        self.data_tree.item_selected.connect(self._on_item_selected)
        
        # 数据集信号
        self.datasetList.currentItemChanged.connect(self._on_dataset_selected)
    
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
        
        ipc_config = self.config.get("ipc", {})
        socket_path = ipc_config.get("socket_path", "/tmp/iec61850_simulator.sock")
        timeout_ms = ipc_config.get("request_timeout_ms", 3000)

        self.server = IEC61850ServerProxy(config, socket_path, timeout_ms)
        
        # 连接回调
        self.server.on_state_change(self._on_server_state_changed)
        self.server.on_connection_change(self._on_connection_changed)
        self.server.on_data_change(self._on_data_changed)
        self.server.on_log(lambda level, msg: self.log_message.emit(level, msg))
        
        # 更新UI
        self.ipInput.setText(config.ip_address)
        self.portInput.setValue(config.port)
        self.maxConnInput.setValue(config.max_connections)
        self.updateIntervalInput.setValue(config.update_interval_ms)
        self.randomValuesCheck.setChecked(config.enable_random_values)
        self.reportingCheck.setChecked(config.enable_reporting)
        
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
        self.server.config.ip_address = self.ipInput.text()
        self.server.config.port = self.portInput.value()
        self.server.config.max_connections = self.maxConnInput.value()
        self.server.config.update_interval_ms = self.updateIntervalInput.value()
        self.server.config.enable_random_values = self.randomValuesCheck.isChecked()
        self.server.config.enable_reporting = self.reportingCheck.isChecked()
        
        # 确保有IED
        if not self.server.ied:
            self._create_default_model()
        
        if self.server.start():
            self.startBtn.setEnabled(False)
            self.stopBtn.setEnabled(True)
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
            
            self.startBtn.setEnabled(True)
            self.stopBtn.setEnabled(False)
            self._disable_config_inputs(False)
            
            # 停止定时器
            self.refresh_timer.stop()
            self.client_timer.stop()
    
    def _disable_config_inputs(self, disabled: bool):
        """禁用/启用配置输入"""
        self.ipInput.setDisabled(disabled)
        self.portInput.setDisabled(disabled)
        self.maxConnInput.setDisabled(disabled)
    
    # ========================================================================
    # 数据模型管理
    # ========================================================================
    
    def _create_default_model(self):
        """创建默认数据模型"""
        name = "SimulatedIED"
        ied = self.data_model_manager.create_default_ied(name)
        
        if self.server:
            self.server.load_model(ied)
        
        self._update_data_tree()
        self.modelInfoLabel.setText(f"已加载: {name}")
        self.log_message.emit("info", f"已创建默认IED: {name}")
    
    def _load_data_model(self):
        """加载数据模型"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "加载数据模型", "",
            "SCL Files (*.scd *.cid *.icd);;All Files (*)"
        )
        
        if file_path:
            ieds = self.data_model_manager.load_from_scd(file_path)
            if ieds:
                try:
                    if self.server:
                        self.server.load_model(ieds[1])
                    self.modelInfoLabel.setText(f"已加载: {ieds[1].name}")
                    self._update_data_tree()
                    self.log_message.emit("info", f"已加载IED: {ieds[1].name}")
                except Exception as e:
                    QMessageBox.critical(self, "错误", f"加载数据模型失败: {e}")
            else:
                QMessageBox.critical(self, "错误", "解析数据模型失败")
    
    def _update_data_tree(self):
        self._update_dataset_list()
        """更新数据树"""
        if self.server and self.server.ied:
            self.data_tree.load_ied(self.server.ied.to_dict())
    
    # ========================================================================
    # 仿真
    # ========================================================================
    
    def _run_simulation_script(self):
        """运行仿真脚本"""
        script = self.simScriptEdit.toPlainText()
        if not script.strip():
            return
        
        self.log_message.emit("info", "仿真脚本功能待实现")
    
    def _stop_simulation_script(self):
        """停止仿真脚本"""
        self.log_message.emit("info", "停止仿真脚本")
    
    # ========================================================================
    # 数据操作
    # ========================================================================
    
    def _on_value_changed(self, reference: str, value):
        """处理树形控件的值变化"""
        if self.server:
            self.server.set_data_value(reference, value)
    
    def _on_item_selected(self, reference: str):
        """处理选中项变化"""
        pass
    
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
        
        references = self.server.ied.get_all_references()
        values = self.server.get_values(references)
        if values:
            self.data_tree.update_values(values)
    
    def _refresh_client_list(self):
        """刷新客户端列表"""
        if not self.server:
            return
        
        clients = self.server.get_connected_clients()
        
        self.connectionTable.setRowCount(len(clients))
        for i, client in enumerate(clients):
            self.connectionTable.setItem(i, 0, QTableWidgetItem(client["id"]))
            self.connectionTable.setItem(i, 1, QTableWidgetItem(
                client["connected_at"].split("T")[1][:8] if "T" in client["connected_at"] else ""
            ))
            self.connectionTable.setItem(i, 2, QTableWidgetItem("已连接"))
    
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
        self.statusLabel.setText(f"状态: {text}")
        self.statusLabel.setStyleSheet(f"color: {color}; font-size: 11px;")
    
    def _on_connection_changed(self, client_id: str, connected: bool):
        """连接变化回调"""
        action = "连接" if connected else "断开"
        self.log_message.emit("info", f"客户端{action}: {client_id}")
    
    # ========================================================================
    # 数据集管理
    # ========================================================================
    
    def _update_dataset_list(self):
        """更新数据集列表"""
        self.datasetList.clear()
        
        if not self.server or not self.server.ied:
            return
        
        # 遍历所有访问点、逻辑设备、逻辑节点，收集所有数据集
        for ap_name, ap in self.server.ied.access_points.items():
            for ld_name, ld in ap.logical_devices.items():
                for ln_name, ln in ld.logical_nodes.items():
                    for ds_name, ds in ln.data_sets.items():
                        # 构建完整路径
                        full_path = f"{self.server.ied.name}{ld_name}/{ln_name}.{ds_name}"
                        item_text = f"{ln_name}.{ds_name} ({len(ds.fcdas)} FCDAs)"
                        
                        # 添加到列表，数据存储完整信息
                        from PyQt6.QtWidgets import QListWidgetItem
                        item = QListWidgetItem(item_text)
                        item.setData(Qt.ItemDataRole.UserRole, {
                            'path': full_path,
                            'ap_name': ap_name,
                            'ld_name': ld_name,
                            'ln_name': ln_name,
                            'ds_name': ds_name,
                            'dataset': ds
                        })
                        self.datasetList.addItem(item)
    
    def _on_dataset_selected(self, current, previous):
        """处理数据集选择"""
        if not current:
            self.datasetNameLabel.setText("选择数据集以查看详情")
            self.fcdaTable.setRowCount(0)
            self.controlBlockTable.setRowCount(0)
            return
        
        # 获取数据集信息
        data = current.data(Qt.ItemDataRole.UserRole)
        dataset = data['dataset']
        path = data['path']
        
        # 更新标题
        self.datasetNameLabel.setText(f"数据集: {path}")
        
        # 显示FCDA列表
        self._display_fcdas(dataset)
        
        # 显示关联的控制块
        self._display_control_blocks(data)
    
    def _display_fcdas(self, dataset):
        """显示数据集的FCDA列表"""
        self.fcdaTable.setRowCount(len(dataset.fcdas))
        
        for i, fcda in enumerate(dataset.fcdas):
            ln_name = f'{fcda.get("prefix", "")}{fcda.get("lnClass", "")}{fcda.get("lnInst", "")}'
            self.fcdaTable.setItem(i, 0, QTableWidgetItem(fcda.get('ldInst', '')))
            self.fcdaTable.setItem(i, 1, QTableWidgetItem(ln_name))
            self.fcdaTable.setItem(i, 2, QTableWidgetItem(fcda.get('doName', '')))
            self.fcdaTable.setItem(i, 3, QTableWidgetItem(fcda.get('daName', '')))
            self.fcdaTable.setItem(i, 4, QTableWidgetItem(fcda.get('fc', '')))
            self.fcdaTable.setItem(i, 5, QTableWidgetItem(''))
    
    def _display_control_blocks(self, data):
        """显示关联的控制块（以属性-值格式显示）"""
        if not self.server or not self.server.ied:
            self.controlBlockTable.setRowCount(0)
            return
        
        # 获取逻辑节点
        ap = self.server.ied.access_points.get(data['ap_name'])
        if not ap:
            self.controlBlockTable.setRowCount(0)
            return
        
        ld = ap.logical_devices.get(data['ld_name'])
        if not ld:
            self.controlBlockTable.setRowCount(0)
            return
        
        ln = ld.logical_nodes.get(data['ln_name'])
        if not ln:
            self.controlBlockTable.setRowCount(0)
            return
        
        ds_name = data['ds_name']
        
        # 收集所有引用该数据集的控制块的属性
        properties = []
        
        # ReportControl
        for rc_name, rc in ln.report_controls.items():
            if rc.dataset == ds_name:
                properties.extend([
                    ("=== ReportControl ===", ""),
                    ("控制块名称", rc_name),
                    ('缓冲型', "缓冲" if rc.buffered else "非缓冲"),
                    ("控制块路径", f"{data['ld_name']}/{data['ln_name']}.{rc_name}"),
                    ("报告ID", rc.rptid or "-"),
                    ("缓冲时间", f"{rc.buf_time} ms"),
                    ("完整性周期", f"{rc.intg_pd} ms"),
                    ("配置选项", ", ".join([k for k, v in rc.options.items() if v and isinstance(v, bool)]) or "-"),
                ])
        
        # GSEControl
        for gse_name, gse in ln.gse_controls.items():
            if gse.dataset == ds_name:
                properties.extend([
                    ("=== GSEControl ===", ""),
                    ("控制块名称", gse_name),
                    ("控制块路径", f"{data['ld_name']}/{data['ln_name']}.{gse_name}"),
                    ("GOOSE控制块名", gse.gocbname or "-"),
                    ("允许生存时间", f"{gse.time_allowed_to_live} ms"),
                    ("IED名称", gse.options.get('iedName', '-')),
                    ("接入点名称", gse.options.get('apName', '-')),
                ])
        
        # SampledValueControl
        for smv_name, smv in ln.smv_controls.items():
            if smv.dataset == ds_name:
                properties.extend([
                    ("=== SampledValueControl ===", ""),
                    ("控制块名称", smv_name),
                    ("控制块路径", f"{data['ld_name']}/{data['ln_name']}.{smv_name}"),
                    ("SMV控制块名", smv.smvcbname or "-"),
                    ("采样率", str(smv.smprate)),
                    ("采样模式", smv.smpmod),
                    ("IED名称", smv.options.get('iedName', '-')),
                    ("接入点名称", smv.options.get('apName', '-')),
                ])
        
        # LogControl
        for log_name, log in ln.log_controls.items():
            if log.dataset == ds_name:
                properties.extend([
                    ("=== LogControl ===", ""),
                    ("控制块名称", log_name),
                    ("控制块路径", f"{data['ld_name']}/{data['ln_name']}.{log_name}"),
                    ("日志名称", log.logname or "-"),
                    ("日志启用", "是" if log.log_ena else "否"),
                    ("完整性周期", f"{log.intg_pd} ms"),
                    ("配置选项", ", ".join([k for k, v in log.options.items() if v and isinstance(v, bool)]) or "-"),
                ])
        
        # 显示控制块属性
        self.controlBlockTable.setRowCount(len(properties))
        
        for i, (prop, value) in enumerate(properties):
            prop_item = QTableWidgetItem(prop)
            value_item = QTableWidgetItem(str(value))
            
            # 如果是标题行，设置粗体
            if prop.startswith("==="):
                from PyQt6.QtGui import QFont
                font = QFont()
                font.setBold(True)
                prop_item.setFont(font)
                prop_item.setBackground(Qt.GlobalColor.lightGray)
                value_item.setBackground(Qt.GlobalColor.lightGray)
            
            self.controlBlockTable.setItem(i, 0, prop_item)
            self.controlBlockTable.setItem(i, 1, value_item)
    
    def _on_data_changed(self, reference: str, old_value, new_value):
        """数据变化回调"""
        self.data_tree.update_value(reference, new_value)
