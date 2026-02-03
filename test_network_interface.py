#!/usr/bin/env python3
"""
测试网络接口配置功能
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from ipc.uds_client import UDSMessageClient

def test_network_interface():
    """测试网络接口API"""
    
    socket_path = "/tmp/iec61850_simulator.sock"
    client = UDSMessageClient(socket_path, 3000)
    
    print("=== 测试 server.get_interfaces ===")
    try:
        response = client.request("server.get_interfaces", {})
        print(f"状态: 成功")
        print(f"接口列表:")
        for iface in response.data.get("interfaces", []):
            name = iface.get("name")
            is_up = iface.get("is_up")
            addresses = iface.get("addresses", [])
            print(f"  - {name} [{'UP' if is_up else 'DOWN'}] {addresses}")
        
        current = response.data.get("current_interface")
        if current:
            print(f"\n当前配置:")
            print(f"  网卡: {current.get('name')}")
            print(f"  前缀长度: {current.get('prefix_len')}")
        else:
            print(f"\n当前配置: 未设置")
    except Exception as e:
        print(f"错误: {e}")
    
    print("\n=== 测试 server.set_interface ===")
    # 获取第一个可用接口
    response = client.request("server.get_interfaces", {})
    interfaces = response.data.get("interfaces", [])
    if interfaces:
        first_iface = interfaces[0].get("name")
        print(f"设置接口为: {first_iface}")
        
        try:
            response = client.request("server.set_interface", {
                "interface_name": first_iface,
                "prefix_len": 24
            })
            print(f"状态: 成功")
            print(f"返回数据: {response.data}")
        except Exception as e:
            print(f"错误: {e}")
        
        # 验证设置
        print("\n验证设置:")
        response = client.request("server.get_interfaces", {})
        current = response.data.get("current_interface")
        if current:
            print(f"  网卡: {current.get('name')}")
            print(f"  前缀长度: {current.get('prefix_len')}")
    else:
        print("没有可用的网络接口")

if __name__ == "__main__":
    print("请确保后端服务已启动 (./iec61850/build/bin/iec61850_core)")
    input("按回车继续...")
    test_network_interface()
