# IEC61850 Simulator 测试文档

## 运行测试

### 运行所有测试

```bash
pytest
```

### 运行特定测试文件

```bash
pytest tests/test_iec61850_server.py
```

### 运行特定测试类

```bash
pytest tests/test_iec61850_server.py::TestServerLifecycle
```

### 运行特定测试函数

```bash
pytest tests/test_iec61850_server.py::TestServerLifecycle::test_start_server
```

### 详细输出

```bash
pytest -v
```

### 显示打印输出

```bash
pytest -s
```

### 生成覆盖率报告

```bash
pytest -v --cov=src --cov-report=html
```

然后在浏览器中打开 `htmlcov/index.html` 查看报告。

### 生成覆盖率终端报告

```bash
pytest --cov=src --cov-report=term-missing
```

## 测试组织

### TestServerConfig
测试服务器配置类的功能：
- 默认配置
- 自定义配置
- 从字典创建配置

### TestClientConnection
测试客户端连接类的功能：
- 客户端创建
- 哈希功能

### TestServerInitialization
测试服务器初始化：
- 默认初始化
- 自定义配置初始化

### TestIEDManagement
测试 IED 模型管理：
- 加载 IED
- 获取/设置数据值
- 无效引用处理

### TestServerLifecycle
测试服务器生命周期：
- 启动/停止服务器
- 重启服务器
- 运行状态检查
- 边界情况（重复启动、停止未运行等）

### TestDataTypeMapping
测试数据类型映射：
- 数据类型到 pyiec61850 类型的映射
- 功能约束映射

### TestCallbacks
测试回调机制：
- 状态变化回调
- 数据变化回调
- 日志回调
- 连接变化回调

### TestClientManagement
测试客户端管理：
- 客户端列表
- 客户端跟踪

### TestServerStatus
测试服务器状态：
- 获取停止状态
- 获取运行状态

### TestErrorHandling
测试错误处理：
- 缺少 pyiec61850 库
- 启动失败
- 其他异常情况

### TestDataUpdate
测试数据更新：
- 更新服务器值
- 数据仿真更新

### TestIntegration
集成测试：
- 完整生命周期测试
- 多个回调测试

## Mock 策略

由于 IEC61850 服务器依赖于 `pyiec61850` 库，测试中使用了 `unittest.mock` 来模拟该库的行为：

- `mock_pyiec61850` fixture 提供了完整的 pyiec61850 模块 mock
- 所有常量（数据类型、功能约束等）都被模拟
- 服务器创建、启动、停止等操作都被模拟
- 数据模型创建相关的函数都被模拟

这种方法允许在没有真实 IEC61850 库的情况下运行测试。

## 测试覆盖率目标

- 代码覆盖率：> 80%
- 分支覆盖率：> 70%
- 核心功能覆盖率：100%

## 持续集成

测试应该在每次提交时自动运行。可以配置 CI/CD 流程：

### GitHub Actions 示例

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install -e ".[test]"
      - name: Run tests
        run: |
          pytest --cov=src --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

## 添加新测试

当添加新功能时，请：

1. 在相应的测试类中添加测试方法
2. 如果需要新的测试类，遵循现有的命名约定
3. 确保新测试使用适当的 fixtures
4. 验证测试覆盖率没有下降

## 调试技巧

### 进入调试器

```python
import pytest

def test_something():
    # ...
    pytest.set_trace()  # 断点
```

### 只运行失败的测试

```bash
pytest --lf
```

### 并行运行测试（需要 pytest-xdist）

```bash
pip install pytest-xdist
pytest -n auto
```

## 注意事项

1. **Mock 的重要性**：由于使用了 mock，测试验证的是代码逻辑而非真实的 IEC61850 通信
2. **集成测试**：建议创建单独的集成测试来测试真实的 pyiec61850 库
3. **异步操作**：服务器使用线程，某些测试可能需要适当的等待或同步
4. **资源清理**：fixtures 确保服务器在测试后正确清理

## 故障排除

### 测试挂起
如果测试挂起，可能是线程没有正确停止。检查：
- `_stop_event` 是否正确设置
- 线程 join 的超时设置

### Import 错误
确保：
- 已安装所有依赖
- Python 路径正确设置
- 使用虚拟环境

### Mock 失败
如果 mock 不工作：
- 检查 patch 的路径是否正确
- 验证 mock 对象的属性和方法设置


[project.optional-dependencies]
test = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "pytest-mock>=3.11.0",
    "pytest-xdist>=3.3.0",
]
dev = [
    "iec61850-simulator[test]",
    "black>=23.0.0",
    "flake8>=6.0.0",
    "mypy>=1.4.0",
]