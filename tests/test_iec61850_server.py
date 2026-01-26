"""
IEC61850 Server Unit Tests
===========================

使用pytest测试IEC61850服务器的核心功能
"""

import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call
import pytest

# 添加项目路径
# sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from server.iec61850_server import (
    IEC61850Server, ServerConfig, ServerState, ClientConnection
)
from core.data_model import (
    IED, DataModelManager, LogicalDevice, LogicalNode, DataObject, DataAttribute,
    DataType, FunctionalConstraint, Quality
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_pyiec61850():
    """Mock pyiec61850 模块"""
    with patch("server.iec61850_server.PYIEC61850_AVAILABLE", True):
        with patch("server.iec61850_server.iec61850") as mock_iec:
            # 设置常量
            mock_iec.IEC61850_BOOLEAN = 0
            mock_iec.IEC61850_INT8 = 1
            mock_iec.IEC61850_INT16 = 2
            mock_iec.IEC61850_INT32 = 3
            mock_iec.IEC61850_INT64 = 4
            mock_iec.IEC61850_INT8U = 5
            mock_iec.IEC61850_INT16U = 6
            mock_iec.IEC61850_INT32U = 7
            mock_iec.IEC61850_FLOAT32 = 8
            mock_iec.IEC61850_FLOAT64 = 9
            mock_iec.IEC61850_VISIBLE_STRING_64 = 10
            mock_iec.IEC61850_VISIBLE_STRING_255 = 11
            mock_iec.IEC61850_UNICODE_STRING_255 = 12
            mock_iec.IEC61850_TIMESTAMP = 13
            mock_iec.IEC61850_QUALITY = 14
            mock_iec.IEC61850_ENUMERATED = 15
            
            # FC 常量
            mock_iec.IEC61850_FC_ST = 0
            mock_iec.IEC61850_FC_MX = 1
            mock_iec.IEC61850_FC_SP = 2
            mock_iec.IEC61850_FC_SV = 3
            mock_iec.IEC61850_FC_CF = 4
            mock_iec.IEC61850_FC_DC = 5
            mock_iec.IEC61850_FC_SG = 6
            mock_iec.IEC61850_FC_SE = 7
            mock_iec.IEC61850_FC_SR = 8
            mock_iec.IEC61850_FC_OR = 9
            mock_iec.IEC61850_FC_BL = 10
            mock_iec.IEC61850_FC_EX = 11
            mock_iec.IEC61850_FC_CO = 12
            
            # 触发选项
            mock_iec.TRG_OPT_DATA_CHANGED = 1
            mock_iec.TRG_OPT_DATA_UPDATE = 4
            
            # Edition
            mock_iec.IEC_61850_EDITION_2 = 2
            
            # Mock 函数返回值
            mock_model = MagicMock()
            mock_server = MagicMock()
            mock_config = MagicMock()
            
            mock_iec.IedModel_create.return_value = mock_model
            mock_iec.IedServerConfig_create.return_value = mock_config
            mock_iec.IedServer_createWithConfig.return_value = mock_server
            mock_iec.IedServer_isRunning.return_value = True
            mock_iec.IedServer_getNumberOfOpenConnections.return_value = 0
            
            # Mock 节点创建
            mock_iec.LogicalDevice_create.return_value = MagicMock()
            mock_iec.LogicalNode_create.return_value = MagicMock()
            mock_iec.DataObject_create.return_value = MagicMock()
            
            # Mock DataAttribute
            mock_da = MagicMock()
            mock_da.mmsValue = MagicMock()
            mock_iec.DataAttribute_create.return_value = mock_da
            mock_iec.DataAttribute_getType.return_value = mock_iec.IEC61850_INT32
            
            # Mock toModelNode
            mock_iec.toModelNode.return_value = MagicMock()
            
            yield mock_iec


@pytest.fixture
def server_config():
    """创建测试用服务器配置"""
    return ServerConfig(
        ip_address="127.0.0.1",
        port=10102,
        max_connections=5,
        update_interval_ms=100,
        enable_random_values=False,
        enable_reporting=False,
        enable_goose=False,
    )


@pytest.fixture
def sample_ied():
    """创建测试用IED数据模型"""
    return DataModelManager().create_default_ied(name = "TestIED")


@pytest.fixture
def server(server_config, sample_ied, mock_pyiec61850):
    """创建测试用服务器实例"""
    srv = IEC61850Server(config=server_config)
    srv.load_model(sample_ied)
    yield srv
    # 清理
    if srv.is_running():
        srv.stop()


# ============================================================================
# ServerConfig 测试
# ============================================================================

class TestServerConfig:
    """测试服务器配置类"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = ServerConfig()
        assert config.ip_address == "0.0.0.0"
        assert config.port == 102
        assert config.max_connections == 10
        assert config.update_interval_ms == 1000
        assert config.enable_random_values is False
        assert config.enable_reporting is True
        assert config.enable_goose is False
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = ServerConfig(
            ip_address="192.168.1.100",
            port=8080,
            max_connections=20,
            update_interval_ms=500
        )
        assert config.ip_address == "192.168.1.100"
        assert config.port == 8080
        assert config.max_connections == 20
        assert config.update_interval_ms == 500
    
    def test_from_dict(self):
        """测试从字典创建配置"""
        data = {
            "ip_address": "10.0.0.1",
            "port": 9999,
            "max_connections": 15,
            "enable_random_values": True,
        }
        config = ServerConfig.from_dict(data)
        assert config.ip_address == "10.0.0.1"
        assert config.port == 9999
        assert config.max_connections == 15
        assert config.enable_random_values is True
        # 其他字段应使用默认值
        assert config.update_interval_ms == 1000


# ============================================================================
# ClientConnection 测试
# ============================================================================

class TestClientConnection:
    """测试客户端连接类"""
    
    def test_client_creation(self):
        """测试客户端连接创建"""
        client = ClientConnection(
            id="client_123",
            address=("192.168.1.10", 12345)
        )
        assert client.id == "client_123"
        assert client.address == ("192.168.1.10", 12345)
        assert client.subscriptions == set()
    
    def test_client_hash(self):
        """测试客户端哈希"""
        client1 = ClientConnection(id="client_1", address=("127.0.0.1", 1000))
        client2 = ClientConnection(id="client_1", address=("127.0.0.1", 2000))
        client3 = ClientConnection(id="client_2", address=("127.0.0.1", 1000))
        
        # 相同 ID 应有相同哈希
        assert hash(client1) == hash(client2)
        # 不同 ID 应有不同哈希
        assert hash(client1) != hash(client3)


# ============================================================================
# IEC61850Server 初始化测试
# ============================================================================

class TestServerInitialization:
    """测试服务器初始化"""
    
    def test_default_initialization(self, mock_pyiec61850):
        """测试默认初始化"""
        server = IEC61850Server()
        assert server.config.ip_address == "0.0.0.0"
        assert server.config.port == 102
        assert server.state == ServerState.STOPPED
        assert server.ied is None
        assert server._ied_server is None
        assert server._ied_model is None
    
    def test_custom_config_initialization(self, server, mock_pyiec61850):
        """测试使用自定义配置初始化"""
        assert server.config.ip_address == "127.0.0.1"
        assert server.config.port == 10102
        assert server.config.max_connections == 5
        assert server.state == ServerState.STOPPED
        assert server.ied is not None
        assert server._ied_server is None
        assert server._ied_model is not None


# ============================================================================
# IED 模型管理测试
# ============================================================================

class TestIEDManagement:
    """测试IED模型管理"""
    
    def test_load_ied(self, server, sample_ied):
        """测试加载IED"""
        assert server.ied is not None
        assert server.ied.name == "TestIED"
        assert "LD0" in server.ied.logical_devices
    
    def test_get_data_value(self, server):
        """测试获取数据值"""
        value = server.get_data_value("LD0/MMXU1.TotW.mag")
        assert value == 1000.0
    
    def test_get_data_value_invalid_ref(self, server):
        """测试获取不存在的数据值"""
        value = server.get_data_value("LD0/INVALID.Path.ref")
        assert value is None
    
    def test_set_data_value(self, server):
        """测试设置数据值"""
        success = server.set_data_value("LD0/MMXU1.TotW.mag", 2000.0)
        assert success is True
        
        # 验证值已更新
        value = server.get_data_value("LD0/MMXU1.TotW.mag")
        assert value == 2000.0
    
    def test_set_data_value_invalid_ref(self, server):
        """测试设置不存在的数据值"""
        success = server.set_data_value("LD0/INVALID.Path.ref", 999)
        assert success is False


# ============================================================================
# 服务器生命周期测试
# ============================================================================

class TestServerLifecycle:
    """测试服务器生命周期"""
    
    def test_start_server(self, server, mock_pyiec61850):
        """测试启动服务器"""
        success = server.start()
        assert success is True
        assert server.state == ServerState.RUNNING
        
        # 验证 pyiec61850 调用
        mock_pyiec61850.IedModel_create.assert_called_once_with("TestIED")
        mock_pyiec61850.IedServer_start.assert_called_once()
    
    def test_start_server_without_ied(self, server_config, mock_pyiec61850):
        """测试在没有IED的情况下启动服务器（应创建默认IED）"""
        server = IEC61850Server(config=server_config)
        success = server.start()
        assert success is True
        assert server.ied is not None  # 应该创建了默认IED
    
    def test_start_already_running(self, server, mock_pyiec61850):
        """测试重复启动服务器"""
        server.start()
        # 再次启动
        success = server.start()
        assert success is False
    
    def test_stop_server(self, server, mock_pyiec61850):
        """测试停止服务器"""
        server.start()
        success = server.stop()
        assert success is True
        assert server.state == ServerState.STOPPED
        
        # 验证清理调用
        mock_pyiec61850.IedServer_stop.assert_called_once()
        mock_pyiec61850.IedServer_destroy.assert_called_once()
    
    def test_stop_not_running(self, server, mock_pyiec61850):
        """测试停止未运行的服务器"""
        success = server.stop()
        assert success is True
    
    def test_restart_server(self, server, mock_pyiec61850):
        """测试重启服务器"""
        server.start()
        success = server.restart()
        assert success is True
        assert server.state == ServerState.RUNNING
    
    def test_is_running(self, server, mock_pyiec61850):
        """测试运行状态检查"""
        assert server.is_running() is False
        
        server.start()
        mock_pyiec61850.IedServer_isRunning.return_value = True
        assert server.is_running() is True
        
        server.stop()
        mock_pyiec61850.IedServer_isRunning.return_value = False
        assert server.is_running() is False


# ============================================================================
# 数据类型映射测试
# ============================================================================

class TestDataTypeMapping:
    """测试数据类型映射"""
    
    def test_map_data_type(self, server, mock_pyiec61850):
        """测试各种数据类型映射"""
        assert server._map_data_type(DataType.BOOLEAN) == mock_pyiec61850.IEC61850_BOOLEAN
        assert server._map_data_type(DataType.INT32) == mock_pyiec61850.IEC61850_INT32
        assert server._map_data_type(DataType.FLOAT32) == mock_pyiec61850.IEC61850_FLOAT32
        assert server._map_data_type(DataType.FLOAT64) == mock_pyiec61850.IEC61850_FLOAT64
        assert server._map_data_type(DataType.QUALITY) == mock_pyiec61850.IEC61850_QUALITY
    
    def test_map_fc(self, server, mock_pyiec61850):
        """测试功能约束映射"""
        assert server._map_fc(FunctionalConstraint.ST) == mock_pyiec61850.IEC61850_FC_ST
        assert server._map_fc(FunctionalConstraint.MX) == mock_pyiec61850.IEC61850_FC_MX
        assert server._map_fc(FunctionalConstraint.SP) == mock_pyiec61850.IEC61850_FC_SP
        assert server._map_fc(FunctionalConstraint.CF) == mock_pyiec61850.IEC61850_FC_CF


# ============================================================================
# 回调机制测试
# ============================================================================

class TestCallbacks:
    """测试回调机制"""
    
    def test_state_change_callback(self, server, mock_pyiec61850):
        """测试状态变化回调"""
        callback_states = []
        
        def state_callback(state):
            callback_states.append(state)
        
        server.on_state_change(state_callback)
        server.start()
        
        # 应该收到 STARTING 和 RUNNING 状态
        assert ServerState.STARTING in callback_states
        assert ServerState.RUNNING in callback_states
    
    def test_data_change_callback(self, server, mock_pyiec61850):
        """测试数据变化回调"""
        changes = []
        
        def data_callback(ref, old_val, new_val):
            changes.append((ref, old_val, new_val))
        
        server.on_data_change(data_callback)
        server.start()
        server.set_data_value("LD0/MMXU1.TotW.mag", 3000.0)
        
        # 验证回调被调用
        assert len(changes) == 1
        assert changes[0][0] == "LD0/MMXU1.TotW.mag"
        assert changes[0][1] == 1000.0
        assert changes[0][2] == 3000.0
    
    def test_log_callback(self, server, mock_pyiec61850):
        """测试日志回调"""
        logs = []
        
        def log_callback(level, message):
            logs.append((level, message))
        
        server.on_log(log_callback)
        server._log("info", "Test message")
        
        assert len(logs) == 1
        assert logs[0][0] == "info"
        assert logs[0][1] == "Test message"


# ============================================================================
# 客户端管理测试
# ============================================================================

class TestClientManagement:
    """测试客户端管理"""
    
    def test_get_connected_clients_empty(self, server):
        """测试获取空客户端列表"""
        clients = server.get_connected_clients()
        assert clients == []
    
    def test_client_tracking(self, server, mock_pyiec61850):
        """测试客户端跟踪"""
        server.start()
        
        # 模拟客户端连接
        mock_pyiec61850.IedServer_getNumberOfOpenConnections.return_value = 2
        
        # 触发更新
        server._update_client_tracking(2)
        
        clients = server.get_connected_clients()
        assert len(clients) == 2


# ============================================================================
# 服务器状态测试
# ============================================================================

class TestServerStatus:
    """测试服务器状态"""
    
    def test_get_status_stopped(self, server):
        """测试获取停止状态的服务器状态"""
        status = server.get_status()
        assert status["state"] == "STOPPED"
        assert status["address"] == "127.0.0.1:10102"
        assert status["ied_name"] == "TestIED"
        assert status["client_count"] == 0
    
    def test_get_status_running(self, server, mock_pyiec61850):
        """测试获取运行状态的服务器状态"""
        mock_pyiec61850.IedServer_getNumberOfOpenConnections.return_value = 3
        server.start()
        
        status = server.get_status()
        assert status["state"] == "RUNNING"
        assert status["ied_name"] == "TestIED"
        assert status["client_count"] == 3
        assert status["config"]["update_interval_ms"] == 100


# ============================================================================
# 错误处理测试
# ============================================================================

class TestErrorHandling:
    """测试错误处理"""
    
    def test_start_without_pyiec61850(self, server_config, sample_ied):
        """测试在没有 pyiec61850 的情况下启动"""
        with patch("server.iec61850_server.PYIEC61850_AVAILABLE", False):
            server = IEC61850Server(config=server_config)
            server.load_model(sample_ied)
            success = server.start()
            assert success is False
            assert server.state == ServerState.ERROR
    
    def test_start_failure(self, server, mock_pyiec61850):
        """测试启动失败"""
        mock_pyiec61850.IedServer_isRunning.return_value = False
        success = server.start()
        assert success is False
        assert server.state == ServerState.ERROR
    
    def test_set_value_no_server(self, server_config, sample_ied, mock_pyiec61850):
        """测试在服务器未启动时设置值"""
        server = IEC61850Server(config=server_config)
        server.load_model(sample_ied)
        # 不启动服务器，直接设置值
        success = server.set_data_value("LD0/MMXU1.TotW.mag", 5000.0)
        # 值应该在数据模型中更新，但不会更新到服务器
        assert success is True


# ============================================================================
# 数据更新测试
# ============================================================================

class TestDataUpdate:
    """测试数据更新"""
    
    def test_update_server_value(self, server, mock_pyiec61850):
        """测试更新服务器值"""
        server.start()
        
        # 创建一个模拟的数据属性节点
        mock_da_node = MagicMock()
        server._model_nodes["LD0/MMXU1.TotW.mag"] = mock_da_node
        mock_pyiec61850.DataAttribute_getType.return_value = mock_pyiec61850.IEC61850_FLOAT32
        
        # 更新值
        server._update_server_value("LD0/MMXU1.TotW.mag", 7500.0)
        
        # 验证调用
        mock_pyiec61850.IedServer_lockDataModel.assert_called()
        mock_pyiec61850.IedServer_updateFloatAttributeValue.assert_called_with(
            server._ied_server, mock_da_node, 7500.0
        )
        mock_pyiec61850.IedServer_unlockDataModel.assert_called()
    
    def test_simulate_data_update(self, server, mock_pyiec61850):
        """测试数据仿真更新"""
        server.config.enable_random_values = True
        server.start()
        
        # 添加模拟节点
        mock_da_node = MagicMock()
        server._model_nodes["LD0/MMXU1.TotW.mag"] = mock_da_node
        
        # 触发仿真更新
        initial_value = server.get_data_value("LD0/MMXU1.TotW.mag")
        server._simulate_data_update()
        
        # 验证锁定和解锁被调用
        mock_pyiec61850.IedServer_lockDataModel.assert_called()
        mock_pyiec61850.IedServer_unlockDataModel.assert_called()


# ============================================================================
# 集成测试
# ============================================================================

class TestIntegration:
    """集成测试"""
    
    def test_full_lifecycle(self, server, mock_pyiec61850):
        """测试完整的生命周期"""
        # 启动服务器
        assert server.start() is True
        assert server.is_running() is True
        
        # 设置数据值
        assert server.set_data_value("LD0/MMXU1.TotW.mag", 4500.0) is True
        assert server.get_data_value("LD0/MMXU1.TotW.mag") == 4500.0
        
        # 获取状态
        status = server.get_status()
        assert status["state"] == "RUNNING"
        
        # 停止服务器
        assert server.stop() is True
        assert server.state == ServerState.STOPPED
    
    def test_multiple_callbacks(self, server, mock_pyiec61850):
        """测试多个回调"""
        state_changes = []
        data_changes = []
        logs = []
        
        server.on_state_change(lambda s: state_changes.append(s))
        server.on_data_change(lambda r, o, n: data_changes.append((r, o, n)))
        server.on_log(lambda l, m: logs.append((l, m)))
        
        server.start()
        server.set_data_value("LD0/MMXU1.TotW.mag", 8888.0)
        
        assert len(state_changes) >= 2  # STARTING, RUNNING
        assert len(data_changes) == 1
        assert len(logs) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
