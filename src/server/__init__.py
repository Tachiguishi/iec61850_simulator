"""
IEC61850 Server Module
======================

服务端模块，用于仿真IED设备，提供MMS协议服务。
"""

from .server_proxy import ServerConfig, ServerState

__all__ = ["ServerConfig", "ServerState"]
