"""
Data model manager Tests
"""

from __future__ import annotations
from core.data_model_manager import DataModelManager

def test_default_model_creation():
	"""测试默认数据模型的创建"""
	manager = DataModelManager()
	ied = manager.create_default_ied()
	assert ied is not None
	assert len(ied.get_logical_devices()) > 0
	print("ied", ied.to_dict())
