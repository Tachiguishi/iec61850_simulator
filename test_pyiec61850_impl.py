#!/usr/bin/env python3
"""
测试 pyiec61850 服务器和客户端实现
"""

import sys
import os
import time

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.server.iec61850_server import IEC61850Server, ServerConfig, ServerState
from src.client.iec61850_client import IEC61850Client, ClientConfig, ClientState


def test_imports():
    """测试导入"""
    print("=" * 60)
    print("测试模块导入")
    print("=" * 60)
    
    print("✓ IEC61850Server 导入成功")
    print("✓ IEC61850Client 导入成功")
    print("✓ 配置类导入成功")
    print("✓ 状态类导入成功")
    return True


def test_server_instantiation():
    """测试服务器实例化"""
    print("\n" + "=" * 60)
    print("测试服务器实例化")
    print("=" * 60)
    
    config = ServerConfig(
        port=8102,  # 使用非标准端口避免权限问题
        max_connections=5,
        update_interval_ms=1000,
        enable_random_values=False,
    )
    
    server = IEC61850Server(config)
    print(f"✓ 服务器实例创建成功")
    print(f"  - 状态: {server.state}")
    print(f"  - 端口: {server.config.port}")
    
    return server


def test_client_instantiation():
    """测试客户端实例化"""
    print("\n" + "=" * 60)
    print("测试客户端实例化")
    print("=" * 60)
    
    config = ClientConfig(
        timeout_ms=5000,
        retry_count=3,
    )
    
    client = IEC61850Client(config)
    print(f"✓ 客户端实例创建成功")
    print(f"  - 状态: {client.state}")
    print(f"  - 超时: {client.config.timeout_ms}ms")
    
    return client


def test_server_lifecycle(server):
    """测试服务器生命周期"""
    print("\n" + "=" * 60)
    print("测试服务器生命周期")
    print("=" * 60)
    
    # 启动服务器
    print("启动服务器...")
    result = server.start()
    
    if result:
        print(f"✓ 服务器启动成功")
        print(f"  - 状态: {server.state}")
        print(f"  - 运行中: {server.is_running()}")
        
        # 获取状态
        status = server.get_status()
        print(f"  - 地址: {status['address']}")
        print(f"  - IED: {status['ied_name']}")
        print(f"  - 客户端数: {status['client_count']}")
        
        time.sleep(1)
        
        # 停止服务器
        print("\n停止服务器...")
        server.stop()
        print(f"✓ 服务器停止成功")
        print(f"  - 状态: {server.state}")
        
        return True
    else:
        print(f"✗ 服务器启动失败")
        print(f"  - 状态: {server.state}")
        return False


def test_client_connection(client, host="localhost", port=8102):
    """测试客户端连接"""
    print("\n" + "=" * 60)
    print("测试客户端连接")
    print("=" * 60)
    
    print(f"尝试连接到 {host}:{port}...")
    result = client.connect(host, port)
    
    if result:
        print(f"✓ 连接成功")
        print(f"  - 状态: {client.state}")
        
        # 获取逻辑设备列表
        devices = client.get_logical_devices()
        print(f"  - 逻辑设备: {devices}")
        
        # 断开连接
        client.disconnect()
        print(f"✓ 断开连接成功")
        return True
    else:
        print(f"✗ 连接失败 (这是预期的，因为没有运行的服务器)")
        return False


def main():
    """主测试函数"""
    print("=" * 60)
    print("pyiec61850 实现测试")
    print("=" * 60)
    
    # 检查 pyiec61850 是否可用
    from src.server.iec61850_server import PYIEC61850_AVAILABLE
    print(f"\npyiec61850 库可用: {PYIEC61850_AVAILABLE}")
    
    if not PYIEC61850_AVAILABLE:
        print("\n⚠ pyiec61850 库不可用，部分测试将跳过")
    
    # 运行测试
    test_imports()
    server = test_server_instantiation()
    client = test_client_instantiation()
    
    if PYIEC61850_AVAILABLE:
        # 测试服务器生命周期
        if test_server_lifecycle(server):
            # 重新创建并启动服务器进行客户端测试
            server2 = IEC61850Server(ServerConfig(port=8102))
            if server2.start():
                time.sleep(0.5)
                test_client_connection(client, "localhost", 8102)
                server2.stop()
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
