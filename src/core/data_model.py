"""
IEC61850 Data Model Implementation
==================================

实现IEC61850数据模型层次结构:
- IED (Intelligent Electronic Device)
- AccessPoint
- LogicalDevice (LD)
- LogicalNode (LN)
- DataObject (DO)
- DataAttribute (DA)

基于IEC 61850-7-2和IEC 61850-7-4标准
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from typing import Any, Callable, Dict, List, Optional, Union
from pathlib import Path

import yaml
from loguru import logger


# ============================================================================
# 基础枚举类型
# ============================================================================

class DataType(Enum):
    """IEC61850基本数据类型"""
    BOOLEAN = "BOOLEAN"
    INT8 = "INT8"
    INT16 = "INT16"
    INT32 = "INT32"
    INT64 = "INT64"
    INT8U = "INT8U"
    INT16U = "INT16U"
    INT32U = "INT32U"
    FLOAT32 = "FLOAT32"
    FLOAT64 = "FLOAT64"
    ENUM = "Enum"
    DBPOS = "Dbpos"  # Double bit position
    QUALITY = "Quality"
    TIMESTAMP = "Timestamp"
    VIS_STRING_32 = "VisString32"
    VIS_STRING_64 = "VisString64"
    VIS_STRING_255 = "VisString255"
    UNICODE_STRING_255 = "UnicodeString255"
    OCTET_STRING_64 = "OctetString64"
    ANALOGUE_VALUE = "AnalogueValue"
    UNIT = "Unit"
    CMV = "CMV"  # Complex Measured Value


class FunctionalConstraint(Enum):
    """功能约束 (Functional Constraint)"""
    ST = "ST"  # Status
    MX = "MX"  # Measured values
    SP = "SP"  # Setpoint
    SV = "SV"  # Substituted values
    CF = "CF"  # Configuration
    DC = "DC"  # Description
    SG = "SG"  # Setting group
    SE = "SE"  # Setting group editable
    SR = "SR"  # Service response
    OR = "OR"  # Operate received
    BL = "BL"  # Blocking
    EX = "EX"  # Extended definition
    CO = "CO"  # Control


class TriggerOption(IntEnum):
    """触发选项"""
    DATA_CHANGE = 1
    QUALITY_CHANGE = 2
    DATA_UPDATE = 4
    INTEGRITY = 8
    GENERAL_INTERROGATION = 16


class Quality(IntEnum):
    """质量标志"""
    GOOD = 0
    INVALID = 1
    RESERVED = 2
    QUESTIONABLE = 3
    
    # 详细位
    OVERFLOW = 0x0004
    OUT_OF_RANGE = 0x0008
    BAD_REFERENCE = 0x0010
    OSCILLATORY = 0x0020
    FAILURE = 0x0040
    OLD_DATA = 0x0080
    INCONSISTENT = 0x0100
    INACCURATE = 0x0200
    SOURCE_SUBSTITUTED = 0x0400
    TEST = 0x0800
    OPERATOR_BLOCKED = 0x1000


class ControlModel(IntEnum):
    """控制模型"""
    STATUS_ONLY = 0
    DIRECT_WITH_NORMAL_SECURITY = 1
    SBO_WITH_NORMAL_SECURITY = 2
    DIRECT_WITH_ENHANCED_SECURITY = 3
    SBO_WITH_ENHANCED_SECURITY = 4


class DbPos(IntEnum):
    """双位位置"""
    INTERMEDIATE = 0
    OFF = 1
    ON = 2
    BAD_STATE = 3


# ============================================================================
# 数据属性 (Data Attribute)
# ============================================================================

@dataclass
class DataAttribute:
    """
    数据属性 - IEC61850数据模型最底层元素
    
    Attributes:
        name: 属性名称
        data_type: 数据类型
        value: 当前值
        fc: 功能约束
        trigger_options: 触发选项
        quality: 质量标志
        timestamp: 时间戳
    """
    name: str
    data_type: DataType
    value: Any = None
    fc: FunctionalConstraint = FunctionalConstraint.ST
    trigger_options: int = TriggerOption.DATA_CHANGE | TriggerOption.QUALITY_CHANGE
    quality: Quality = Quality.GOOD
    timestamp: Optional[datetime] = None
    
    # 内部字段
    _id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    _parent: Optional[DataObject] = field(default=None, repr=False)
    _callbacks: List[Callable] = field(default_factory=list, repr=False)
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        self._convert_value()
    
    def _convert_value(self):
        """根据数据类型转换值"""
        if self.value is None:
            return
            
        try:
            if self.data_type == DataType.BOOLEAN:
                self.value = bool(self.value)
            elif self.data_type in (DataType.INT8, DataType.INT16, DataType.INT32, 
                                     DataType.INT64, DataType.INT8U, DataType.INT16U,
                                     DataType.INT32U, DataType.ENUM, DataType.DBPOS,
                                     DataType.QUALITY):
                self.value = int(self.value)
            elif self.data_type in (DataType.FLOAT32, DataType.FLOAT64, 
                                     DataType.ANALOGUE_VALUE):
                self.value = float(self.value)
            elif self.data_type in (DataType.VIS_STRING_32, DataType.VIS_STRING_64,
                                     DataType.VIS_STRING_255, DataType.UNICODE_STRING_255,
                                     DataType.UNIT):
                self.value = str(self.value)
        except (ValueError, TypeError) as e:
            logger.warning(f"Value conversion failed for {self.name}: {e}")
    
    @property
    def reference(self) -> str:
        """获取完整引用路径"""
        if self._parent:
            return f"{self._parent.reference}.{self.name}"
        return self.name
    
    def set_value(self, value: Any, update_timestamp: bool = True) -> bool:
        """
        设置属性值
        
        Args:
            value: 新值
            update_timestamp: 是否更新时间戳
            
        Returns:
            是否成功设置
        """
        old_value = self.value
        self.value = value
        self._convert_value()
        
        if update_timestamp:
            self.timestamp = datetime.now()
        
        # 触发回调
        if old_value != self.value:
            for callback in self._callbacks:
                try:
                    callback(self, old_value, self.value)
                except Exception as e:
                    logger.error(f"Callback error: {e}")
        
        return True
    
    def add_callback(self, callback: Callable):
        """添加值变化回调"""
        self._callbacks.append(callback)
    
    def remove_callback(self, callback: Callable):
        """移除回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "name": self.name,
            "type": self.data_type.value,
            "value": self.value,
            "fc": self.fc.value,
            "quality": self.quality,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


# ============================================================================
# 数据对象 (Data Object)
# ============================================================================

@dataclass
class DataObject:
    """
    数据对象 - 包含多个数据属性的容器
    
    Attributes:
        name: 对象名称
        cdc: 公共数据类 (Common Data Class)
        description: 描述
        attributes: 数据属性列表
    """
    name: str
    cdc: str  # 如 SPS, DPS, MV, CMV, etc.
    description: str = ""
    attributes: Dict[str, DataAttribute] = field(default_factory=dict)
    
    _id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    _parent: Optional[LogicalNode] = field(default=None, repr=False)
    
    @property
    def reference(self) -> str:
        """获取完整引用路径"""
        if self._parent:
            return f"{self._parent.reference}.{self.name}"
        return self.name
    
    def add_attribute(self, attr: DataAttribute) -> DataAttribute:
        """添加数据属性"""
        attr._parent = self
        self.attributes[attr.name] = attr
        return attr
    
    def get_attribute(self, name: str) -> Optional[DataAttribute]:
        """获取数据属性"""
        return self.attributes.get(name)
    
    def get_value(self, attr_name: str = "stVal") -> Any:
        """获取指定属性的值"""
        attr = self.attributes.get(attr_name)
        return attr.value if attr else None
    
    def set_value(self, attr_name: str, value: Any) -> bool:
        """设置指定属性的值"""
        attr = self.attributes.get(attr_name)
        if attr:
            return attr.set_value(value)
        return False
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "name": self.name,
            "cdc": self.cdc,
            "description": self.description,
            "attributes": {k: v.to_dict() for k, v in self.attributes.items()},
        }


# ============================================================================
# 逻辑节点 (Logical Node)
# ============================================================================

@dataclass
class LogicalNode:
    """
    逻辑节点 - IEC61850功能单元
    
    常见类型:
    - LLN0: 逻辑节点零
    - LPHD: 物理设备信息
    - PTOC: 过流保护
    - XCBR: 断路器
    - MMXU: 测量单元
    """
    name: str
    ln_class: str  # LN类型，如 PTOC, XCBR
    description: str = ""
    data_objects: Dict[str, DataObject] = field(default_factory=dict)
    
    _id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    _parent: Optional[LogicalDevice] = field(default=None, repr=False)
    
    @property
    def reference(self) -> str:
        """获取完整引用路径"""
        if self._parent:
            return f"{self._parent.reference}/{self.name}"
        return self.name
    
    def add_data_object(self, do: DataObject) -> DataObject:
        """添加数据对象"""
        do._parent = self
        self.data_objects[do.name] = do
        return do
    
    def get_data_object(self, name: str) -> Optional[DataObject]:
        """获取数据对象"""
        return self.data_objects.get(name)
    
    def get_all_attributes(self) -> List[DataAttribute]:
        """获取所有数据属性"""
        attrs = []
        for do in self.data_objects.values():
            attrs.extend(do.attributes.values())
        return attrs
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "name": self.name,
            "class": self.ln_class,
            "description": self.description,
            "data_objects": {k: v.to_dict() for k, v in self.data_objects.items()},
        }


# ============================================================================
# 逻辑设备 (Logical Device)
# ============================================================================

@dataclass
class LogicalDevice:
    """
    逻辑设备 - 逻辑节点的容器
    
    Attributes:
        name: 设备名称 (如 PROT, MEAS)
        description: 描述
        logical_nodes: 逻辑节点字典
    """
    name: str
    description: str = ""
    logical_nodes: Dict[str, LogicalNode] = field(default_factory=dict)
    
    _id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    _parent: Optional[IED] = field(default=None, repr=False)
    
    @property
    def reference(self) -> str:
        """获取完整引用路径"""
        if self._parent:
            return f"{self._parent.name}{self.name}"
        return self.name
    
    def add_logical_node(self, ln: LogicalNode) -> LogicalNode:
        """添加逻辑节点"""
        ln._parent = self
        self.logical_nodes[ln.name] = ln
        return ln
    
    def get_logical_node(self, name: str) -> Optional[LogicalNode]:
        """获取逻辑节点"""
        return self.logical_nodes.get(name)
    
    def get_all_data_objects(self) -> List[DataObject]:
        """获取所有数据对象"""
        objects = []
        for ln in self.logical_nodes.values():
            objects.extend(ln.data_objects.values())
        return objects
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "logical_nodes": {k: v.to_dict() for k, v in self.logical_nodes.items()},
        }


# ============================================================================
# IED (Intelligent Electronic Device)
# ============================================================================

@dataclass 
class IED:
    """
    智能电子设备 - IEC61850数据模型顶层容器
    
    Attributes:
        name: IED名称
        manufacturer: 制造商
        model: 型号
        revision: 版本
        logical_devices: 逻辑设备字典
    """
    name: str
    manufacturer: str = "IEC61850Simulator"
    model: str = "VirtualIED"
    revision: str = "1.0"
    description: str = ""
    logical_devices: Dict[str, LogicalDevice] = field(default_factory=dict)
    
    _id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    
    def add_logical_device(self, ld: LogicalDevice) -> LogicalDevice:
        """添加逻辑设备"""
        ld._parent = self
        self.logical_devices[ld.name] = ld
        return ld
    
    def get_logical_device(self, name: str) -> Optional[LogicalDevice]:
        """获取逻辑设备"""
        return self.logical_devices.get(name)
    
    def get_data_attribute(self, reference: str) -> Optional[DataAttribute]:
        """
        通过引用路径获取数据属性
        
        Args:
            reference: 如 "IEDPROT/PTOC1.Op.general"
            
        Returns:
            数据属性对象
        """
        try:
            # 解析引用: IEDName + LD/LN.DO.DA
            # 移除IED名称前缀
            if reference.startswith(self.name):
                reference = reference[len(self.name):]
            
            # 分割 LD/LN 和 DO.DA
            if "/" in reference:
                ld_name, rest = reference.split("/", 1)
            else:
                return None
            
            # 分割 LN.DO.DA
            parts = rest.split(".")
            if len(parts) < 3:
                return None
            
            ln_name = parts[0]
            do_name = parts[1]
            da_name = ".".join(parts[2:])
            
            # 查找
            ld = self.logical_devices.get(ld_name)
            if not ld:
                return None
            
            ln = ld.logical_nodes.get(ln_name)
            if not ln:
                return None
            
            do = ln.data_objects.get(do_name)
            if not do:
                return None
            
            return do.attributes.get(da_name)
            
        except Exception as e:
            logger.error(f"Failed to parse reference '{reference}': {e}")
            return None
    
    def get_all_references(self) -> List[str]:
        """获取所有数据属性引用"""
        refs = []
        for ld in self.logical_devices.values():
            for ln in ld.logical_nodes.values():
                for do in ln.data_objects.values():
                    for da in do.attributes.values():
                        refs.append(da.reference)
        return refs
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "revision": self.revision,
            "description": self.description,
            "logical_devices": {k: v.to_dict() for k, v in self.logical_devices.items()},
        }


# ============================================================================
# 数据模型管理器
# ============================================================================

class DataModelManager:
    """
    数据模型管理器 - 负责加载、创建和管理IED数据模型
    """
    
    def __init__(self):
        self.ieds: Dict[str, IED] = {}
        self._data_type_map = {
            "BOOLEAN": DataType.BOOLEAN,
            "Enum": DataType.ENUM,
            "Dbpos": DataType.DBPOS,
            "Quality": DataType.QUALITY,
            "Timestamp": DataType.TIMESTAMP,
            "VisString255": DataType.VIS_STRING_255,
            "VisString64": DataType.VIS_STRING_64,
            "VisString32": DataType.VIS_STRING_32,
            "AnalogueValue": DataType.ANALOGUE_VALUE,
            "Unit": DataType.UNIT,
            "CMV": DataType.CMV,
            "INT32": DataType.INT32,
            "FLOAT32": DataType.FLOAT32,
        }
    
    def load_from_yaml(self, yaml_path: Union[str, Path]) -> Optional[IED]:
        """
        从YAML配置文件加载数据模型
        
        Args:
            yaml_path: YAML文件路径
            
        Returns:
            加载的IED对象
        """
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            return self._build_ied_from_config(config.get('ied', {}))
            
        except Exception as e:
            logger.error(f"Failed to load data model from {yaml_path}: {e}")
            return None
    
    def _build_ied_from_config(self, ied_config: Dict) -> IED:
        """从配置字典构建IED"""
        ied = IED(
            name=ied_config.get('name', 'SimulatedIED'),
            description=ied_config.get('description', ''),
        )
        
        for ld_config in ied_config.get('logical_devices', []):
            ld = LogicalDevice(
                name=ld_config.get('name', 'LD0'),
                description=ld_config.get('description', ''),
            )
            
            for ln_config in ld_config.get('logical_nodes', []):
                ln = LogicalNode(
                    name=ln_config.get('name', 'LN0'),
                    ln_class=ln_config.get('class', 'LLN0'),
                    description=ln_config.get('description', ''),
                )
                
                for do_config in ln_config.get('data_objects', []):
                    do = DataObject(
                        name=do_config.get('name', 'DO0'),
                        cdc=do_config.get('cdc', 'SPS'),
                        description=do_config.get('description', ''),
                    )
                    
                    for da_config in do_config.get('data_attributes', []):
                        data_type = self._data_type_map.get(
                            da_config.get('type', 'BOOLEAN'),
                            DataType.BOOLEAN
                        )
                        da = DataAttribute(
                            name=da_config.get('name', 'val'),
                            data_type=data_type,
                            value=da_config.get('value'),
                        )
                        do.add_attribute(da)
                    
                    ln.add_data_object(do)
                
                ld.add_logical_node(ln)
            
            ied.add_logical_device(ld)
        
        self.ieds[ied.name] = ied
        logger.info(f"Loaded IED: {ied.name} with {len(ied.logical_devices)} logical devices")
        return ied
    
    def create_default_ied(self, name: str = "SimulatedIED") -> IED:
        """
        创建默认IED数据模型
        
        Args:
            name: IED名称
            
        Returns:
            新创建的IED对象
        """
        ied = IED(name=name, description="Default simulated IED")
        
        # 创建保护逻辑设备
        prot_ld = LogicalDevice(name="PROT", description="Protection LD")
        
        # LLN0
        lln0 = LogicalNode(name="LLN0", ln_class="LLN0", description="Logical Node Zero")
        
        mod_do = DataObject(name="Mod", cdc="ENC", description="Mode")
        mod_do.add_attribute(DataAttribute("stVal", DataType.ENUM, value=1))
        mod_do.add_attribute(DataAttribute("q", DataType.QUALITY, value=0))
        mod_do.add_attribute(DataAttribute("t", DataType.TIMESTAMP))
        lln0.add_data_object(mod_do)
        
        beh_do = DataObject(name="Beh", cdc="ENS", description="Behaviour")
        beh_do.add_attribute(DataAttribute("stVal", DataType.ENUM, value=1))
        beh_do.add_attribute(DataAttribute("q", DataType.QUALITY, value=0))
        lln0.add_data_object(beh_do)
        
        prot_ld.add_logical_node(lln0)
        
        # PTOC1 - 过流保护
        ptoc1 = LogicalNode(name="PTOC1", ln_class="PTOC", description="Overcurrent Protection")
        
        ptoc_mod = DataObject(name="Mod", cdc="ENC", description="Mode")
        ptoc_mod.add_attribute(DataAttribute("stVal", DataType.ENUM, value=1))
        ptoc1.add_data_object(ptoc_mod)
        
        op_do = DataObject(name="Op", cdc="ACT", description="Operate")
        op_do.add_attribute(DataAttribute("general", DataType.BOOLEAN, value=False))
        op_do.add_attribute(DataAttribute("phsA", DataType.BOOLEAN, value=False))
        op_do.add_attribute(DataAttribute("phsB", DataType.BOOLEAN, value=False))
        op_do.add_attribute(DataAttribute("phsC", DataType.BOOLEAN, value=False))
        op_do.add_attribute(DataAttribute("q", DataType.QUALITY, value=0))
        op_do.add_attribute(DataAttribute("t", DataType.TIMESTAMP))
        ptoc1.add_data_object(op_do)
        
        prot_ld.add_logical_node(ptoc1)
        
        # XCBR1 - 断路器
        xcbr1 = LogicalNode(name="XCBR1", ln_class="XCBR", description="Circuit Breaker")
        
        pos_do = DataObject(name="Pos", cdc="DPC", description="Position")
        pos_do.add_attribute(DataAttribute("stVal", DataType.DBPOS, value=DbPos.ON))
        pos_do.add_attribute(DataAttribute("q", DataType.QUALITY, value=0))
        pos_do.add_attribute(DataAttribute("t", DataType.TIMESTAMP))
        pos_do.add_attribute(DataAttribute("ctlModel", DataType.ENUM, value=ControlModel.DIRECT_WITH_NORMAL_SECURITY))
        xcbr1.add_data_object(pos_do)
        
        prot_ld.add_logical_node(xcbr1)
        
        ied.add_logical_device(prot_ld)
        
        # 创建测量逻辑设备
        meas_ld = LogicalDevice(name="MEAS", description="Measurement LD")
        
        # MMXU1 - 测量单元
        mmxu1 = LogicalNode(name="MMXU1", ln_class="MMXU", description="Measurement Unit")
        
        totw_do = DataObject(name="TotW", cdc="MV", description="Total Active Power")
        totw_do.add_attribute(DataAttribute("mag", DataType.ANALOGUE_VALUE, value=1000.0, fc=FunctionalConstraint.MX))
        totw_do.add_attribute(DataAttribute("q", DataType.QUALITY, value=0))
        totw_do.add_attribute(DataAttribute("t", DataType.TIMESTAMP))
        mmxu1.add_data_object(totw_do)
        
        hz_do = DataObject(name="Hz", cdc="MV", description="Frequency")
        hz_do.add_attribute(DataAttribute("mag", DataType.ANALOGUE_VALUE, value=50.0, fc=FunctionalConstraint.MX))
        hz_do.add_attribute(DataAttribute("q", DataType.QUALITY, value=0))
        hz_do.add_attribute(DataAttribute("t", DataType.TIMESTAMP))
        mmxu1.add_data_object(hz_do)
        
        meas_ld.add_logical_node(mmxu1)
        ied.add_logical_device(meas_ld)
        
        self.ieds[ied.name] = ied
        logger.info(f"Created default IED: {ied.name}")
        return ied
    
    def get_ied(self, name: str) -> Optional[IED]:
        """获取IED"""
        return self.ieds.get(name)
    
    def remove_ied(self, name: str) -> bool:
        """移除IED"""
        if name in self.ieds:
            del self.ieds[name]
            return True
        return False
    
    def export_to_yaml(self, ied: IED, output_path: Union[str, Path]) -> bool:
        """导出IED配置到YAML文件"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                yaml.dump({"ied": ied.to_dict()}, f, 
                         allow_unicode=True, default_flow_style=False)
            logger.info(f"Exported IED {ied.name} to {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to export IED: {e}")
            return False
