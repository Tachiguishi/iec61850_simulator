"""
IEC61850 Simulator Package
==========================

基于PyQt的IEC61850协议仿真器，支持服务端和客户端两种模式。

服务端模式: 仿真IED设备，提供MMS服务
客户端模式: 连接IED设备，读写数据点
"""

from config.constants import APP_VERSION, APP_NAME, APP_ORG_NAME

__version__ = APP_VERSION
__author__ = "IEC61850 Simulator Team"

from .data_model import (
    DataAttribute,
    DataObject,
    LogicalNode,
    LogicalDevice,
    IED,
)

from .data_model_manager import DataModelManager

__all__ = [
    "DataAttribute",
    "DataObject", 
    "LogicalNode",
    "LogicalDevice",
    "IED",
    "DataModelManager",
]
