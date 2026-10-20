"""机器人进程管理：启动 / 停止 / 状态探测。"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from .. import paths

CREATE_NO_WINDOW = 0x08000000


def port_open(host: str, port: int, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


class ProcessManager(QObject):
    changed = Signal()
    message = Signal(str)

    def __init__(self, config_path: Callable[[], Path], get_port: Callable[[], int], parent: QObject | None = None):
        super().__init__(parent)
        self._config_path = config_path
        self._get_port = get_port
        self._proc: subprocess.Popen | None = None
        self._status = "stopped"
        self._started_at = 0.0
        self._stopping_since = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(1200)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    # ---------- 状态 ----------

    @property
    def status(self) -> str:
        return self._status

    @property
    def running(self) -> bool:
        return self._status in ("starting", "running")

    @property
    def pid(self) -> int:
        return self._proc.pid if self._proc is not None else 0

    @property
    def uptime(self) -> str:
        if not self.running or not self._started_at:
            return "—"
        seconds = int(time.time() - self._started_at)
        if seconds < 60:
            return f"{seconds} 秒"
        if seconds < 3600:
            return f"{seconds // 60} 分 {seconds % 60} 秒"
        return f"{seconds // 3600} 时 {(seconds % 3600) // 60} 分"

    def _set_status(self, value: str) -> None:
        if value != self._status:
            self._status = value
            self.changed.emit()

    # ---------- 控制 ----------

    def start(self) -> bool:
        if self.running:
            return True
        port = self._get_port()
        if not port_free("127.0.0.1", port):
            self.message.emit(f"端口 {port} 已被占用，先关掉别的机器人实例")
            self._set_status("error")
            return False

        cmd = self._command()
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        repo_src = paths.app_dir() / "src"
        if not paths.is_frozen() and repo_src.is_dir():
            env["PYTHONPATH"] = str(repo_src) + os.pathsep + env.get("PYTHONPATH", "")
        creation = CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(paths.data_dir()),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=open(paths.data_dir() / "logs" / "bot-stderr.log", "ab"),  # noqa: SIM115
                creationflags=creation,
            )
        except OSError as exc:
            self.message.emit(f"启动失败：{exc}")
            self._set_status("error")
            return False

        self._started_at = time.time()
        self._stopping_since = 0.0
        self._set_status("starting")
        self.message.emit(f"机器人进程已拉起（PID {self._proc.pid}），等待监听端口 {port} …")
        return True

    def stop(self) -> None:
        if self._proc is None:
            self._set_status("stopped")
            return
        self._set_status("stopping")
        self._stopping_since = time.time()
        try:
            self._proc.terminate()
        except OSError:
            pass
        self.message.emit("正在停止机器人 …")

    def _command(self) -> list[str]:
        config = str(self._config_path())
        if paths.is_frozen():
            return [sys.executable, "--run-bot", "--config", config]
        return [sys.executable, "-m", "qqbot_generator", "--run-bot", "--config", config]

    # ---------- 轮询 ----------

    def _poll(self) -> None:
        if self._proc is None and self._status in ("starting", "running"):
            self._set_status("stopped")
            self.message.emit("机器人进程已退出，状态已重置")
            return
        if self._proc is not None:
            code = self._proc.poll()
            if code is not None:
                self._proc = None
                self._started_at = 0.0
                if self._status == "stopping":
                    self.message.emit("机器人已停止")
                else:
                    self.message.emit(f"机器人进程退出（代码 {code}），看日志里的原因")
                self._set_status("stopped")
                return

        if self._proc is not None and self._status == "starting":
            if port_open("127.0.0.1", self._get_port()):
                self._set_status("running")
                self.message.emit("机器人已就绪，等待 NapCat 连接")
        elif self._status == "stopping":
            if time.time() - self._stopping_since > 4 and self._proc is not None:
                try:
                    self._proc.kill()
                except OSError:
                    pass
                self.message.emit("机器人没有响应停止信号，已强制结束")

    def shutdown(self) -> None:
        if self._proc is not None:
            try:
                self._proc.terminate()
            except OSError:
                pass
            self._proc = None
