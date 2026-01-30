"""
IEC61850 server proxy communicating with C++ backend via UDS.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from core.data_model import IED
from core.data_model_manager import DataModelManager
from ipc.uds_client import IPCError, UDSMessageClient

class ServerState(Enum):
    """Server lifecycle state."""
    STOPPED = auto()
    STARTING = auto()
    RUNNING = auto()
    STOPPING = auto()
    ERROR = auto()


@dataclass
class ServerConfig:
    """Server configuration."""
    ip_address: str = "0.0.0.0"
    port: int = 102
    max_connections: int = 10
    update_interval_ms: int = 1000
    enable_random_values: bool = False
    enable_reporting: bool = True
    enable_goose: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServerConfig":
        return cls(
            ip_address=data.get("ip_address", "0.0.0.0"),
            port=data.get("port", 102),
            max_connections=data.get("max_connections", 10),
            update_interval_ms=data.get("update_interval_ms", 1000),
            enable_random_values=data.get("enable_random_values", False),
            enable_reporting=data.get("enable_reporting", True),
            enable_goose=data.get("enable_goose", False),
        )
    


class IEC61850ServerProxy:
    """
    Server proxy for GUI. Keeps a local IED model for UI display,
    while delegating IEC61850 networking to C++ backend via IPC.
    """

    def __init__(self, config: Optional[ServerConfig], socket_path: str, timeout_ms: int = 3000):
        self.config = config or ServerConfig()
        self.state = ServerState.STOPPED

        self.data_model_manager = DataModelManager()
        self.ied: Optional[IED] = None

        self._ipc = UDSMessageClient(socket_path, timeout_ms)

        self._state_callbacks: List[Callable[[ServerState], None]] = []
        self._connection_callbacks: List[Callable[[str, bool], None]] = []
        self._data_callbacks: List[Callable[[str, Any, Any], None]] = []
        self._log_callbacks: List[Callable[[str, str], None]] = []

    # =====================================================================
    # Callback registration
    # =====================================================================

    def on_state_change(self, callback: Callable[[ServerState], None]) -> None:
        self._state_callbacks.append(callback)

    def on_connection_change(self, callback: Callable[[str, bool], None]) -> None:
        self._connection_callbacks.append(callback)

    def on_data_change(self, callback: Callable[[str, Any, Any], None]) -> None:
        self._data_callbacks.append(callback)

    def on_log(self, callback: Callable[[str, str], None]) -> None:
        self._log_callbacks.append(callback)

    # =====================================================================
    # Lifecycle
    # =====================================================================

    def start(self) -> bool:
        if self.state == ServerState.RUNNING:
            self._log("warning", "Server already running")
            return False

        if not self.ied:
            self.ied = self.data_model_manager.create_default_ied()

        self._set_state(ServerState.STARTING)
        try:
            payload = {
                "config": asdict(self.config),
                "model": self.ied.to_dict() if self.ied else {},
            }
            self._ipc.request("server.start", payload)
            self._set_state(ServerState.RUNNING)
            self._log("info", f"Server started on {self.config.ip_address}:{self.config.port}")
            return True
        except IPCError as exc:
            self._set_state(ServerState.ERROR)
            self._log("error", f"Start failed: {exc}")
            return False

    def stop(self) -> bool:
        if self.state == ServerState.STOPPED:
            return True

        self._set_state(ServerState.STOPPING)
        try:
            self._ipc.request("server.stop", {})
            self._set_state(ServerState.STOPPED)
            self._log("info", "Server stopped")
            return True
        except IPCError as exc:
            self._set_state(ServerState.ERROR)
            self._log("error", f"Stop failed: {exc}")
            return False

    # =====================================================================
    # Model & Data
    # =====================================================================

    def load_model(self, ied: IED) -> None:
        self.ied = ied
        try:
            self._ipc.request("server.load_model", {"model": ied.to_dict()})
            self._log("info", f"Model loaded: {ied.name}")
        except IPCError as exc:
            self._log("error", f"Load model failed: {exc}")

    def set_data_value(self, reference: str, value: Any) -> None:
        old_value = None
        if self.ied:
            da = self.ied.get_data_attribute(reference)
            if da:
                old_value = da.value
                da.value = value
                da.timestamp = datetime.now()
        try:
            self._ipc.request("server.set_data_value", {"reference": reference, "value": value})
            for callback in self._data_callbacks:
                callback(reference, old_value, value)
        except IPCError as exc:
            self._log("error", f"Set value failed: {exc}")

    def get_values(self, references: List[str]) -> Dict[str, Dict[str, Any]]:
        if not references:
            return {}
        try:
            response = self._ipc.request("server.get_values", {"references": references})
            values = response.data.get("values", {})
            return values
        except IPCError as exc:
            self._log("error", f"Get values failed: {exc}")
            return {}

    def get_connected_clients(self) -> List[Dict[str, Any]]:
        try:
            response = self._ipc.request("server.get_clients", {})
            return response.data.get("clients", [])
        except IPCError as exc:
            self._log("error", f"Get clients failed: {exc}")
            return []

    # =====================================================================
    # Internal helpers
    # =====================================================================

    def _set_state(self, state: ServerState) -> None:
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
