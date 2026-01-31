"""
Tests for Server Instance Manager
=================================
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from server.instance_manager import ServerInstanceManager, ServerInstance
from server.server_proxy import ServerConfig, ServerState


class TestServerInstanceManager:
    """测试服务器实例管理器"""
    
    @pytest.fixture
    def manager(self):
        """创建测试用的管理器"""
        with patch('server.instance_manager.IEC61850ServerProxy') as mock_proxy:
            mock_instance = MagicMock()
            mock_instance.state = ServerState.STOPPED
            mock_instance.ied = None
            mock_proxy.return_value = mock_instance
            
            mgr = ServerInstanceManager("/tmp/test.sock", 1000)
            yield mgr
    
    def test_create_instance(self, manager):
        """测试创建实例"""
        instance = manager.create_instance("TestServer")
        
        assert instance is not None
        assert instance.name == "TestServer"
        assert instance.id is not None
        assert len(instance.id) == 8
    
    def test_create_instance_with_config(self, manager):
        """测试使用配置创建实例"""
        config = ServerConfig(
            ip_address="192.168.1.100",
            port=8102,
            max_connections=5
        )
        
        instance = manager.create_instance("CustomServer", config)
        
        assert instance.config.ip_address == "192.168.1.100"
        assert instance.config.port == 8102
        assert instance.config.max_connections == 5
    
    def test_create_instance_with_custom_id(self, manager):
        """测试使用自定义ID创建实例"""
        instance = manager.create_instance("TestServer", instance_id="custom123")
        
        assert instance.id == "custom123"
    
    def test_get_instance(self, manager):
        """测试获取实例"""
        instance = manager.create_instance("TestServer")
        
        retrieved = manager.get_instance(instance.id)
        
        assert retrieved is instance
    
    def test_get_nonexistent_instance(self, manager):
        """测试获取不存在的实例"""
        result = manager.get_instance("nonexistent")
        
        assert result is None
    
    def test_remove_instance(self, manager):
        """测试移除实例"""
        instance = manager.create_instance("TestServer")
        instance_id = instance.id
        
        result = manager.remove_instance(instance_id)
        
        assert result is True
        assert manager.get_instance(instance_id) is None
    
    def test_remove_nonexistent_instance(self, manager):
        """测试移除不存在的实例"""
        result = manager.remove_instance("nonexistent")
        
        assert result is False
    
    def test_get_all_instances(self, manager):
        """测试获取所有实例"""
        manager.create_instance("Server1")
        manager.create_instance("Server2")
        manager.create_instance("Server3")
        
        instances = manager.get_all_instances()
        
        assert len(instances) == 3
    
    def test_get_instance_count(self, manager):
        """测试获取实例数量"""
        assert manager.get_instance_count() == 0
        
        manager.create_instance("Server1")
        assert manager.get_instance_count() == 1
        
        manager.create_instance("Server2")
        assert manager.get_instance_count() == 2
    
    def test_instance_added_callback(self, manager):
        """测试实例添加回调"""
        callback = Mock()
        manager.on_instance_added(callback)
        
        instance = manager.create_instance("TestServer")
        
        callback.assert_called_once_with(instance)
    
    def test_instance_removed_callback(self, manager):
        """测试实例移除回调"""
        callback = Mock()
        manager.on_instance_removed(callback)
        
        instance = manager.create_instance("TestServer")
        manager.remove_instance(instance.id)
        
        callback.assert_called_once_with(instance.id)
    
    def test_log_callback(self, manager):
        """测试日志回调"""
        callback = Mock()
        manager.on_log(callback)
        
        manager.create_instance("TestServer")
        
        assert callback.called
        # 检查调用参数格式: (instance_id, level, message)
        args = callback.call_args[0]
        assert len(args) == 3
        assert args[1] == "info"
    
    def test_instance_to_dict(self, manager):
        """测试实例转字典"""
        config = ServerConfig(ip_address="127.0.0.1", port=8102)
        instance = manager.create_instance("TestServer", config)
        
        data = instance.to_dict()
        
        assert data["name"] == "TestServer"
        assert data["ip_address"] == "127.0.0.1"
        assert data["port"] == 8102
        assert "id" in data
        assert "state" in data
        assert "created_at" in data


class TestServerInstance:
    """测试服务器实例数据类"""
    
    def test_instance_state_property(self):
        """测试状态属性"""
        mock_proxy = MagicMock()
        mock_proxy.state = ServerState.RUNNING
        mock_proxy.ied = None
        
        instance = ServerInstance(
            id="test123",
            name="TestServer",
            config=ServerConfig(),
            proxy=mock_proxy
        )
        
        assert instance.state == ServerState.RUNNING
    
    def test_instance_ied_property(self):
        """测试IED属性"""
        mock_proxy = MagicMock()
        mock_ied = MagicMock()
        mock_ied.name = "TestIED"
        mock_proxy.ied = mock_ied
        mock_proxy.state = ServerState.STOPPED
        
        instance = ServerInstance(
            id="test123",
            name="TestServer",
            config=ServerConfig(),
            proxy=mock_proxy
        )
        
        assert instance.ied is mock_ied
        assert instance.ied.name == "TestIED"


class TestServerInstancePersistence:
    """测试服务器实例持久化"""
    
    @pytest.fixture
    def manager(self, tmp_path):
        """创建测试用的管理器"""
        with patch('server.instance_manager.IEC61850ServerProxy') as mock_proxy:
            mock_instance = MagicMock()
            mock_instance.state = ServerState.STOPPED
            mock_instance.ied = None
            mock_proxy.return_value = mock_instance
            
            mgr = ServerInstanceManager("/tmp/test.sock", 1000)
            yield mgr
    
    def test_save_to_file(self, manager, tmp_path):
        """测试保存配置到文件"""
        config = ServerConfig(ip_address="192.168.1.100", port=8102)
        manager.create_instance("Server1", config)
        manager.create_instance("Server2")
        
        file_path = tmp_path / "servers.yaml"
        result = manager.save_to_file(file_path)
        
        assert result is True
        assert file_path.exists()
        
        # 验证文件内容
        import yaml
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)
        
        assert data["type"] == "server_instances"
        assert len(data["instances"]) == 2
    
    def test_load_from_file(self, tmp_path):
        """测试从文件加载配置"""
        # 创建配置文件
        import yaml
        config_data = {
            "version": "1.0",
            "type": "server_instances",
            "instances": [
                {
                    "id": "srv001",
                    "name": "LoadedServer",
                    "config": {
                        "ip_address": "10.0.0.1",
                        "port": 9102,
                        "max_connections": 20,
                    }
                }
            ]
        }
        file_path = tmp_path / "servers.yaml"
        with open(file_path, 'w') as f:
            yaml.dump(config_data, f)
        
        # 加载配置
        with patch('server.instance_manager.IEC61850ServerProxy') as mock_proxy:
            mock_instance = MagicMock()
            mock_instance.state = ServerState.STOPPED
            mock_instance.ied = None
            mock_proxy.return_value = mock_instance
            
            manager = ServerInstanceManager("/tmp/test.sock", 1000)
            count = manager.load_from_file(file_path)
        
        assert count == 1
        instance = manager.get_instance("srv001")
        assert instance is not None
        assert instance.name == "LoadedServer"
        assert instance.config.ip_address == "10.0.0.1"
        assert instance.config.port == 9102
    
    def test_load_nonexistent_file(self, manager, tmp_path):
        """测试加载不存在的文件"""
        file_path = tmp_path / "nonexistent.yaml"
        count = manager.load_from_file(file_path)
        
        assert count == 0
    
    def test_save_and_load_roundtrip(self, tmp_path):
        """测试保存后加载的完整流程"""
        with patch('server.instance_manager.IEC61850ServerProxy') as mock_proxy:
            mock_instance = MagicMock()
            mock_instance.state = ServerState.STOPPED
            mock_instance.ied = None
            mock_proxy.return_value = mock_instance
            
            # 创建并保存
            manager1 = ServerInstanceManager("/tmp/test.sock", 1000)
            config = ServerConfig(ip_address="172.16.0.1", port=7102)
            manager1.create_instance("RoundtripServer", config, instance_id="rt123")
            
            file_path = tmp_path / "roundtrip.yaml"
            manager1.save_to_file(file_path)
            
            # 新管理器加载
            manager2 = ServerInstanceManager("/tmp/test.sock", 1000)
            count = manager2.load_from_file(file_path)
        
        assert count == 1
        instance = manager2.get_instance("rt123")
        assert instance.name == "RoundtripServer"
        assert instance.config.ip_address == "172.16.0.1"
        assert instance.config.port == 7102
