"""
IEC61850 Client Module
======================

客户端模块，用于连接和操作IED设备。
"""

from .client_proxy import ClientConfig, ClientState

__all__ = ["ClientConfig", "ClientState"]
