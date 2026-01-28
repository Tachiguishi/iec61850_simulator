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
from typing import List, Optional, Any

from .data_model import (
	IED, AccessPoint, LogicalDevice, LogicalNode, DataObject, DataAttribute, 
	DataType, FunctionalConstraint, DataSet, ReportControl, GSEControl, 
	SampledValueControl, LogControl
)
from loguru import logger

class SCDParser:
	def __init__(self):
		self._root = None
		self._dataTypeTemplate_element = None

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
			
			# 解析 DOI (Data Object Instance) - 包含实例化描述和初始值
			for doi_elem in self._findall_elements(ln_elem, 'DOI'):
				self._apply_doi_to_data_object(doi_elem, ln)
			
			# 解析 DataSet
			for dataset_elem in self._findall_elements(ln_elem, 'DataSet'):
				ds = self._parse_data_set(dataset_elem)
				if ds:
					ln.data_sets[ds.name] = ds
			
			# 解析 ReportControl
			for rc_elem in self._findall_elements(ln_elem, 'ReportControl'):
				rc = self._parse_report_control(rc_elem)
				if rc:
					ln.report_controls[rc.name] = rc
			
			# 解析 GSEControl
			for gse_elem in self._findall_elements(ln_elem, 'GSEControl'):
				gse = self._parse_gse_control(gse_elem)
				if gse:
					ln.gse_controls[gse.name] = gse
			
			# 解析 SampledValueControl
			for smv_elem in self._findall_elements(ln_elem, 'SampledValueControl'):
				smv = self._parse_sampled_value_control(smv_elem)
				if smv:
					ln.smv_controls[smv.name] = smv
			
			# 解析 LogControl
			for log_elem in self._findall_elements(ln_elem, 'LogControl'):
				log = self._parse_log_control(log_elem)
				if log:
					ln.log_controls[log.name] = log
			
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
			da_btype = da_elem.get('bType', 'UNKNOWN')
			da_type = da_elem.get('type', '')
			
			# 映射基本类型
			data_type = DataType.from_string(da_btype, DataType.UNKNOWN)
			
			fc = FunctionalConstraint.from_string(da_fc, FunctionalConstraint.DEFAULT)
			
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
			bda_btype = bda_elem.get('bType', 'UNKNOWN')
			bda_type = bda_elem.get('type', '')
			
			# 映射基本类型
			data_type = DataType.from_string(bda_btype, DataType.UNKNOWN)
			
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
	
	def _apply_doi_to_data_object(self, doi_elem: ET.Element, ln: LogicalNode):
		"""
		应用 DOI (Data Object Instance) 到 LogicalNode 中的 DataObject
		
		DOI 包含实例化的描述和初始值
		
		Args:
			doi_elem: DOI XML 元素
			ln: LogicalNode 对象
		"""
		try:
			doi_name = doi_elem.get('name', '')
			if not doi_name:
				return
			
			# 查找对应的 DataObject
			do = ln.get_data_object(doi_name)
			if not do:
				logger.warning(f"DataObject {doi_name} not found in LogicalNode {ln.name}")
				return
			
			# 更新描述
			doi_desc = doi_elem.get('desc', '')
			if doi_desc:
				do.description = doi_desc
			
			# 处理 DAI (Data Attribute Instance)
			for dai_elem in self._findall_elements(doi_elem, 'DAI'):
				self._apply_dai_to_data_attribute(dai_elem, do)
			
			# 处理 SDI (Sub Data Instance) - 嵌套的数据对象实例
			for sdi_elem in self._findall_elements(doi_elem, 'SDI'):
				self._apply_sdi_to_data_attribute(sdi_elem, do)
				
		except Exception as e:
			logger.error(f"Failed to apply DOI: {e}")
	
	def _apply_dai_to_data_attribute(self, dai_elem: ET.Element, do: DataObject):
		"""
		应用 DAI (Data Attribute Instance) 到 DataObject 中的 DataAttribute
		
		DAI 包含数据属性的初始值
		
		Args:
			dai_elem: DAI XML 元素
			do: DataObject 对象
		"""
		try:
			dai_name = dai_elem.get('name', '')
			if not dai_name:
				return
			
			# 查找对应的 DataAttribute
			da = do.get_attribute(dai_name)
			if not da or not isinstance(da, DataAttribute):
				logger.debug(f"DataAttribute {dai_name} not found in DataObject {do.name}")
				return
			
			# 解析值 - 可能在 Val 子元素中
			val_elem = self._find_element(dai_elem, 'Val')
			if val_elem is not None and val_elem.text:
				# 设置初始值
				value_str = val_elem.text.strip()
				da.value = self._convert_value_by_type(value_str, da.data_type)
				logger.debug(f"Set value for {do.name}.{dai_name} = {da.value}")
			
			# 处理嵌套的 DAI（用于结构体类型）
			for sub_dai_elem in self._findall_elements(dai_elem, 'DAI'):
				# 对于结构体类型的属性，递归处理
				if da.attributes:
					self._apply_dai_to_sub_attribute(sub_dai_elem, da)
					
		except Exception as e:
			logger.error(f"Failed to apply DAI: {e}")
	
	def _apply_sdi_to_data_attribute(self, sdi_elem: ET.Element, do: DataObject):
		"""
		应用 SDI (Sub Data Instance) 到数据对象的子属性
		
		Args:
			sdi_elem: SDI XML 元素
			do: DataObject 对象
		"""
		try:
			sdi_name = sdi_elem.get('name', '')
			if not sdi_name:
				return
			
			# 查找对应的子属性（可能是 DataAttribute 或 DataObject）
			attr = do.get_attribute(sdi_name)
			if not attr:
				logger.debug(f"Attribute {sdi_name} not found in DataObject {do.name}")
				return
			
			# 如果是 DataAttribute 类型
			if isinstance(attr, DataAttribute):
				# 处理嵌套的 DAI
				for dai_elem in self._findall_elements(sdi_elem, 'DAI'):
					self._apply_dai_to_sub_attribute(dai_elem, attr)
				
				# 处理更深层的 SDI
				for sub_sdi_elem in self._findall_elements(sdi_elem, 'SDI'):
					self._apply_sdi_to_sub_attribute(sub_sdi_elem, attr)
					
		except Exception as e:
			logger.error(f"Failed to apply SDI: {e}")
	
	def _apply_dai_to_sub_attribute(self, dai_elem: ET.Element, da: DataAttribute):
		"""
		应用 DAI 到 DataAttribute 的子属性（用于结构体类型）
		
		Args:
			dai_elem: DAI XML 元素
			da: DataAttribute 对象
		"""
		try:
			dai_name = dai_elem.get('name', '')
			if not dai_name:
				return
			
			# 查找子属性
			sub_da = da.get_sub_attribute(dai_name)
			if not sub_da:
				logger.debug(f"Sub attribute {dai_name} not found in {da.name}")
				return
			
			# 解析值
			val_elem = self._find_element(dai_elem, 'Val')
			if val_elem is not None and val_elem.text:
				value_str = val_elem.text.strip()
				sub_da.value = self._convert_value_by_type(value_str, sub_da.data_type)
				logger.debug(f"Set value for {da.name}.{dai_name} = {sub_da.value}")
			
			# 递归处理更深层的 DAI
			for nested_dai_elem in self._findall_elements(dai_elem, 'DAI'):
				self._apply_dai_to_sub_attribute(nested_dai_elem, sub_da)
					
		except Exception as e:
			logger.error(f"Failed to apply DAI to sub attribute: {e}")

	def _apply_sdi_to_sub_attribute(self, sdi_elem: ET.Element, da: DataAttribute):
		"""
		应用 SDI 到 DataAttribute 的子属性
		
		Args:
			sdi_elem: SDI XML 元素
			da: DataAttribute 对象
		"""
		try:
			sdi_name = sdi_elem.get('name', '')
			if not sdi_name:
				return
			
			# 查找子属性
			sub_attr = da.get_sub_attribute(sdi_name)
			if not sub_attr:
				logger.debug(f"Sub attribute {sdi_name} not found in {da.name}")
				return
			
			# 处理嵌套的 DAI
			for dai_elem in self._findall_elements(sdi_elem, 'DAI'):
				self._apply_dai_to_sub_attribute(dai_elem, sub_attr)
			
			# 递归处理更深层的 SDI
			for sub_sdi_elem in self._findall_elements(sdi_elem, 'SDI'):
				self._apply_sdi_to_sub_attribute(sub_sdi_elem, sub_attr)
					
		except Exception as e:
			logger.error(f"Failed to apply SDI to sub attribute: {e}")
	
	def _convert_value_by_type(self, value_str: str, data_type: DataType) -> Any:
		"""
		根据数据类型转换字符串值
		
		Args:
			value_str: 值字符串
			data_type: 数据类型
			
		Returns:
			转换后的值
		"""
		try:
			if data_type == DataType.BOOLEAN:
				return value_str.lower() in ('true', '1', 'yes')
			elif data_type in (DataType.INT8, DataType.INT16, DataType.INT24, DataType.INT32,
							   DataType.INT64, DataType.INT8U, DataType.INT16U, DataType.INT24U,
							   DataType.INT32U, DataType.DBPOS, DataType.QUALITY):
				return int(value_str)
			elif data_type in (DataType.FLOAT32, DataType.FLOAT64):
				return float(value_str)
			else:
				# 字符串类型
				return value_str
		except (ValueError, TypeError) as e:
			logger.warning(f"Value conversion failed for '{value_str} to {data_type}': {e}")
			return value_str

	def _parse_data_set(self, dataset_elem: ET.Element) -> Optional[DataSet]:
		"""
		解析 DataSet 元素
		
		Args:
			dataset_elem: DataSet XML 元素
			
		Returns:
			DataSet 对象或 None
		"""
		try:
			ds_name = dataset_elem.get('name', '')
			if not ds_name:
				return None
			
			ds = DataSet(
				name=ds_name,
				description=dataset_elem.get('desc', '')
			)
			
			# 解析 FCDA (Functional Constrained Data Attribute)
			for fcda_elem in self._findall_elements(dataset_elem, 'FCDA'):
				fcda_info = {
					'prefix': fcda_elem.get('prefix', ''),
					'ldInst': fcda_elem.get('ldInst', ''),
					'lnClass': fcda_elem.get('lnClass', ''),
					'lnInst': fcda_elem.get('lnInst', ''),
					'doName': fcda_elem.get('doName', ''),
					'daName': fcda_elem.get('daName', ''),
					'fc': fcda_elem.get('fc', ''),
				}
				ds.add_fcda(fcda_info)
			
			return ds
			
		except Exception as e:
			logger.error(f"Failed to parse DataSet: {e}")
			return None
	
	def _parse_report_control(self, rc_elem: ET.Element) -> Optional[ReportControl]:
		"""
		解析 ReportControl 元素
		
		Args:
			rc_elem: ReportControl XML 元素
			
		Returns:
			ReportControl 对象或 None
		"""
		try:
			rc_name = rc_elem.get('name', '')
			if not rc_name:
				return None
			
			rc = ReportControl(
				name=rc_name,
				description=rc_elem.get('desc', ''),
				buffered=rc_elem.get('buffered', 'false').lower() == 'true',
				dataset=rc_elem.get('datSet', ''),
				rptid=rc_elem.get('rptID', ''),
				buf_time=int(rc_elem.get('bufTm', '0')),
				intg_pd=int(rc_elem.get('intgPd', '0')),
			)
			
			# 解析 RptEnabled 和其他选项
			rep_enabled_elem = self._find_element(rc_elem, 'RptEnabled')
			if rep_enabled_elem is not None:
				rc.options['rptEnabled'] = rep_enabled_elem.get('max', '1')
			
			# 解析 OptFields
			opt_fields_elem = self._find_element(rc_elem, 'OptFields')
			if opt_fields_elem is not None:
				rc.options['seqNum'] = opt_fields_elem.get('seqNum', 'false').lower() == 'true'
				rc.options['timeStamp'] = opt_fields_elem.get('timeStamp', 'false').lower() == 'true'
				rc.options['dataSet'] = opt_fields_elem.get('dataSet', 'false').lower() == 'true'
				rc.options['reasonForInclusion'] = opt_fields_elem.get('reasonForInclusion', 'false').lower() == 'true'
				rc.options['configRevision'] = opt_fields_elem.get('configRevision', 'false').lower() == 'true'
				rc.options['bufferOverflow'] = opt_fields_elem.get('bufOvfl', 'false').lower() == 'true'
			
			# 解析 TrgOps (触发选项)
			trg_ops_elem = self._find_element(rc_elem, 'TrgOps')
			if trg_ops_elem is not None:
				rc.options['dataChange'] = trg_ops_elem.get('dchg', 'false').lower() == 'true'
				rc.options['qualityChange'] = trg_ops_elem.get('qchg', 'false').lower() == 'true'
				rc.options['dataUpdate'] = trg_ops_elem.get('dupd', 'false').lower() == 'true'
				rc.options['integrityCheck'] = trg_ops_elem.get('period', 'false').lower() == 'true'
			
			return rc
			
		except Exception as e:
			logger.error(f"Failed to parse ReportControl: {e}")
			return None
	
	def _parse_gse_control(self, gse_elem: ET.Element) -> Optional[GSEControl]:
		"""
		解析 GSEControl 元素
		
		Args:
			gse_elem: GSEControl XML 元素
			
		Returns:
			GSEControl 对象或 None
		"""
		try:
			gse_name = gse_elem.get('name', '')
			if not gse_name:
				return None
			
			gse = GSEControl(
				name=gse_name,
				description=gse_elem.get('desc', ''),
				dataset=gse_elem.get('datSet', ''),
				gocbname=gse_elem.get('gocbName', ''),
				time_allowed_to_live=int(gse_elem.get('timeAllowedToLive', '0')),
			)
			
			# 解析 IEDName 和 ApName
			gse.options['iedName'] = gse_elem.get('iedName', '')
			gse.options['apName'] = gse_elem.get('apName', '')
			
			return gse
			
		except Exception as e:
			logger.error(f"Failed to parse GSEControl: {e}")
			return None
	
	def _parse_sampled_value_control(self, smv_elem: ET.Element) -> Optional[SampledValueControl]:
		"""
		解析 SampledValueControl 元素
		
		Args:
			smv_elem: SampledValueControl XML 元素
			
		Returns:
			SampledValueControl 对象或 None
		"""
		try:
			smv_name = smv_elem.get('name', '')
			if not smv_name:
				return None
			
			# 解析采样模式
			smpmod = smv_elem.get('smpMod', 'SmpPerPeriod')  # SmpPerPeriod 或 SmpPerSec
			
			smv = SampledValueControl(
				name=smv_name,
				description=smv_elem.get('desc', ''),
				dataset=smv_elem.get('datSet', ''),
				smvcbname=smv_elem.get('smvCBName', ''),
				smprate=int(smv_elem.get('smpRate', '0')),
				smpmod=smpmod,
			)
			
			# 解析 IEDName 和 ApName
			smv.options['iedName'] = smv_elem.get('iedName', '')
			smv.options['apName'] = smv_elem.get('apName', '')
			
			# 解析 OptFields
			opt_fields_elem = self._find_element(smv_elem, 'OptFields')
			if opt_fields_elem is not None:
				smv.options['sampleSync'] = opt_fields_elem.get('sampleSync', 'false').lower() == 'true'
				smv.options['sampleRate'] = opt_fields_elem.get('sampleRate', 'false').lower() == 'true'
				smv.options['security'] = opt_fields_elem.get('security', 'false').lower() == 'true'
				smv.options['timestamp'] = opt_fields_elem.get('timestamp', 'false').lower() == 'true'
				smv.options['syncSourceId'] = opt_fields_elem.get('syncSourceId', 'false').lower() == 'true'
			
			return smv
			
		except Exception as e:
			logger.error(f"Failed to parse SampledValueControl: {e}")
			return None
	
	def _parse_log_control(self, log_elem: ET.Element) -> Optional[LogControl]:
		"""
		解析 LogControl 元素
		
		Args:
			log_elem: LogControl XML 元素
			
		Returns:
			LogControl 对象或 None
		"""
		try:
			log_name = log_elem.get('name', '')
			if not log_name:
				return None
			
			# 解析 logEna - 是否启用日志
			log_ena_elem = self._find_element(log_elem, 'LogEna')
			log_ena = False
			if log_ena_elem is not None:
				log_ena = log_ena_elem.get('value', 'false').lower() == 'true'
			
			log = LogControl(
				name=log_name,
				description=log_elem.get('desc', ''),
				dataset=log_elem.get('datSet', ''),
				logname=log_elem.get('logName', ''),
				log_ena=log_ena,
				intg_pd=int(log_elem.get('intgPd', '0')),
			)
			
			# 解析 OptFields
			opt_fields_elem = self._find_element(log_elem, 'OptFields')
			if opt_fields_elem is not None:
				log.options['seqNum'] = opt_fields_elem.get('seqNum', 'false').lower() == 'true'
				log.options['timeStamp'] = opt_fields_elem.get('timeStamp', 'false').lower() == 'true'
				log.options['dataSet'] = opt_fields_elem.get('dataSet', 'false').lower() == 'true'
				log.options['reasonForInclusion'] = opt_fields_elem.get('reasonForInclusion', 'false').lower() == 'true'
				log.options['configRevision'] = opt_fields_elem.get('configRevision', 'false').lower() == 'true'
				log.options['bufferOverflow'] = opt_fields_elem.get('bufOvfl', 'false').lower() == 'true'
			
			# 解析 TrgOps (触发选项)
			trg_ops_elem = self._find_element(log_elem, 'TrgOps')
			if trg_ops_elem is not None:
				log.options['dataChange'] = trg_ops_elem.get('dchg', 'false').lower() == 'true'
				log.options['qualityChange'] = trg_ops_elem.get('qchg', 'false').lower() == 'true'
				log.options['dataUpdate'] = trg_ops_elem.get('dupd', 'false').lower() == 'true'
				log.options['integrityCheck'] = trg_ops_elem.get('period', 'false').lower() == 'true'
			
			return log
			
		except Exception as e:
			logger.error(f"Failed to parse LogControl: {e}")
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