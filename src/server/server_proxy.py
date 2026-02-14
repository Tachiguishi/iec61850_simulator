"""
IEC61850 server proxy communicating with C++ backend via UDS.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from core.data_model import IED
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
    Server proxy for GUI, delegating IEC61850 networking to C++ backend via IPC.
    """

    def __init__(self, config: Optional[ServerConfig] = None, socket_path: str = "", timeout_ms: int = 3000):
        self.config = config or ServerConfig()
        self._states: Dict[str, ServerState] = {}

        # 将毫秒转换为秒传递给 UDSMessageClient
        self._ipc = UDSMessageClient(socket_path or "/tmp/iec61850_simulator.sock", timeout_ms / 1000.0)

        self._state_callbacks: Dict[str, Callable[[ServerState], None]] = {}
        self._connection_callbacks: Dict[str, Callable[[str, bool], None]] = {}
        self._data_callbacks: Dict[str, Callable[[str, Any, Any], None]] = {}
        self._log_callbacks: Dict[str, Callable[[str, str], None]] = {}

    # =====================================================================
    # Callback registration
    # =====================================================================

    def on_state_change(self, instance_id: str, callback: Callable[[ServerState], None]) -> None:
        self._state_callbacks[instance_id] = callback

    def off_state_change(self, instance_id: str, callback: Callable[[ServerState], None]) -> None:
        registered = self._state_callbacks.get(instance_id)
        if registered is callback:
            del self._state_callbacks[instance_id]

    def on_connection_change(self, instance_id: str, callback: Callable[[str, bool], None]) -> None:
        self._connection_callbacks[instance_id] = callback

    def off_connection_change(self, instance_id: str, callback: Callable[[str, bool], None]) -> None:
        registered = self._connection_callbacks.get(instance_id)
        if registered is callback:
            del self._connection_callbacks[instance_id]

    def on_data_change(self, instance_id: str, callback: Callable[[str, Any, Any], None]) -> None:
        self._data_callbacks[instance_id] = callback

    def off_data_change(self, instance_id: str, callback: Callable[[str, Any, Any], None]) -> None:
        registered = self._data_callbacks.get(instance_id)
        if registered is callback:
            del self._data_callbacks[instance_id]

    def on_log(self, instance_id: str, callback: Callable[[str, str], None]) -> None:
        self._log_callbacks[instance_id] = callback

    def off_log(self, instance_id: str, callback: Callable[[str, str], None]) -> None:
        registered = self._log_callbacks.get(instance_id)
        if registered is callback:
            del self._log_callbacks[instance_id]

    def remove_callback(self, instance_id: str) -> None:
        if instance_id in self._state_callbacks:
            del self._state_callbacks[instance_id]

        if instance_id in self._connection_callbacks:
            del self._connection_callbacks[instance_id]

        if instance_id in self._data_callbacks:
            del self._data_callbacks[instance_id]
        
        if instance_id in self._log_callbacks:
            del self._log_callbacks[instance_id]

    def close(self) -> None:
        """释放IPC连接资源"""
        self._ipc.close()

    # =====================================================================
    # Lifecycle
    # =====================================================================

    def start(self, instance_id: str, ied: Optional[IED] = None) -> bool:
        if self._states.get(instance_id, ServerState.STOPPED) == ServerState.RUNNING:
            self._log(instance_id, "warning", "Server already running")
            return False

        if not ied:
            self._log(instance_id, "error", "Start failed: no IED model provided")
            return False

        self._set_state(instance_id, ServerState.STARTING)
        try:
            # 从 IED 通信参数中获取 IP 地址，如果有的话覆盖配置
            effective_ip = self.config.ip_address
            if ied:
                for ap in ied.access_points.values():
                    if ap.mms_addresses and ap.mms_addresses.ip_address:
                        effective_ip = ap.mms_addresses.ip_address
                        self._log(instance_id, "info", f"Using IP from SCD: {effective_ip}")
                        break

            payload = {
                "instance_id": instance_id,
                "config": asdict(self.config),
                "model": ied.to_dict() if ied else {},
            }
            # 如果从 SCD 获取到 IP，覆盖 config 中的 ip_address
            if effective_ip != self.config.ip_address:
                payload["config"]["ip_address"] = effective_ip
            
            self._ipc.request("server.start", payload)
            self._set_state(instance_id, ServerState.RUNNING)
            self._log(instance_id, "info", f"Server started on {effective_ip}:{self.config.port}")
            return True
        except IPCError as exc:
            self._set_state(instance_id, ServerState.ERROR)
            self._log(instance_id, "error", f"Start failed: {exc}")
            return False

    def stop(self, instance_id: str) -> bool:
        if self._states.get(instance_id, ServerState.STOPPED) == ServerState.STOPPED:
            return True

        self._set_state(instance_id, ServerState.STOPPING)
        try:
            self._ipc.request("server.stop", {"instance_id": instance_id})
            self._set_state(instance_id, ServerState.STOPPED)
            self._log(instance_id, "info", "Server stopped")
            return True
        except IPCError as exc:
            self._set_state(instance_id, ServerState.ERROR)
            self._log(instance_id, "error", f"Stop failed: {exc}")
            return False

    # =====================================================================
    # Model & Data
    # =====================================================================

    def load_model(self, instance_id: str, ied: IED) -> None:
        try:
            response = self._ipc.request("server.load_model", {"instance_id": instance_id, "model": ied.to_dict()})
            if not response.data.get("success", False):
                raise IPCError("Backend failed to load model")
            self._log(instance_id, "info", f"Model loaded: {ied.name}")
        except IPCError as exc:
            self._log(instance_id, "error", f"Load model failed: {exc}")

    def set_data_value(self, instance_id: str, reference: str, value: Any) -> None:
        old_value = None
        try:
            response = self._ipc.request("server.set_data_value", {"instance_id": instance_id, "reference": reference, "value": value})
            if not response.data.get("success", False):
                raise IPCError("Backend failed to set data value")
            callback = self._data_callbacks.get(instance_id)
            if callback:
                callback(reference, old_value, value)
        except IPCError as exc:
            self._log(instance_id, "error", f"Set value failed: {exc}")

    def get_values(self, instance_id: str, references: List[str]) -> Dict[str, Dict[str, Any]]:
        if not references:
            return {}
        try:
            response = self._ipc.request("server.get_values", {"instance_id": instance_id, "references": references})
            values = response.data.get("values", {})
            return values
        except IPCError as exc:
            self._log(instance_id, "error", f"Get values failed: {exc}")
            return {}

    def get_connected_clients(self, instance_id: str) -> List[Dict[str, Any]]:
        try:
            response = self._ipc.request("server.get_clients", {"instance_id": instance_id})
            return response.data.get("clients", [])
        except IPCError as exc:
            self._log(instance_id, "error", f"Get clients failed: {exc}")
            return []
    
    def get_network_interfaces(self) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        获取网络接口列表及当前配置
        
        Returns:
            (interfaces, current_interface): 接口列表和当前配置的接口
        """
        try:
            response = self._ipc.request("server.get_interfaces", {})
            interfaces = response.data.get("interfaces", [])
            current_interface = response.data.get("current_interface")
            return interfaces, current_interface
        except IPCError as exc:
            self._log("system", "error", f"Get interfaces failed: {exc}")
            return [], None
    
    def set_network_interface(self, interface_name: str, prefix_len: int = 24) -> bool:
        """
        设置全局网络接口配置
        
        Args:
            interface_name: 网卡名称
            prefix_len: IP前缀长度，默认24
            
        Returns:
            是否设置成功
        """
        try:
            response = self._ipc.request("server.set_interface", {
                "interface_name": interface_name,
                "prefix_len": prefix_len
            })
            if response.data.get("interface_name") == interface_name:
                self._log("system", "info", f"Network interface set to: {interface_name} (prefix_len: {prefix_len})")
                return True
            return False
        except IPCError as exc:
            self._log("system", "error", f"Set interface failed: {exc}")
            return False

    # =====================================================================
    # Internal helpers
    # =====================================================================

    def _set_state(self, instance_id: str, state: ServerState) -> None:
        self._states[instance_id] = state
        if instance_id in self._state_callbacks:
            self._state_callbacks[instance_id](state)

    def _log(self, instance_id: str, level: str, message: str) -> None:
        if instance_id in self._log_callbacks:
            self._log_callbacks[instance_id](level, message)
        if level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)
        else:
            logger.info(message)
