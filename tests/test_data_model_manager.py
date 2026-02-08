"""
Data model manager Tests
"""

from __future__ import annotations
from core.data_model_manager import DataModelManager

import json

"""
获取测试数据文件路径
"""
def get_test_data_path(filename: str) -> str:
	import os
	return os.path.join(os.path.dirname(__file__), "test_data", filename)

def get_test_output_path(filename: str) -> str:
	import os
	return os.path.join(os.path.dirname(__file__), "../iec61850/build/tests", filename)


def test_default_model_creation():
	"""测试默认数据模型的创建"""
	manager = DataModelManager()
	ied = manager.create_default_ied()
	assert ied is not None
	assert len(ied.get_logical_devices()) > 0
	# write ied.to_dict() to file
	with open(get_test_output_path("default_ied.json"), "w") as f:
		json.dump(ied.to_dict(), f, indent=2)


def test_load_from_report_goose_cid():
	"""测试从test_data/report_goose.cid加载数据模型"""
	manager = DataModelManager()
	ieds = manager.load_from_scd(get_test_data_path("report_goose.cid"))
	assert len(ieds) == 1
	with open(get_test_output_path("report_goose_ied.json"), "w") as f:
		json.dump(ieds[0].to_dict(), f, indent=2)


def test_load_from_setting_group_cid():
	"""测试从test_data/setting_group.cid加载数据模型"""
	manager = DataModelManager()
	ieds = manager.load_from_scd(get_test_data_path("setting_group.cid"))
	assert len(ieds) == 1
	with open(get_test_output_path("setting_group_ied.json"), "w") as f:
		json.dump(ieds[0].to_dict(), f, indent=2)


def test_load_from_control_cid():
	"""测试从test_data/control.cid加载数据模型"""
	manager = DataModelManager()
	ieds = manager.load_from_scd(get_test_data_path("control.cid"))
	assert len(ieds) == 1
	with open(get_test_output_path("control_ied.json"), "w") as f:
		json.dump(ieds[0].to_dict(), f, indent=2)
