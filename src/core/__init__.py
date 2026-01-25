"""
IEC61850 Simulator Package
==========================

基于PyQt的IEC61850协议仿真器，支持服务端和客户端两种模式。

服务端模式: 仿真IED设备，提供MMS服务
客户端模式: 连接IED设备，读写数据点
"""

__version__ = "1.0.0"
__author__ = "IEC61850 Simulator Team"

from .data_model import (
    DataAttribute,
    DataObject,
    LogicalNode,
    LogicalDevice,
    IED,
    DataModelManager,
)

__all__ = [
    "DataAttribute",
    "DataObject", 
    "LogicalNode",
    "LogicalDevice",
    "IED",
    "DataModelManager",
]
