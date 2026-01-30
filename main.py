#!/usr/bin/env python3
"""
IEC61850 Simulator
==================

基于PyQt6的IEC61850协议仿真器

支持两种模式:
- 服务端模式: 仿真IED设备，提供MMS服务
- 客户端模式: 连接到IED设备，读写数据点

用法:
    python main.py              # 启动GUI
    python main.py --server     # 直接启动服务端模式
    python main.py --client     # 直接启动客户端模式
    python main.py --headless   # 无界面服务器模式
"""

import sys
import os
import argparse
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from loguru import logger


def setup_logging(log_file: str = None, level: str = "DEBUG"):
    """配置日志"""
    # 移除默认处理器
    logger.remove()
    
    # 控制台输出
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=level,
        colorize=True
    )
    
    # 文件输出
    if log_file:
        log_path = PROJECT_ROOT / "logs"
        log_path.mkdir(exist_ok=True)
        
        logger.add(
            log_path / log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {module}:{function}:{line} - {message}",
            level=level,
            rotation="10 MB",
            retention="7 days",
            compression="zip"
        )


def run_gui(initial_mode: str = None):
    """运行GUI程序"""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    
    # 高DPI支持
    # Qt6中默认启用高DPI缩放
    
    app = QApplication(sys.argv)
    app.setApplicationName("IEC61850 Simulator")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("IEC61850Simulator")
    
    # 设置样式
    app.setStyle("Fusion")
    
    # 创建主窗口
    from gui.main_window import MainWindow
    window = MainWindow()
    
    # 如果指定了初始模式
    if initial_mode == "server":
        window.server_mode_btn.setChecked(True)
        window._on_mode_changed(window.server_mode_btn)
    elif initial_mode == "client":
        window.client_mode_btn.setChecked(True)
        window._on_mode_changed(window.client_mode_btn)
    
    window.show()
    
    logger.info("IEC61850 Simulator GUI started")
    
    return app.exec()


def run_headless_server(host: str = "0.0.0.0", port: int = 102):
    """运行无界面服务器"""
    import signal
    import time
    
    from server.server_proxy import ServerConfig
    from core.data_model import DataModelManager
    
    logger.info(f"Starting headless server on {host}:{port}")
    
    # 创建服务器
    config = ServerConfig(
        ip_address=host,
        port=port,
        enable_random_values=True,
        enable_reporting=True,
    )
    
    
    # 信号处理
    running = True
    
    def signal_handler(sig, frame):
        nonlocal running
        logger.info("Received shutdown signal")
        running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    
    return 0


def run_client_cli(host: str, port: int = 102):
    """运行TUI客户端"""
    
    return 0


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="IEC61850 Simulator - A PyQt6-based IEC61850 protocol simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                     # Start GUI
  python main.py --server            # Start in server mode
  python main.py --client            # Start in client mode  
  python main.py --headless          # Run headless server
  python main.py --headless -p 8102  # Run headless server on port 8102
  python main.py --cli -H 127.0.0.1  # Connect CLI client to localhost
        """
    )
    
    # 模式选择
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--server", "-s",
        action="store_true",
        help="Start in server mode"
    )
    mode_group.add_argument(
        "--client", "-c",
        action="store_true",
        help="Start in client mode"
    )
    mode_group.add_argument(
        "--headless",
        action="store_true",
        help="Run headless server (no GUI)"
    )
    mode_group.add_argument(
        "--cli",
        action="store_true",
        help="Run command-line client"
    )
    
    # 网络选项
    parser.add_argument(
        "-H", "--host",
        default="0.0.0.0",
        help="Host address (default: 0.0.0.0 for server, 127.0.0.1 for client)"
    )
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=102,
        help="Port number (default: 102)"
    )
    
    # 日志选项
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Log level (default: INFO)"
    )
    parser.add_argument(
        "--log-file",
        default="simulator.log",
        help="Log file name (default: simulator.log)"
    )
    
    # 版本
    parser.add_argument(
        "--version", "-v",
        action="version",
        version="IEC61850 Simulator v1.0.0"
    )
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(args.log_file, args.log_level)
    
    # 运行
    if args.headless:
        return run_headless_server(args.host, args.port)
    
    elif args.cli:
        host = args.host if args.host != "0.0.0.0" else "127.0.0.1"
        return run_client_cli(host, args.port)
    
    else:
        # GUI模式
        initial_mode = None
        if args.server:
            initial_mode = "server"
        elif args.client:
            initial_mode = "client"
        
        return run_gui(initial_mode)


if __name__ == "__main__":
    sys.exit(main())
