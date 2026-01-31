"""
Server Proxy Unit Tests
=======================

测试 IEC61850ServerProxy 的核心行为
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pytest

from core.data_model import DbPos
from core.data_model_manager import DataModelManager
from ipc.uds_client import IPCError, IPCResponse
from server.server_proxy import IEC61850ServerProxy, ServerConfig, ServerState


class DummyIPC:
    """可控的 IPC Stub, 用于验证请求和返回。"""

    def __init__(self) -> None:
        self.requests: List[Tuple[str, Dict[str, Any]]] = []
        self._responses: Dict[str, IPCResponse] = {}
        self._errors: Dict[str, IPCError] = {}

    def when(self, action: str, data: Dict[str, Any] | None = None, error: IPCError | None = None) -> None:
        if error is not None:
            self._errors[action] = error
            return
        self._responses[action] = IPCResponse(data=data or {})

    def request(self, action: str, payload: Dict[str, Any] | None = None) -> IPCResponse:
        self.requests.append((action, payload or {}))
        if action in self._errors:
            raise self._errors[action]
        return self._responses.get(action, IPCResponse(data={}))


def make_proxy() -> tuple[IEC61850ServerProxy, DummyIPC]:
    proxy = IEC61850ServerProxy(ServerConfig(), "/tmp/fake.sock")
    ipc = DummyIPC()
    proxy._ipc = ipc
    return proxy, ipc


def test_start_calls_ipc_and_updates_state():
    proxy, ipc = make_proxy()
    ipc.when("server.start", {})

    states: List[ServerState] = []
    logs: List[Tuple[str, str]] = []
    proxy.on_state_change(states.append)
    proxy.on_log(lambda level, message: logs.append((level, message)))

    result = proxy.start()

    assert result is True
    assert proxy.state == ServerState.RUNNING
    assert states == [ServerState.STARTING, ServerState.RUNNING]
    assert ipc.requests[0][0] == "server.start"
    assert "config" in ipc.requests[0][1]
    assert "model" in ipc.requests[0][1]
    assert logs[-1][0] == "info"


def test_start_when_running_returns_false():
    proxy, _ = make_proxy()
    proxy.state = ServerState.RUNNING

    logs: List[Tuple[str, str]] = []
    proxy.on_log(lambda level, message: logs.append((level, message)))

    result = proxy.start()

    assert result is False
    assert logs[-1][0] == "warning"


def test_stop_transitions_state_and_calls_ipc():
    proxy, ipc = make_proxy()
    proxy.state = ServerState.RUNNING
    ipc.when("server.stop", {})

    states: List[ServerState] = []
    proxy.on_state_change(states.append)

    result = proxy.stop()

    assert result is True
    assert proxy.state == ServerState.STOPPED
    assert states == [ServerState.STOPPING, ServerState.STOPPED]
    assert ipc.requests[0][0] == "server.stop"


def test_stop_error_sets_error_state():
    proxy, ipc = make_proxy()
    proxy.state = ServerState.RUNNING
    ipc.when("server.stop", error=IPCError("boom"))

    result = proxy.stop()

    assert result is False
    assert proxy.state == ServerState.ERROR


def test_load_model_success_logs_info():
    proxy, ipc = make_proxy()
    ipc.when("server.load_model", {"success": True})

    logs: List[Tuple[str, str]] = []
    proxy.on_log(lambda level, message: logs.append((level, message)))

    ied = DataModelManager().create_default_ied()
    proxy.load_model(ied)

    assert ipc.requests[0][0] == "server.load_model"
    assert logs[-1][0] == "info"


def test_load_model_failure_logs_error():
    proxy, ipc = make_proxy()
    ipc.when("server.load_model", {"success": False})

    logs: List[Tuple[str, str]] = []
    proxy.on_log(lambda level, message: logs.append((level, message)))

    ied = DataModelManager().create_default_ied()
    proxy.load_model(ied)

    assert logs[-1][0] == "error"


def test_set_data_value_updates_local_and_notifies_callbacks():
    proxy, ipc = make_proxy()
    ipc.when("server.set_data_value", {"success": True})

    ied = DataModelManager().create_default_ied()
    proxy.ied = ied

    reference = "PROT/XCBR1.Pos.stVal"
    data_attr = ied.get_data_attribute(reference)
    assert data_attr is not None

    changes: List[Tuple[Any, Any]] = []
    proxy.on_data_change(lambda ref, old, new: changes.append((old, new)))

    proxy.set_data_value(reference, DbPos.OFF)

    assert ipc.requests[0][0] == "server.set_data_value"
    assert data_attr.value == DbPos.OFF
    assert data_attr.timestamp is not None
    assert len(changes) == 1
    old_value, new_value = changes[0]
    assert old_value in {DbPos.ON, int(DbPos.ON), True}
    assert new_value == DbPos.OFF


def test_set_data_value_failure_does_not_notify_callbacks():
    proxy, ipc = make_proxy()
    ipc.when("server.set_data_value", {"success": False})

    ied = DataModelManager().create_default_ied()
    proxy.ied = ied

    reference = "PROT/XCBR1.Pos.stVal"
    changes: List[Tuple[Any, Any]] = []
    proxy.on_data_change(lambda ref, old, new: changes.append((old, new)))

    proxy.set_data_value(reference, DbPos.OFF)

    assert changes == []


def test_get_values_returns_payload():
    proxy, ipc = make_proxy()
    ipc.when("server.get_values", {"values": {"A": {"value": 1}}})

    result = proxy.get_values(["A"])

    assert result == {"A": {"value": 1}}


def test_get_values_error_returns_empty_dict():
    proxy, ipc = make_proxy()
    ipc.when("server.get_values", error=IPCError("fail"))

    result = proxy.get_values(["A"])

    assert result == {}


def test_get_connected_clients_returns_payload():
    proxy, ipc = make_proxy()
    ipc.when("server.get_clients", {"clients": [{"id": "c1"}]})

    result = proxy.get_connected_clients()

    assert result == [{"id": "c1"}]


def test_get_connected_clients_error_returns_empty_list():
    proxy, ipc = make_proxy()
    ipc.when("server.get_clients", error=IPCError("fail"))

    result = proxy.get_connected_clients()

    assert result == []
