"""
IEC61850 SCD Parser Module
==========================

用于解析和处理IEC61850 SCD文件的模块。

该模块提供了读取、验证和转换SCD文件的功能，支持IEC61850标准的各种数据模型和配置选项。
基于lxml库实现XML解析，确保高效和可靠的文件处理。

主要功能:
- 读取SCD文件并构建内部数据模型
- 验证SCD文件的结构和内容
- 提供API以便其他模块访问和操作SCD数据

基于IEC 61850-6标准
"""

from ctypes import Union
from xml.etree import ElementTree as ET
from pathlib import Path
from typing import List, Optional

from .data_model import IED, AccessPoint, LogicalDevice, LogicalNode, DataObject, DataAttribute, DataType, FunctionalConstraint
from loguru import logger

class SCDParser:
	def __init__(self):
		self._root = None
		self._dataTypeTemplate_element = None
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
			"Struct": DataType.STRUCT,
		}

	def parse(self, scd_path: Union[str, Path]) -> List[IED]:
		"""
		从 SCD (Substation Configuration Description) 文件加载数据模型
		
		支持带有或不带 XML 命名空间的 SCD 文件
		
		Args:
			scd_path: SCD 文件路径
			
		Returns:
			加载的 IED 对象列表
		"""
		try:
			tree = ET.parse(scd_path)
			root = tree.getroot()
			
			loaded_ieds = []
			self._dataTypeTemplate_element = self._find_element(root, 'DataTypeTemplates')

			# 使用通配符方式查找 IED 元素，忽略命名空间
			for ied_elem in root.findall('./{*}IED'):
				ied = self._parse_ied_from_scd(ied_elem)
				if ied:
					loaded_ieds.append(ied)
					logger.info(f"Loaded IED from SCD: {ied.name}")
			
			return loaded_ieds
			
		except Exception as e:
			logger.error(f"Failed to load SCD file {scd_path}: {e}")
			return []
	
	def _parse_ied_from_scd(self, ied_elem: ET.Element,) -> Optional[IED]:
		"""从 SCD XML 元素解析 IED"""
		try:
			ied_name = ied_elem.get('name', 'Unknown')
			manufacturer = ied_elem.get('manufacturer', 'Unknown')
			model = ied_elem.get('type', '')
			desc = ied_elem.get('desc', '')
			version = ied_elem.get('configVersion', '0.0.0')
			
			ied = IED(
				name=ied_name,
				manufacturer=manufacturer,
				description=desc,
				model=model,
				revision=version
			)
			
			# 查找 AccessPoint（忽略命名空间）
			for ap_elem in self._findall_elements(ied_elem, 'AccessPoint'):
				access_point_name = ap_elem.get('name', 'AP1')
				access_point = AccessPoint(
					name=access_point_name,
					description=''
				)
				ied.add_access_point(access_point)

				# 在 AccessPoint 中查找 Server
				server_elem = self._find_element(ap_elem, 'Server')
				if server_elem is not None:
					# 解析 LogicalDevice
					for ld_elem in self._findall_elements(server_elem, 'LDevice'):
						ld = self._parse_logical_device_from_scd(ld_elem, ied_name)
						if ld:
							access_point.add_logical_device(ld)
			
			return ied
			
		except Exception as e:
			logger.error(f"Failed to parse IED: {e}")
			return None
	
	def _parse_logical_device_from_scd(self, ld_elem: ET.Element, ied_name: str) -> Optional[LogicalDevice]:
		"""从 SCD XML 元素解析 LogicalDevice"""
		try:
			ld_inst = ld_elem.get('inst', 'LD0')
			ld_desc = ld_elem.get('desc', '')
			
			ld = LogicalDevice(
				name=ld_inst,
				description=ld_desc
			)

			# 处理 LN0 (特殊的逻辑节点)
			ln0_elem = self._find_element(ld_elem, 'LN0')
			if ln0_elem is not None:
				ln0 = self._parse_logical_node_from_scd(ln0_elem, ied_name, is_ln0=True)
				if ln0:
					ld.add_logical_node(ln0)
			
			# 解析 LogicalNode（忽略命名空间）
			for ln_elem in self._findall_elements(ld_elem, 'LN'):
				ln = self._parse_logical_node_from_scd(ln_elem, ied_name, is_ln0=False)
				if ln:
					ld.add_logical_node(ln)
			
			return ld
			
		except Exception as e:
			logger.error(f"Failed to parse LogicalDevice: {e}")
			return None
	
	def _parse_logical_node_from_scd(self, ln_elem: ET.Element, ied_name: str,
									is_ln0: bool = False) -> Optional[LogicalNode]:
		"""从 SCD XML 元素解析 LogicalNode"""
		try:
			if is_ln0:
				prefix = ''
				ln_class = 'LLN0'
				ln_inst = ''
			else:
				prefix = ln_elem.get('prefix', '')
				ln_class = ln_elem.get('lnClass', 'UNKN')
				ln_inst = ln_elem.get('inst', '')
			
			ln_desc = ln_elem.get('desc', '')
			ln_type = ln_elem.get('lnType', '')
			
			ln = LogicalNode(
				prefix=prefix,
				ln_class=ln_class,
				ln_inst=ln_inst,
				name=f"{prefix}{ln_class}{ln_inst}",
				description=ln_desc,
				ln_type=ln_type
			)
			
			# 根据 lnType 查找 DataTypeTemplates 中的定义（忽略命名空间）
			if ln_type:
				ln_type_def = self._find_element_by_id(self._dataTypeTemplate_element, 'LNodeType', ln_type)
				if ln_type_def is not None:
					# 解析 DO (Data Object)
					for do_elem in self._findall_elements(ln_type_def, 'DO'):
						do = self._parse_data_object_from_scd(do_elem)
						if do:
							ln.add_data_object(do)
			
			return ln
			
		except Exception as e:
			logger.error(f"Failed to parse LogicalNode: {e}")
			return None
	
	def _parse_data_object_from_scd(self, do_elem: ET.Element) -> Optional[DataObject]:
		"""从 SCD XML 元素解析 DataObject"""
		try:
			do_name = do_elem.get('name', 'DO')
			do_type = do_elem.get('type', '')
			
			# 查找 DOType 定义（忽略命名空间）
			do_type_def = self._find_element_by_id(self._dataTypeTemplate_element, 'DOType', do_type)
			if do_type_def is None:
				return None
			
			cdc = do_type_def.get('cdc', 'UNKNOWN')
			
			do = DataObject(
				name=do_name,
				cdc=cdc,
				description=''
			)

			# 解析 SDO (Sub Data Object)（忽略命名空间）
			for sdo_elem in self._findall_elements(do_type_def, 'SDO'):
				sdo = self._parse_data_object_from_scd(sdo_elem)
				if sdo:
					do.add_attribute(sdo)
			
			# 解析 DA (Data Attribute)（忽略命名空间）
			for da_elem in self._findall_elements(do_type_def, 'DA'):
				da = self._parse_data_type(da_elem)
				if da:
					do.add_attribute(da)
			
			return do
			
		except Exception as e:
			logger.error(f"Failed to parse DataObject: {e}")
			return None
	
	def _parse_data_type(self, da_elem: ET.Element) -> Optional[DataAttribute]:
		"""从 SCD XML 元素解析 DataAttribute"""
		try:
			da_name = da_elem.get('name', 'DA')
			da_fc = da_elem.get('fc', '')
			da_btype = da_elem.get('bType', 'BOOLEAN')
			da_type = da_elem.get('type', '')
			
			# 映射基本类型
			data_type = self._data_type_map.get(da_btype, DataType.BOOLEAN)
			
			# 映射功能约束
			fc_map = {
				'ST': FunctionalConstraint.ST,
				'MX': FunctionalConstraint.MX,
				'SP': FunctionalConstraint.SP,
				'SV': FunctionalConstraint.SV,
				'CF': FunctionalConstraint.CF,
				'DC': FunctionalConstraint.DC,
				'CO': FunctionalConstraint.CO,
			}
			fc = fc_map.get(da_fc, FunctionalConstraint.DEFAULT)
			
			da = DataAttribute(
				name=da_name,
				data_type=data_type,
				fc=fc,
				value=None
			)
			
			# 如果有 type 属性，说明是结构体类型，需要解析子属性（忽略命名空间）
			if da_type:
				da_type_def = self._find_element_by_id(self._dataTypeTemplate_element, 'DAType', da_type)
				if da_type_def is not None:
					for bda_elem in self._findall_elements(da_type_def, 'BDA'):
						sub_da = self._parse_data_attribute(fc, bda_elem)
						if sub_da:
							da.add_sub_attribute(sub_da)
			
			return da
			
		except Exception as e:
			logger.error(f"Failed to parse DataAttribute: {e}")
			return None
	

	def _parse_data_attribute(self, fc: FunctionalConstraint, bda_elem: ET.Element) -> Optional[DataAttribute]:
		"""从 SCD XML 元素解析 BDA (Basic Data Attribute)"""
		try:
			bda_name = bda_elem.get('name', 'BDA')
			bda_btype = bda_elem.get('bType', 'BOOLEAN')
			bda_type = bda_elem.get('type', '')
			
			# 映射基本类型
			data_type = self._data_type_map.get(bda_btype, DataType.BOOLEAN)
			
			bda = DataAttribute(
				name=bda_name,
				data_type=data_type,
				fc=fc,
				value=None
			)
			
			# 如果有 type 属性，说明是结构体类型，需要解析子属性（忽略命名空间）
			if bda_type:
				bda_type_def = self._find_element_by_id(self._dataTypeTemplate_element, 'DAType', bda_type)
				if bda_type_def is not None:
					for sub_bda_elem in self._findall_elements(bda_type_def, 'BDA'):
						sub_bda = self._parse_data_attribute(fc, sub_bda_elem)
						if sub_bda:
							bda.add_sub_attribute(sub_bda)
			
			return bda
		except Exception as e:
			logger.error(f"Failed to parse DataAttribute: {e}")
			return None

	def _find_element(self, parent: ET.Element, local_name: str) -> Optional[ET.Element]:
		"""
		在忽略命名空间的情况下查找子元素
		
		Args:
			parent: 父元素
			local_name: 元素本地名称
			
		Returns:
			找到的元素或 None
		"""
		# 尝试直接查找
		elem = parent.find(local_name)
		if elem is not None:
			return elem
		
		# 使用通配符查找
		elem = parent.find(f'{{*}}{local_name}')
		if elem is not None:
			return elem
		
		return None
	
	def _findall_elements(self, parent: ET.Element, local_name: str) -> List[ET.Element]:
		"""
		在忽略命名空间的情况下查找所有子元素
		
		Args:
			parent: 父元素
			local_name: 元素本地名称
			
		Returns:
			找到的元素列表
		"""
		# 使用通配符查找
		elements = parent.findall(f'{{*}}{local_name}')
		if not elements:
			# 如果没有命名空间的元素，尝试直接查找
			elements = parent.findall(local_name)
		return elements
	
	def _find_element_by_id(self, parent: ET.Element, tag_name: str, attr_id: str) -> Optional[ET.Element]:
		"""
		在忽略命名空间的情况下按 ID 属性查找元素
		
		Args:
			parent: 父元素
			tag_name: 标签名称
			attr_id: ID 属性值
			
		Returns:
			找到的元素或 None
		"""
		# 构造通配符路径，避免 f-string 的语法问题
		elements = parent.findall(f'./{{*}}{tag_name}')
		for elem in elements:
			if elem.get('id') == attr_id:
				return elem
		
		# 尝试不使用命名空间的方式
		elements = parent.findall(f"./{tag_name}")
		for elem in elements:
			if elem.get('id') == attr_id:
				return elem
		
		return None