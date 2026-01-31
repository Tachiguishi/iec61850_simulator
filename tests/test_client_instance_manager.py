"""
Tests for Client Instance Manager
=================================
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from client.instance_manager import ClientInstanceManager, ClientInstance
from client.client_proxy import ClientConfig, ClientState


class TestClientInstanceManager:
    """测试客户端实例管理器"""
    
    @pytest.fixture
    def manager(self):
        """创建测试用的管理器"""
        with patch('client.instance_manager.IEC61850ClientProxy') as mock_proxy:
            mock_instance = MagicMock()
            mock_instance.state = ClientState.DISCONNECTED
            mock_proxy.return_value = mock_instance
            
            mgr = ClientInstanceManager("/tmp/test.sock", 1000)
            yield mgr
    
    def test_create_instance(self, manager):
        """测试创建实例"""
        instance = manager.create_instance("TestClient")
        
        assert instance is not None
        assert instance.name == "TestClient"
        assert instance.id is not None
        assert len(instance.id) == 8
    
    def test_create_instance_with_config(self, manager):
        """测试使用配置创建实例"""
        config = ClientConfig(
            timeout_ms=10000,
            retry_count=5
        )
        
        instance = manager.create_instance("CustomClient", config)
        
        assert instance.config.timeout_ms == 10000
        assert instance.config.retry_count == 5
    
    def test_create_instance_with_custom_id(self, manager):
        """测试使用自定义ID创建实例"""
        instance = manager.create_instance("TestClient", instance_id="client123")
        
        assert instance.id == "client123"
    
    def test_get_instance(self, manager):
        """测试获取实例"""
        instance = manager.create_instance("TestClient")
        
        retrieved = manager.get_instance(instance.id)
        
        assert retrieved is instance
    
    def test_get_nonexistent_instance(self, manager):
        """测试获取不存在的实例"""
        result = manager.get_instance("nonexistent")
        
        assert result is None
    
    def test_remove_instance(self, manager):
        """测试移除实例"""
        instance = manager.create_instance("TestClient")
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
        manager.create_instance("Client1")
        manager.create_instance("Client2")
        manager.create_instance("Client3")
        
        instances = manager.get_all_instances()
        
        assert len(instances) == 3
    
    def test_get_instance_count(self, manager):
        """测试获取实例数量"""
        assert manager.get_instance_count() == 0
        
        manager.create_instance("Client1")
        assert manager.get_instance_count() == 1
        
        manager.create_instance("Client2")
        assert manager.get_instance_count() == 2
    
    def test_instance_added_callback(self, manager):
        """测试实例添加回调"""
        callback = Mock()
        manager.on_instance_added(callback)
        
        instance = manager.create_instance("TestClient")
        
        callback.assert_called_once_with(instance)
    
    def test_instance_removed_callback(self, manager):
        """测试实例移除回调"""
        callback = Mock()
        manager.on_instance_removed(callback)
        
        instance = manager.create_instance("TestClient")
        manager.remove_instance(instance.id)
        
        callback.assert_called_once_with(instance.id)
    
    def test_log_callback(self, manager):
        """测试日志回调"""
        callback = Mock()
        manager.on_log(callback)
        
        manager.create_instance("TestClient")
        
        assert callback.called
        # 检查调用参数格式: (instance_id, level, message)
        args = callback.call_args[0]
        assert len(args) == 3
        assert args[1] == "info"
    
    def test_instance_target_info(self, manager):
        """测试实例目标信息"""
        instance = manager.create_instance("TestClient")
        instance.target_host = "192.168.1.100"
        instance.target_port = 8102
        
        assert instance.target_host == "192.168.1.100"
        assert instance.target_port == 8102
    
    def test_instance_to_dict(self, manager):
        """测试实例转字典"""
        instance = manager.create_instance("TestClient")
        instance.target_host = "127.0.0.1"
        instance.target_port = 102
        
        data = instance.to_dict()
        
        assert data["name"] == "TestClient"
        assert data["target_host"] == "127.0.0.1"
        assert data["target_port"] == 102
        assert "id" in data
        assert "state" in data
        assert "created_at" in data


class TestClientInstance:
    """测试客户端实例数据类"""
    
    def test_instance_state_property(self):
        """测试状态属性"""
        mock_proxy = MagicMock()
        mock_proxy.state = ClientState.CONNECTED
        
        instance = ClientInstance(
            id="test123",
            name="TestClient",
            config=ClientConfig(),
            proxy=mock_proxy
        )
        
        assert instance.state == ClientState.CONNECTED


class TestClientInstancePersistence:
    """测试客户端实例持久化"""
    
    @pytest.fixture
    def manager(self, tmp_path):
        """创建测试用的管理器"""
        with patch('client.instance_manager.IEC61850ClientProxy') as mock_proxy:
            mock_instance = MagicMock()
            mock_instance.state = ClientState.DISCONNECTED
            mock_proxy.return_value = mock_instance
            
            mgr = ClientInstanceManager("/tmp/test.sock", 1000)
            yield mgr
    
    def test_save_to_file(self, manager, tmp_path):
        """测试保存配置到文件"""
        instance1 = manager.create_instance("Client1")
        instance1.target_host = "192.168.1.100"
        instance1.target_port = 8102
        
        instance2 = manager.create_instance("Client2")
        instance2.target_host = "10.0.0.1"
        instance2.target_port = 102
        
        file_path = tmp_path / "clients.yaml"
        result = manager.save_to_file(file_path)
        
        assert result is True
        assert file_path.exists()
        
        # 验证文件内容
        import yaml
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)
        
        assert data["type"] == "client_instances"
        assert len(data["instances"]) == 2
    
    def test_load_from_file(self, tmp_path):
        """测试从文件加载配置"""
        # 创建配置文件
        import yaml
        config_data = {
            "version": "1.0",
            "type": "client_instances",
            "instances": [
                {
                    "id": "cli001",
                    "name": "LoadedClient",
                    "target_host": "10.0.0.1",
                    "target_port": 9102,
                    "config": {
                        "timeout_ms": 10000,
                        "retry_count": 5,
                    }
                }
            ]
        }
        file_path = tmp_path / "clients.yaml"
        with open(file_path, 'w') as f:
            yaml.dump(config_data, f)
        
        # 加载配置
        with patch('client.instance_manager.IEC61850ClientProxy') as mock_proxy:
            mock_instance = MagicMock()
            mock_instance.state = ClientState.DISCONNECTED
            mock_proxy.return_value = mock_instance
            
            manager = ClientInstanceManager("/tmp/test.sock", 1000)
            count = manager.load_from_file(file_path)
        
        assert count == 1
        instance = manager.get_instance("cli001")
        assert instance is not None
        assert instance.name == "LoadedClient"
        assert instance.target_host == "10.0.0.1"
        assert instance.target_port == 9102
        assert instance.config.timeout_ms == 10000
    
    def test_load_nonexistent_file(self, manager, tmp_path):
        """测试加载不存在的文件"""
        file_path = tmp_path / "nonexistent.yaml"
        count = manager.load_from_file(file_path)
        
        assert count == 0
    
    def test_save_and_load_roundtrip(self, tmp_path):
        """测试保存后加载的完整流程"""
        with patch('client.instance_manager.IEC61850ClientProxy') as mock_proxy:
            mock_instance = MagicMock()
            mock_instance.state = ClientState.DISCONNECTED
            mock_proxy.return_value = mock_instance
            
            # 创建并保存
            manager1 = ClientInstanceManager("/tmp/test.sock", 1000)
            instance = manager1.create_instance("RoundtripClient", instance_id="rtc123")
            instance.target_host = "172.16.0.1"
            instance.target_port = 7102
            
            file_path = tmp_path / "roundtrip.yaml"
            manager1.save_to_file(file_path)
            
            # 新管理器加载
            manager2 = ClientInstanceManager("/tmp/test.sock", 1000)
            count = manager2.load_from_file(file_path)
        
        assert count == 1
        loaded = manager2.get_instance("rtc123")
        assert loaded.name == "RoundtripClient"
        assert loaded.target_host == "172.16.0.1"
        assert loaded.target_port == 7102
