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

from sys import prefix
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from typing import Any, Callable, Dict, List, Optional, Union

from loguru import logger


# ============================================================================
# 基础类
# ============================================================================

@dataclass
class IEC61850Element:
	"""
	IEC61850 数据模型基类
	
	为 DataAttribute, DataObject, LogicalNode 提供公共属性和方法
	"""
	name: str
	description: str = ""
	
	_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
	_parent: Optional['IEC61850Element'] = field(default=None, repr=False)
	
	@property
	def reference(self) -> str:
		"""获取完整引用路径"""
		if self._parent:
			separator = self._get_separator()
			return f"{self._parent.reference}{separator}{self.name}"
		return self.name
	
	def _get_separator(self) -> str:
		"""获取路径分隔符（子类可重写）"""
		return "."
	
	def to_dict(self) -> Dict:
		"""转换为字典（子类应重写）"""
		return {
			"name": self.name,
			"description": self.description,
		}


# ============================================================================
# 基础枚举类型
# ============================================================================

class DataType(Enum):
	"""IEC61850基本数据类型"""
	UNKNOWN = "Unknown"
	STRUCT = "Struct"
	BOOLEAN = "BOOLEAN"
	INT8 = "INT8"
	INT16 = "INT16"
	INT24 = "INT24"
	INT32 = "INT32"
	INT64 = "INT64"
	INT128 = "INT128"
	INT8U = "INT8U"
	INT16U = "INT16U"
	INT24U = "INT24U"
	INT32U = "INT32U"
	FLOAT32 = "FLOAT32"
	FLOAT64 = "FLOAT64"
	ENUM = "Enum"
	DBPOS = "Dbpos"  # Double bit position
	TCMD = "Tcmd"  # Trip command
	QUALITY = "Quality"
	TIMESTAMP = "Timestamp"
	VIS_STRING_32 = "VisString32"
	VIS_STRING_64 = "VisString64"
	VIS_STRING_129 = "VisString129"
	VIS_STRING_255 = "VisString255"
	UNICODE_STRING_255 = "Unicode255"
	OCTET_STRING_64 = "Octet64"
	ENTRY_TIME = "EntryTime"
	CHECK = "Check"
	OBJECT_REF = "ObjRef"
	CURRENCY = "Currency"
	PHYSICAL_ADDRESS = "PhyComAddr"
	TRIGGER_OPTIONS = "TrgOps"
	OPTION_FIELD = "OptFlds"
	SV_OPTION_FIELD = "SvOptFlds"
	
	@classmethod
	def from_string(cls, value: str, default: Optional['DataType'] = None) -> Optional['DataType']:
		"""
		通过字符串获取对应的枚举值
		
		支持通过枚举名称或枚举值进行查找（不区分大小写）
		
		Args:
			value: 字符串值，可以是枚举名称（如 "BOOLEAN"）或枚举值（如 "BOOLEAN"）
			default: 找不到时返回的默认值，默认为 None
			
		Returns:
			对应的 DataType 枚举，如果找不到则返回 default
			
		Examples:
			>>> DataType.from_string("BOOLEAN")
			<DataType.BOOLEAN: 'BOOLEAN'>
			>>> DataType.from_string("boolean")
			<DataType.BOOLEAN: 'BOOLEAN'>
			>>> DataType.from_string("INT32")
			<DataType.INT32: 'INT32'>
			>>> DataType.from_string("VisString64")
			<DataType.VIS_STRING_64: 'VisString64'>
			>>> DataType.from_string("invalid")
			None
			>>> DataType.from_string("invalid", DataType.UNKNOWN)
			<DataType.UNKNOWN: 'Unknown'>
		"""
		if not value:
			return default
		
		value_upper = value.upper()

		# 通过枚举值匹配（不区分大小写）
		for member in cls:
			if member.value.upper() == value_upper:
				return member
		
		return default


class FunctionalConstraint(Enum):
	"""功能约束 (Functional Constraint)"""
	DEFAULT = ""
	ST = "ST"  # Status
	MX = "MX"  # Measured values
	SP = "SP"  # Setting Parameters
	SV = "SV"  # Substitution
	CF = "CF"  # Configuration
	DC = "DC"  # Description
	SG = "SG"  # Setting group
	SE = "SE"  # Setting group editable
	SR = "SR"  # Service response
	OR = "OR"  # Operate received
	BL = "BL"  # Blocking
	EX = "EX"  # Extended definition
	CO = "CO"  # Control

	@classmethod
	def from_string(cls, value: str, default: Optional['FunctionalConstraint'] = None) -> Optional['FunctionalConstraint']:
		"""
		通过字符串获取对应的枚举值
		
		支持通过枚举名称或枚举值进行查找（不区分大小写）
		
		Args:
			value: 字符串值，可以是枚举名称（如 "ST"）或枚举值(如 "ST")
			default: 找不到时返回的默认值，默认为 None
			
		Returns:
			对应的 FunctionalConstraint 枚举，如果找不到则返回 default
		"""
		if not value:
			return default
		
		value_upper = value.upper()

		# 通过枚举值匹配（不区分大小写）
		for member in cls:
			if member.value.upper() == value_upper:
				return member
		
		return default


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
class DataAttribute(IEC61850Element):
	"""
	数据属性 - IEC61850数据模型元素，可以是基础类型或结构体
	
	Attributes:
		name: 属性名称
		data_type: 数据类型（基础类型或结构体类型）
		value: 当前值（仅用于基础类型）
		format_value: 格式化值（仅用于枚举值的描述）
		fc: 功能约束
		trigger_options: 触发选项
		quality: 质量标志
		timestamp: 时间戳
		attributes: 子属性字典（用于结构体类型）
	"""
	data_type: DataType = DataType.BOOLEAN
	value: Any = None
	format_value: str = ""
	fc: FunctionalConstraint = FunctionalConstraint.ST
	trigger_options: int = TriggerOption.DATA_CHANGE | TriggerOption.QUALITY_CHANGE
	quality: Quality = Quality.GOOD
	timestamp: Optional[datetime] = None
	attributes: Dict[str, 'DataAttribute'] = field(default_factory=dict)
	
	# 内部字段
	_callbacks: List[Callable] = field(default_factory=list, repr=False)
	
	def __post_init__(self):
		if self.timestamp is None:
			self.timestamp = datetime.now()
		self._convert_value()
	
	def _convert_value(self):
		"""根据数据类型转换值（仅用于基础类型）"""
		# 如果有子属性，说明是结构体类型，不需要转换值
		if self.attributes:
			return
			
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
	
	def add_sub_attribute(self, attr: 'DataAttribute') -> 'DataAttribute':
		"""添加子属性（用于结构体类型）"""
		attr._parent = self
		self.attributes[attr.name] = attr
		return attr
	
	def get_sub_attribute(self, name: str) -> Optional['DataAttribute']:
		"""获取子属性"""
		return self.attributes.get(name)
	
	def is_struct(self) -> bool:
		"""判断是否为结构体类型"""
		return len(self.attributes) > 0
	
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
		result = {
			"name": self.name,
			"type": self.data_type.value,
			"fc": self.fc.value,
		}
		
		# 如果是结构体类型，序列化子属性
		if self.attributes:
			result["attributes"] = {k: v.to_dict() for k, v in self.attributes.items()}
		else:
			# 基础类型才有 value, quality, timestamp
			result["value"] = self.value
			result["quality"] = self.quality
			result["timestamp"] = self.timestamp.isoformat() if self.timestamp else None
		
		return result


# ============================================================================
# 数据对象 (Data Object)
# ============================================================================

@dataclass
class DataObject(IEC61850Element):
	"""
	数据对象 - 包含多个数据属性或子数据对象的容器
	
	Attributes:
		name: 对象名称
		cdc: 公共数据类 (Common Data Class)
		description: 描述
		attributes: 数据属性或子数据对象字典
	"""
	cdc: str = ""  # 如 SPS, DPS, MV, CMV, etc.
	attributes: Dict[str, Union['DataAttribute', 'DataObject']] = field(default_factory=dict)
	
	def add_attribute(self, attr: Union['DataAttribute', 'DataObject']) -> Union['DataAttribute', 'DataObject']:
		"""添加数据属性或子数据对象"""
		attr._parent = self
		self.attributes[attr.name] = attr
		return attr
	
	def get_attribute(self, name: str) -> Optional[Union['DataAttribute', 'DataObject']]:
		"""获取数据属性或子数据对象"""
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
class LogicalNode(IEC61850Element):
	"""
	逻辑节点 - IEC61850功能单元
	
	常见类型:
	- LLN0: 逻辑节点零
	- LPHD: 物理设备信息
	- PTOC: 过流保护
	- XCBR: 断路器
	- MMXU: 测量单元
	"""
	prefix: str = ""  # 前缀，如 "WarnPTOC1" 中的 "Warn"
	ln_class: str = ""  # LN类型，如 PTOC, XCBR
	ln_inst: str = ""  # 实例标识符，如 "1" 在 "PTOC1"
	ln_type: str = ""  # LN类型标识符
	data_objects: Dict[str, DataObject] = field(default_factory=dict)
	data_sets: Dict[str, 'DataSet'] = field(default_factory=dict)  # 数据集
	report_controls: Dict[str, 'ReportControl'] = field(default_factory=dict)  # 报告控制块
	gse_controls: Dict[str, 'GSEControl'] = field(default_factory=dict)  # GSE控制块
	smv_controls: Dict[str, 'SampledValueControl'] = field(default_factory=dict)  # 采样值控制块
	log_controls: Dict[str, 'LogControl'] = field(default_factory=dict)  # 日志控制块
	
	def _get_separator(self) -> str:
		"""LogicalNode 使用 '/' 作为分隔符"""
		return "/"
	
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
			"data_sets": {k: v.to_dict() for k, v in self.data_sets.items()},
			"report_controls": {k: v.to_dict() for k, v in self.report_controls.items()},
			"gse_controls": {k: v.to_dict() for k, v in self.gse_controls.items()},
			"smv_controls": {k: v.to_dict() for k, v in self.smv_controls.items()},
			"log_controls": {k: v.to_dict() for k, v in self.log_controls.items()},
		}


# ============================================================================
# 数据集和控制块 (DataSet and Control Blocks)
# ============================================================================

@dataclass
class DataSet(IEC61850Element):
	"""
	数据集 - 用于报告或采样值的相关数据属性集合
	
	Attributes:
		name: 数据集名称
		fcdas: FCDA (Functional Constrained Data Attribute) 列表
	"""
	fcdas: List[Dict[str, str]] = field(default_factory=list)  # FCDA列表，每个FCDA包含ldInst, lnClass, lnInst, doName, daName等
	
	def add_fcda(self, fcda_info: Dict[str, str]):
		"""添加 FCDA"""
		self.fcdas.append(fcda_info)

	def get_fcdaReferences(self) -> List[str]:
		"""获取 FCDA 的完整引用路径列表"""
		references = []
		for fcda in self.fcdas:
			prefix = fcda.get("prefix", "")
			ld_inst = fcda.get("ldInst", "")
			ln_class = fcda.get("lnClass", "")
			ln_inst = fcda.get("lnInst", "")
			do_name = fcda.get("doName", "")
			da_name = fcda.get("daName", "")
			ref = f"{ld_inst}/{prefix}{ln_class}{ln_inst}.{do_name}.{da_name}"
			references.append(ref)
		return references
	
	def to_dict(self) -> Dict:
		return {
			"name": self.name,
			"description": self.description,
			"fcdas": self.get_fcdaReferences(),
		}


@dataclass
class ReportControl(IEC61850Element):
	"""
	报告控制块 - 用于配置报告的生成和传输
	
	Attributes:
		name: 报告控制块名称
		dataset: 所关联的数据集名称
		rptid: 报告ID
		buf_time: 缓冲时间（ms）
		intg_pd: 完整性周期（ms）
		options: 报告选项（trigger, data_change, quality_change, buf_overflow, seq_num, time_stamp, reason_for_inclusion)
	"""
	buffered: bool = False  # 是否启用缓冲
	dataset: str = ""  # 关联的数据集名称
	rptid: str = ""  # 报告ID
	buf_time: int = 0  # 缓冲时间
	intg_pd: int = 0  # 完整性周期
	options: Dict[str, bool] = field(default_factory=dict)  # 报告选项
	
	def to_dict(self) -> Dict:
		return {
			"name": self.name,
			"description": self.description,
			"buffered": self.buffered,
			"dataset": self.dataset,
			"rptid": self.rptid,
			"buf_time": self.buf_time,
			"intg_pd": self.intg_pd,
			"options": self.options,
		}


@dataclass
class GSEControl(IEC61850Element):
	"""
	GSE 控制块 - 用于配置 Generic Substation Event (GSE) 的生成和传输
	
	Attributes:
		name: GSE控制块名称
		dataset: 所关联的数据集名称
		gocbname: GSE控制块名称
		timeAllowedtoLive: 允许存活时间
		"""
	dataset: str = ""  # 关联的数据集名称
	gocbname: str = ""  # GSE控制块名称
	time_allowed_to_live: int = 0  # 允许存活时间
	options: Dict[str, bool] = field(default_factory=dict)  # GSE选项
	
	def to_dict(self) -> Dict:
		return {
			"name": self.name,
			"description": self.description,
			"dataset": self.dataset,
			"gocbname": self.gocbname,
			"time_allowed_to_live": self.time_allowed_to_live,
			"options": self.options,
		}


@dataclass
class SampledValueControl(IEC61850Element):
	"""
	采样值控制块 - 用于配置采样值的生成和传输
	
	Attributes:
		name: 采样值控制块名称
		dataset: 所关联的数据集名称
		smvcbname: 采样值控制块名称
		smprate: 采样率
		smpmod: 采样模式
		"""
	dataset: str = ""  # 关联的数据集名称
	smvcbname: str = ""  # 采样值控制块名称
	smprate: int = 0  # 采样率
	smpmod: str = ""  # 采样模式（SmpPerPeriod, SmpPerSec）
	options: Dict[str, bool] = field(default_factory=dict)  # 采样值选项
	
	def to_dict(self) -> Dict:
		return {
			"name": self.name,
			"description": self.description,
			"dataset": self.dataset,
			"smvcbname": self.smvcbname,
			"smprate": self.smprate,
			"smpmod": self.smpmod,
			"options": self.options,
		}


@dataclass
class LogControl(IEC61850Element):
	"""
	日志控制块 - 用于配置日志的记录
	
	Attributes:
		name: 日志控制块名称
		dataset: 所关联的数据集名称
		logname: 日志名称
		logEna: 是否启用日志
		intgPd: 完整性周期
		"""
	dataset: str = ""  # 关联的数据集名称
	logname: str = ""  # 日志名称
	log_ena: bool = False  # 是否启用日志
	intg_pd: int = 0  # 完整性周期
	options: Dict[str, bool] = field(default_factory=dict)  # 日志选项
	
	def to_dict(self) -> Dict:
		return {
			"name": self.name,
			"description": self.description,
			"dataset": self.dataset,
			"logname": self.logname,
			"log_ena": self.log_ena,
			"intg_pd": self.intg_pd,
			"options": self.options,
		}




@dataclass
class LogicalDevice(IEC61850Element):
	"""
	逻辑设备 - 逻辑节点的容器
	
	Attributes:
		name: 设备名称 (如 PROT, MEAS)
		description: 描述
		logical_nodes: 逻辑节点字典
	"""
	logical_nodes: Dict[str, LogicalNode] = field(default_factory=dict)
	
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


@dataclass
class AccessPoint(IEC61850Element):
	"""
	访问点 - IED的网络访问点容器
	
	Attributes:
		name: 访问点名称
		logical_devices: 逻辑设备字典
	"""
	logical_devices: Dict[str, LogicalDevice] = field(default_factory=dict)
	
	def add_logical_device(self, ld: LogicalDevice) -> LogicalDevice:
		"""添加逻辑设备"""
		ld._parent = self
		self.logical_devices[ld.name] = ld
		return ld
	
	def get_logical_device(self, name: str) -> Optional[LogicalDevice]:
		"""获取逻辑设备"""
		return self.logical_devices.get(name)
	
	def to_dict(self) -> Dict:
		"""转换为字典"""
		return {
			"name": self.name,
			"description": self.description,
			"logical_devices": {k: v.to_dict() for k, v in self.logical_devices.items()},
		}

# ============================================================================
# IED (Intelligent Electronic Device)
# ============================================================================

@dataclass 
class IED(IEC61850Element):
	"""
	智能电子设备 - IEC61850数据模型顶层容器
	
	Attributes:
		name: IED名称
		manufacturer: 制造商
		model: 型号
		revision: 版本
		access_points: 访问点字典
	"""
	manufacturer: str = "IEC61850Simulator"
	model: str = "VirtualIED"
	revision: str = "1.0"
	access_points: Dict[str, AccessPoint] = field(default_factory=dict)
	
	def add_access_point(self, ap: AccessPoint) -> AccessPoint:
		"""添加访问点"""
		ap._parent = self
		self.access_points[ap.name] = ap
		return ap
	
	def get_access_point(self, name: str) -> Optional[AccessPoint]:
		"""获取访问点"""
		return self.access_points.get(name)
	
	def get_logical_devices(self) -> List[LogicalDevice]:
		"""获取所有逻辑设备"""
		devices = []
		for ap in self.access_points.values():
			devices.extend(ap.logical_devices.values())
		return devices
	
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
			for ap in self.access_points.values():
				if not ap:
					continue
				
				ld = ap.logical_devices.get(ld_name)
				if not ld:
					continue
				
				ln = ld.logical_nodes.get(ln_name)
				if not ln:
					continue
				
				do = ln.data_objects.get(do_name)
				if not do:
					continue
			
				return do.attributes.get(da_name)
			
			return None
			
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
			"logical_devices": {ld.name: ld.to_dict() for ld in self.get_logical_devices()},
		}
