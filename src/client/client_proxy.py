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
    """

    def __init__(self, config: Optional[ClientConfig], socket_path: str, timeout_ms: int = 3000):
        self.config = config or ClientConfig()
        self.state = ClientState.DISCONNECTED

        self._ipc = UDSMessageClient(socket_path, timeout_ms)

        self._state_callbacks: List[Callable[[ClientState], None]] = []
        self._data_callbacks: List[Callable[[str, Any], None]] = []
        self._log_callbacks: List[Callable[[str, str], None]] = []

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
            self._ipc.request("client.disconnect", {})
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
            response = self._ipc.request("client.browse", {})
            return response.data.get("model")
        except IPCError as exc:
            self._log("error", f"Browse failed: {exc}")
            return None

    def read_value(self, reference: str) -> Optional[DataValue]:
        try:
            response = self._ipc.request("client.read", {"reference": reference})
            info = response.data.get("value", {})
            return self._to_data_value(reference, info)
        except IPCError as exc:
            self._log("error", f"Read failed: {exc}")
            return DataValue(reference=reference, value=None, error=str(exc))

    def read_values(self, references: List[str]) -> Dict[str, DataValue]:
        if not references:
            return {}
        try:
            response = self._ipc.request("client.read_batch", {"references": references})
            values = response.data.get("values", {})
            return {ref: self._to_data_value(ref, info) for ref, info in values.items()}
        except IPCError as exc:
            self._log("error", f"Read batch failed: {exc}")
            return {}

    def write_value(self, reference: str, value: Any) -> bool:
        try:
            response = self._ipc.request("client.write", {"reference": reference, "value": value})
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
