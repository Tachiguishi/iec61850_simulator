"""
IEC61850 client proxy communicating with C++ backend via UDS.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from ipc.uds_client import IPCError, UDSMessageClient

class ClientState(Enum):
    """Client lifecycle state."""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    DISCONNECTING = auto()
    ERROR = auto()


@dataclass
class ClientConfig:
    """Client configuration."""
    timeout_ms: int = 5000
    retry_count: int = 3
    retry_interval_ms: int = 1000
    polling_interval_ms: int = 1000
    enable_reporting: bool = True
    auto_reconnect: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClientConfig":
        return cls(
            timeout_ms=data.get("timeout_ms", 5000),
            retry_count=data.get("retry_count", 3),
            retry_interval_ms=data.get("retry_interval_ms", 1000),
            polling_interval_ms=data.get("polling_interval_ms", 1000),
            enable_reporting=data.get("enable_reporting", True),
            auto_reconnect=data.get("auto_reconnect", True),
        )


@dataclass
class DataValue:
    """Data value returned from backend."""
    reference: str
    value: Any
    quality: int = 0
    timestamp: Optional[datetime] = None
    error: Optional[str] = None


class IEC61850ClientProxy:
    """
    Client proxy for GUI. Delegates IEC61850 operations to C++ backend via IPC.
    
    单例模式：确保全局只有一个客户端代理实例，避免重复连接。
    """

    _instance: Optional['IEC61850ClientProxy'] = None
    _initialized: bool = False

    def __new__(cls, config: Optional[ClientConfig] = None, socket_path: str = "", timeout_ms: int = 3000):
        """单例模式：确保只创建一个实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config: Optional[ClientConfig] = None, socket_path: str = "", timeout_ms: int = 3000):
        # 避免重复初始化
        if self._initialized:
            return
        
        self.config = config or ClientConfig()
        self.state = ClientState.DISCONNECTED
        self.instance_id: Optional[str] = None  # 实例ID，用于多实例支持

        # 将毫秒转换为秒传递给 UDSMessageClient
        self._ipc = UDSMessageClient(socket_path or "/tmp/iec61850_simulator.sock", timeout_ms / 1000.0)

        self._state_callbacks: List[Callable[[ClientState], None]] = []
        self._data_callbacks: List[Callable[[str, Any], None]] = []
        self._log_callbacks: List[Callable[[str, str], None]] = []
        
        self._initialized = True

    # =====================================================================
    # Callback registration
    # =====================================================================

    def on_state_change(self, callback: Callable[[ClientState], None]) -> None:
        self._state_callbacks.append(callback)

    def on_data_change(self, callback: Callable[[str, Any], None]) -> None:
        self._data_callbacks.append(callback)

    def on_log(self, callback: Callable[[str, str], None]) -> None:
        self._log_callbacks.append(callback)

    # =====================================================================
    # Connection
    # =====================================================================

    def connect(self, host: str, port: int = 102, name: str = "") -> bool:
        if self.state == ClientState.CONNECTED:
            self._log("warning", "Already connected")
            return False

        self._set_state(ClientState.CONNECTING)
        try:
            payload = {
                "instance_id": self.instance_id,
                "host": host,
                "port": port,
                "name": name,
                "config": asdict(self.config),
            }
            self._ipc.request("client.connect", payload)
            self._set_state(ClientState.CONNECTED)
            self._log("info", f"Connected to {host}:{port}")
            return True
        except IPCError as exc:
            self._set_state(ClientState.ERROR)
            self._log("error", f"Connect failed: {exc}")
            return False

    def disconnect(self) -> bool:
        if self.state == ClientState.DISCONNECTED:
            return True

        self._set_state(ClientState.DISCONNECTING)
        try:
            self._ipc.request("client.disconnect", {"instance_id": self.instance_id})
            self._set_state(ClientState.DISCONNECTED)
            self._log("info", "Disconnected")
            return True
        except IPCError as exc:
            self._set_state(ClientState.ERROR)
            self._log("error", f"Disconnect failed: {exc}")
            return False

    def is_connected(self) -> bool:
        return self.state == ClientState.CONNECTED

    # =====================================================================
    # Data operations
    # =====================================================================

    def browse_data_model(self) -> Optional[Dict[str, Any]]:
        try:
            response = self._ipc.request("client.browse", {"instance_id": self.instance_id})
            return response.data.get("model")
        except IPCError as exc:
            self._log("error", f"Browse failed: {exc}")
            return None

    def read_value(self, reference: str) -> Optional[DataValue]:
        try:
            response = self._ipc.request("client.read", {"instance_id": self.instance_id, "reference": reference})
            info = response.data.get("value", {})
            return self._to_data_value(reference, info)
        except IPCError as exc:
            self._log("error", f"Read failed: {exc}")
            return DataValue(reference=reference, value=None, error=str(exc))

    def read_values(self, references: List[str]) -> Dict[str, DataValue]:
        if not references:
            return {}
        try:
            response = self._ipc.request("client.read_batch", {"instance_id": self.instance_id, "references": references})
            values = response.data.get("values", {})
            return {ref: self._to_data_value(ref, info) for ref, info in values.items()}
        except IPCError as exc:
            self._log("error", f"Read batch failed: {exc}")
            return {}

    def write_value(self, reference: str, value: Any) -> bool:
        try:
            response = self._ipc.request("client.write", {"instance_id": self.instance_id, "reference": reference, "value": value})
            return bool(response.data.get("success", False))
        except IPCError as exc:
            self._log("error", f"Write failed: {exc}")
            return False

    # =====================================================================
    # Internal helpers
    # =====================================================================

    def _set_state(self, state: ClientState) -> None:
        self.state = state
        for callback in self._state_callbacks:
            callback(state)

    def _log(self, level: str, message: str) -> None:
        for callback in self._log_callbacks:
            callback(level, message)
        if level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)
        else:
            logger.info(message)

    @staticmethod
    def _to_data_value(reference: str, info: Dict[str, Any]) -> DataValue:
        timestamp = info.get("timestamp")
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp)
            except ValueError:
                timestamp = None
        return DataValue(
            reference=reference,
            value=info.get("value"),
            quality=int(info.get("quality", 0)),
            timestamp=timestamp,
            error=info.get("error"),
        )
