"""应用上下文：把配置、进程、日志、NapCat 服务串起来，页面只依赖它。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from qqbot_core.config import Config

from . import paths
from .services.config_service import ConfigService
from .services.logbus import LogBus
from .services.process_manager import ProcessManager


class AppSignals(QObject):
    toast = Signal(str)
    config_changed = Signal()
    request_page = Signal(str)
    status_dirty = Signal()


@dataclass
class AppContext:
    config_service: ConfigService
    process: ProcessManager
    logbus: LogBus
    signals: AppSignals = field(default_factory=AppSignals)
    navigate: Callable[[str], None] | None = None

    @property
    def cfg(self) -> Config:
        return self.config_service.cfg

    @property
    def config_path(self):
        return self.config_service.path

    def save_config(self, cfg: Config | None = None) -> None:
        self.config_service.save(cfg or self.cfg)
        self.signals.config_changed.emit()
        self.signals.status_dirty.emit()

    def reload_config(self) -> Config:
        cfg = self.config_service.reload()
        self.signals.config_changed.emit()
        self.signals.status_dirty.emit()
        return cfg

    def toast(self, text: str) -> None:
        self.signals.toast.emit(text)

    def open_page(self, key: str) -> None:
        if self.navigate is not None:
            self.navigate(key)

    @property
    def data_dir(self):
        return paths.data_dir()
