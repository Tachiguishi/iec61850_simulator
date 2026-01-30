"""
Core process manager for iec61850_core lifecycle.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSignal, QProcess


class CoreProcessManager(QObject):
    """Manage iec61850_core process lifecycle from GUI."""

    started = pyqtSignal()
    stopped = pyqtSignal()
    output = pyqtSignal(str)
    error_output = pyqtSignal(str)
    state_changed = pyqtSignal(str)

    def __init__(self, config: Dict, project_root: Path, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._config = config
        self._project_root = project_root
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)

        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.stateChanged.connect(self._on_state_changed)
        self._process.finished.connect(self._on_finished)

    def start(self) -> bool:
        if self._process.state() != QProcess.ProcessState.NotRunning:
            return True

        core_config = self._config.get("core", {})
        binary_path = core_config.get("binary_path")
        if not binary_path:
            binary_path = "iec61850/build/src/iec61850_core"

        binary = Path(binary_path)
        if not binary.is_absolute():
            binary = (self._project_root / binary).resolve()

        if not binary.exists():
            self.error_output.emit(f"iec61850_core 未找到: {binary}")
            return False

        socket_path = self._config.get("ipc", {}).get("socket_path", "/tmp/iec61850_simulator.sock")
        args: List[str] = core_config.get("args", [])

        if args:
            args = [arg.format(socket_path=socket_path) for arg in args]
        else:
            args = []

        if core_config.get("pdeathsig", True) and "--pdeathsig" not in args:
            args.insert(0, "--pdeathsig")

        if not any("{socket_path}" in arg for arg in core_config.get("args", [])):
            if "--socket" not in args and not any(arg.startswith("--socket=") for arg in args):
                args.append(socket_path)

        self._process.start(str(binary), args)
        return True

    def stop(self) -> None:
        if self._process.state() == QProcess.ProcessState.NotRunning:
            return

        self._process.terminate()
        if not self._process.waitForFinished(2000):
            self._process.kill()
            self._process.waitForFinished(2000)

    def is_running(self) -> bool:
        return self._process.state() == QProcess.ProcessState.Running

    def _on_stdout(self) -> None:
        data = self._process.readAllStandardOutput().data().decode(errors="ignore").strip()
        if data:
            self.output.emit(data)

    def _on_stderr(self) -> None:
        data = self._process.readAllStandardError().data().decode(errors="ignore").strip()
        if data:
            self.error_output.emit(data)

    def _on_state_changed(self, state: QProcess.ProcessState) -> None:
        mapping = {
            QProcess.ProcessState.NotRunning: "stopped",
            QProcess.ProcessState.Starting: "starting",
            QProcess.ProcessState.Running: "running",
        }
        state_text = mapping.get(state, "unknown")
        self.state_changed.emit(state_text)

        if state == QProcess.ProcessState.Running:
            self.started.emit()
        elif state == QProcess.ProcessState.NotRunning:
            self.stopped.emit()

    def _on_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        self.state_changed.emit(f"exited({exit_code})")
