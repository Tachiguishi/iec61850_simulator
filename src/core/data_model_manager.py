"""
Data Model Manager for IEC61850 Simulator
"""

from ctypes import Union
from re import U
from .data_model import IED, DataType, LogicalDevice, LogicalNode, DataObject, DataAttribute, FunctionalConstraint, DbPos, ControlModel
from typing import Dict, Optional, List
from loguru import logger
from pathlib import Path


class DataModelManager:
	"""
	数据模型管理器 - 负责加载、创建和管理IED数据模型
	"""
	
	def __init__(self):
		self.ieds: Dict[str, IED] = {}
		
	def load_from_scd(self, scd_path: Union[str, Path]) -> List[IED]:
		"""
		从SCD文件加载数据模型
		
		Args:
			scd_path: SCD文件路径
		"""
		from .scd_parser import SCDParser
		
		parser = SCDParser()
		loaded_ieds = parser.parse(scd_path)
		
		for ied in loaded_ieds:
			self.ieds[ied.name] = ied
			logger.info(f"Loaded IED: {ied.name}")
		
		return loaded_ieds

	
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
		magAttribute = DataAttribute("mag", DataType.STRUCT, fc=FunctionalConstraint.MX)
		magAttribute.add_sub_attribute(DataAttribute("f", DataType.FLOAT32, value=1.10))
		totw_do.add_attribute(magAttribute)
		totw_do.add_attribute(DataAttribute("q", DataType.QUALITY, value=0))
		totw_do.add_attribute(DataAttribute("t", DataType.TIMESTAMP))
		mmxu1.add_data_object(totw_do)
		
		hz_do = DataObject(name="Hz", cdc="MV", description="Frequency")
		magAttribute = DataAttribute("mag", DataType.STRUCT, fc=FunctionalConstraint.MX)
		magAttribute.add_sub_attribute(DataAttribute("f", DataType.FLOAT32, value=2.20))
		hz_do.add_attribute(magAttribute)
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
