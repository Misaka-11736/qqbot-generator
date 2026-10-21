"""页面注册表：新增页面只需要在这里加一行。"""

from __future__ import annotations

from .about import AboutPage
from .base import BasePage
from .bot import BotPage
from .capabilities import CapabilitiesPage
from .chat import ChatPage
from .diagnostics import DiagnosticsPage
from .home import HomePage
from .logs import LogsPage
from .model import ModelPage
from .napcat import NapCatPage
from .persona import PersonaPage
from .settings import SettingsPage
from .tutorial import TutorialPage

PAGES: list[type[BasePage]] = [
    HomePage,
    BotPage,
    ModelPage,
    PersonaPage,
    CapabilitiesPage,
    NapCatPage,
    ChatPage,
    LogsPage,
    DiagnosticsPage,
    TutorialPage,
    SettingsPage,
    AboutPage,
]

__all__ = ["PAGES", "BasePage"]
