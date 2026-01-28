"""
Data Model Unit Tests
=====================

测试 IEC61850 数据模型的核心功能
"""

import sys
from datetime import datetime
from pathlib import Path

import pytest

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.data_model import (
    DataType, FunctionalConstraint, Quality, TriggerOption,
    DataAttribute, DataObject, LogicalNode, LogicalDevice, AccessPoint, IED
)


# ============================================================================
# DataType 测试
# ============================================================================

class TestDataType:
    """测试 DataType 枚举"""
    
    def test_from_string_by_name_exact(self):
        """测试通过精确枚举名称获取"""
        assert DataType.from_string("BOOLEAN") == DataType.BOOLEAN
        assert DataType.from_string("INT32") == DataType.INT32
        assert DataType.from_string("FLOAT64") == DataType.FLOAT64
        assert DataType.from_string("QUALITY") == DataType.QUALITY
    
    def test_from_string_by_name_case_insensitive(self):
        """测试不区分大小写的枚举名称"""
        assert DataType.from_string("boolean") == DataType.BOOLEAN
        assert DataType.from_string("Boolean") == DataType.BOOLEAN
        assert DataType.from_string("BOOLEAN") == DataType.BOOLEAN
        assert DataType.from_string("int32") == DataType.INT32
        assert DataType.from_string("float64") == DataType.FLOAT64
    
    def test_from_string_by_value(self):
        """测试通过枚举值获取"""
        assert DataType.from_string("BOOLEAN") == DataType.BOOLEAN
        assert DataType.from_string("INT32") == DataType.INT32
        assert DataType.from_string("VisString64") == DataType.VIS_STRING_64
        assert DataType.from_string("Unknown") == DataType.UNKNOWN
    
    def test_from_string_by_value_case_insensitive(self):
        """测试不区分大小写的枚举值"""
        assert DataType.from_string("visstring64") == DataType.VIS_STRING_64
        assert DataType.from_string("VISSTRING64") == DataType.VIS_STRING_64
        assert DataType.from_string("unknown") == DataType.UNKNOWN
    
    def test_from_string_invalid_returns_none(self):
        """测试无效字符串返回 None"""
        assert DataType.from_string("invalid") is None
        assert DataType.from_string("not_a_type") is None
        assert DataType.from_string("") is None
        assert DataType.from_string(None) is None
    
    def test_from_string_with_default(self):
        """测试使用默认值"""
        assert DataType.from_string("invalid", DataType.UNKNOWN) == DataType.UNKNOWN
        assert DataType.from_string("", DataType.BOOLEAN) == DataType.BOOLEAN
        assert DataType.from_string(None, DataType.INT32) == DataType.INT32
    
    def test_from_string_all_types(self):
        """测试所有数据类型都能被正确获取"""
        for dt in DataType:
            # 通过名称
            assert DataType.from_string(dt.name) == dt
            # 通过值
            assert DataType.from_string(dt.value) == dt


# ============================================================================
# DataAttribute 测试
# ============================================================================

class TestDataAttribute:
    """测试数据属性"""
    
    def test_create_simple_attribute(self):
        """测试创建简单属性"""
        attr = DataAttribute(
            name="stVal",
            data_type=DataType.BOOLEAN,
            value=True
        )
        assert attr.name == "stVal"
        assert attr.data_type == DataType.BOOLEAN
        assert attr.value is True
    
    def test_value_conversion(self):
        """测试值类型转换"""
        # Boolean
        attr = DataAttribute(name="test", data_type=DataType.BOOLEAN, value="1")
        assert attr.value is True
        
        # Integer
        attr = DataAttribute(name="test", data_type=DataType.INT32, value="123")
        assert attr.value == 123
        
        # Float
        attr = DataAttribute(name="test", data_type=DataType.FLOAT32, value="45.6")
        assert attr.value == 45.6
    
    def test_set_value(self):
        """测试设置值"""
        attr = DataAttribute(name="test", data_type=DataType.INT32, value=100)
        assert attr.set_value(200) is True
        assert attr.value == 200
    
    def test_value_change_callback(self):
        """测试值变化回调"""
        changes = []
        
        def callback(attr, old_val, new_val):
            changes.append((old_val, new_val))
        
        attr = DataAttribute(name="test", data_type=DataType.INT32, value=100)
        attr.add_callback(callback)
        attr.set_value(200)
        
        assert len(changes) == 1
        assert changes[0] == (100, 200)
    
    def test_struct_attribute(self):
        """测试结构体属性"""
        struct = DataAttribute(name="mag", data_type=DataType.STRUCT)
        
        # 添加子属性
        f = DataAttribute(name="f", data_type=DataType.FLOAT32, value=50.0)
        struct.add_sub_attribute(f)
        
        assert struct.is_struct() is True
        assert struct.get_sub_attribute("f") == f
    
    def test_to_dict(self):
        """测试转换为字典"""
        attr = DataAttribute(
            name="stVal",
            data_type=DataType.BOOLEAN,
            value=True,
            fc=FunctionalConstraint.ST
        )
        d = attr.to_dict()
        assert d["name"] == "stVal"
        assert d["type"] == "BOOLEAN"
        assert d["value"] is True


# ============================================================================
# DataObject 测试
# ============================================================================

class TestDataObject:
    """测试数据对象"""
    
    def test_create_data_object(self):
        """测试创建数据对象"""
        do = DataObject(name="Pos", cdc="DPC")
        assert do.name == "Pos"
        assert do.cdc == "DPC"
    
    def test_add_attribute(self):
        """测试添加属性"""
        do = DataObject(name="Pos", cdc="DPC")
        attr = DataAttribute(name="stVal", data_type=DataType.INT32, value=1)
        do.add_attribute(attr)
        
        assert "stVal" in do.attributes
        assert do.get_attribute("stVal") == attr
    
    def test_get_set_value(self):
        """测试获取和设置值"""
        do = DataObject(name="Pos", cdc="DPC")
        attr = DataAttribute(name="stVal", data_type=DataType.INT32, value=1)
        do.add_attribute(attr)
        
        assert do.get_value("stVal") == 1
        assert do.set_value("stVal", 2) is True
        assert do.get_value("stVal") == 2


# ============================================================================
# LogicalNode 测试
# ============================================================================

class TestLogicalNode:
    """测试逻辑节点"""
    
    def test_create_logical_node(self):
        """测试创建逻辑节点"""
        ln = LogicalNode(name="XCBR1", ln_class="XCBR")
        assert ln.name == "XCBR1"
        assert ln.ln_class == "XCBR"
    
    def test_add_data_object(self):
        """测试添加数据对象"""
        ln = LogicalNode(name="XCBR1", ln_class="XCBR")
        do = DataObject(name="Pos", cdc="DPC")
        ln.add_data_object(do)
        
        assert "Pos" in ln.data_objects
        assert ln.get_data_object("Pos") == do
    
    def test_reference_separator(self):
        """测试引用分隔符"""
        ln = LogicalNode(name="XCBR1", ln_class="XCBR")
        assert ln._get_separator() == "/"


# ============================================================================
# LogicalDevice 测试
# ============================================================================

class TestLogicalDevice:
    """测试逻辑设备"""
    
    def test_create_logical_device(self):
        """测试创建逻辑设备"""
        ld = LogicalDevice(name="PROT")
        assert ld.name == "PROT"
    
    def test_add_logical_node(self):
        """测试添加逻辑节点"""
        ld = LogicalDevice(name="PROT")
        ln = LogicalNode(name="XCBR1", ln_class="XCBR")
        ld.add_logical_node(ln)
        
        assert "XCBR1" in ld.logical_nodes
        assert ld.get_logical_node("XCBR1") == ln


# ============================================================================
# AccessPoint 测试
# ============================================================================

class TestAccessPoint:
    """测试访问点"""
    
    def test_create_access_point(self):
        """测试创建访问点"""
        ap = AccessPoint(name="AP1")
        assert ap.name == "AP1"
    
    def test_add_logical_device(self):
        """测试添加逻辑设备"""
        ap = AccessPoint(name="AP1")
        ld = LogicalDevice(name="PROT")
        ap.add_logical_device(ld)
        
        assert "PROT" in ap.logical_devices
        assert ap.get_logical_device("PROT") == ld


# ============================================================================
# IED 测试
# ============================================================================

class TestIED:
    """测试 IED"""
    
    def test_create_ied(self):
        """测试创建 IED"""
        ied = IED(
            name="TestIED",
            manufacturer="TestMfr",
            model="Model1",
            revision="1.0"
        )
        assert ied.name == "TestIED"
        assert ied.manufacturer == "TestMfr"
    
    def test_full_hierarchy(self):
        """测试完整层次结构"""
        # 创建 IED
        ied = IED(name="TestIED")
        
        # 添加访问点
        ap = AccessPoint(name="AP1")
        ied.add_access_point(ap)
        
        # 添加逻辑设备
        ld = LogicalDevice(name="PROT")
        ap.add_logical_device(ld)
        
        # 添加逻辑节点
        ln = LogicalNode(name="XCBR1", ln_class="XCBR")
        ld.add_logical_node(ln)
        
        # 添加数据对象
        do = DataObject(name="Pos", cdc="DPC")
        ln.add_data_object(do)
        
        # 添加属性
        attr = DataAttribute(
            name="stVal",
            data_type=DataType.INT32,
            value=1,
            fc=FunctionalConstraint.ST
        )
        do.add_attribute(attr)
        
        # 验证层次
        assert ap in ied.access_points.values()
        assert ld in ap.logical_devices.values()
        assert ln in ld.logical_nodes.values()
        assert do in ln.data_objects.values()
        assert attr in do.attributes.values()
    
    def test_get_data_attribute(self):
        """测试通过引用获取数据属性"""
        # 构建完整模型
        ied = IED(name="TestIED")
        ap = AccessPoint(name="AP1")
        ied.add_access_point(ap)
        ld = LogicalDevice(name="PROT")
        ap.add_logical_device(ld)
        ln = LogicalNode(name="XCBR1", ln_class="XCBR")
        ld.add_logical_node(ln)
        do = DataObject(name="Pos", cdc="DPC")
        ln.add_data_object(do)
        attr = DataAttribute(name="stVal", data_type=DataType.INT32, value=1)
        do.add_attribute(attr)
        
        # 通过引用获取
        result = ied.get_data_attribute("PROT/XCBR1.Pos.stVal")
        assert result == attr
    
    def test_get_data_attribute_invalid(self):
        """测试无效引用"""
        ied = IED(name="TestIED")
        assert ied.get_data_attribute("invalid/path") is None


# ============================================================================
# 集成测试
# ============================================================================

class TestIntegration:
    """集成测试"""
    
    def test_complete_model(self):
        """测试完整的数据模型"""
        # 创建完整的 IED 模型
        ied = IED(name="PROT_IED", manufacturer="TestMfr")
        ap = AccessPoint(name="SERVER")
        ied.add_access_point(ap)
        
        # 保护逻辑设备
        ld_prot = LogicalDevice(name="PROT")
        ap.add_logical_device(ld_prot)
        
        # 断路器逻辑节点
        ln_xcbr = LogicalNode(name="XCBR1", ln_class="XCBR")
        ld_prot.add_logical_node(ln_xcbr)
        
        # 位置数据对象
        do_pos = DataObject(name="Pos", cdc="DPC")
        ln_xcbr.add_data_object(do_pos)
        
        # 状态值属性
        attr_stval = DataAttribute(
            name="stVal",
            data_type=DataType.INT32,
            value=1,
            fc=FunctionalConstraint.ST
        )
        do_pos.add_attribute(attr_stval)
        
        # 质量属性
        attr_q = DataAttribute(
            name="q",
            data_type=DataType.QUALITY,
            value=Quality.GOOD,
            fc=FunctionalConstraint.ST
        )
        do_pos.add_attribute(attr_q)
        
        # 验证
        assert len(ied.access_points) == 1
        assert len(ap.logical_devices) == 1
        assert len(ld_prot.logical_nodes) == 1
        assert len(ln_xcbr.data_objects) == 1
        assert len(do_pos.attributes) == 2
        
        # 测试引用
        result = ied.get_data_attribute("PROT/XCBR1.Pos.stVal")
        assert result == attr_stval
        assert result.value == 1
        
        # 测试值修改
        result.set_value(2)
        assert ied.get_data_attribute("PROT/XCBR1.Pos.stVal").value == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
