"""
Pytest 配置和共享 fixtures
===========================

提供测试中使用的共享配置和 fixtures
"""

import os
import sys
from pathlib import Path

import pytest

# 添加项目源代码路径到 sys.path
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))


# ============================================================================
# Pytest 配置钩子
# ============================================================================

def pytest_configure(config):
    """Pytest 配置钩子"""
    # 注册自定义标记
    config.addinivalue_line("markers", "unit: 单元测试")
    config.addinivalue_line("markers", "integration: 集成测试")
    config.addinivalue_line("markers", "slow: 慢速测试")


def pytest_collection_modifyitems(config, items):
    """修改测试项"""
    # 自动标记测试
    for item in items:
        # 如果测试在 test_integration_*.py 文件中，标记为 integration
        if "integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)
        # 默认标记为 unit
        elif not list(item.iter_markers(name="integration")):
            item.add_marker(pytest.mark.unit)


# ============================================================================
# 会话级 Fixtures
# ============================================================================

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """设置测试环境"""
    # 设置测试环境变量
    os.environ["IEC61850_TEST_MODE"] = "1"
    
    yield
    
    # 清理
    if "IEC61850_TEST_MODE" in os.environ:
        del os.environ["IEC61850_TEST_MODE"]


@pytest.fixture(scope="session")
def test_data_dir():
    """测试数据目录"""
    data_dir = Path(__file__).parent / "test_data"
    data_dir.mkdir(exist_ok=True)
    return data_dir


# ============================================================================
# 模块级 Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def temp_config_dir(tmp_path_factory):
    """临时配置目录"""
    return tmp_path_factory.mktemp("config")


# ============================================================================
# 函数级 Fixtures
# ============================================================================

@pytest.fixture
def clean_environment(monkeypatch):
    """清理环境变量"""
    # 保存原始环境变量
    original_env = os.environ.copy()
    
    yield
    
    # 恢复环境变量
    os.environ.clear()
    os.environ.update(original_env)


# ============================================================================
# 自动使用的 Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def reset_loggers():
    """在每个测试后重置 loggers"""
    import logging
    
    yield
    
    # 清理所有 handlers
    for logger_name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.setLevel(logging.NOTSET)
