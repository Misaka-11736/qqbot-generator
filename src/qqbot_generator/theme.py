"""视觉主题：颜色、字体、QSS。

设计参考：用户提供的蓝发鲸娘角色设定（深海军蓝 + 奶白蕾丝 + 渐变蓝）。
主色是「海军蓝 + 天空蓝」，保留一点奶油白作为纸张感底色。
所有颜色集中在 COLORS，改主题只动这里。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

COLORS = {
    "ink": "#1A2340",
    "ink2": "#2B3A5E",
    "sidebar": "#0E1830",
    "sidebar_hi": "#1B2A4A",
    "cream": "#F3F7FF",
    "cream2": "#E7EFFF",
    "card": "#FFFFFF",
    "line": "#DDE8F9",
    "text": "#1E2946",
    "muted": "#6E7FA3",
    "faint": "#A3B2CC",
    "coral": "#4F7FE0",
    "coral_dark": "#355FC4",
    "coral_soft": "#E1EBFF",
    "teal": "#3FAFC4",
    "teal_soft": "#DDF4F9",
    "blue": "#6FA1F2",
    "blue_soft": "#E8F1FF",
    "yellow": "#F0B459",
    "yellow_soft": "#FFF2D9",
    "green": "#35B98A",
    "green_soft": "#DDF5EC",
    "red": "#E25C6A",
    "red_soft": "#FFE5E8",
}

FONT_STACK = '"Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif'


def pick_font() -> str:
    families = set(QFontDatabase.families())
    for name in ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Segoe UI"):
        if name in families:
            return name
    return QFont().family()


def app_font(size: int = 10, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont(pick_font(), size)
    font.setWeight(weight)
    return font


def shadow(widget: QWidget, radius: int = 28, alpha: int = 30, dy: int = 8) -> QGraphicsDropShadowEffect:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(radius)
    effect.setOffset(0, dy)
    effect.setColor(QColor(27, 48, 92, alpha))
    widget.setGraphicsEffect(effect)
    return effect


def qss() -> str:
    c = COLORS
    from .paths import resource

    asset_dir = resource("assets").as_posix()
    chevron_down = f"{asset_dir}/chevron_down.png"
    chevron_up = f"{asset_dir}/chevron_up.png"
    check = f"{asset_dir}/check.png"
    return f"""
* {{
    font-family: {FONT_STACK};
    font-size: 13px;
    color: {c['text']};
}}
QMainWindow, QWidget#root {{
    background: {c['cream']};
}}
QWidget#content, QStackedWidget, QWidget#pageBody {{
    background: {c['cream']};
}}
QScrollArea, QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QWidget#footer {{
    background: {c['cream']};
    border-top: 1px solid {c['line']};
}}
QWidget#sidebar {{
    background: {c['sidebar']};
}}
QLabel#brandTitle {{
    color: #FFFFFF;
    font-size: 19px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QLabel#brandSub {{
    color: #8FA6D4;
    font-size: 11px;
}}
QLabel#navSection {{
    color: #5F7399;
    font-size: 10px;
    letter-spacing: 2px;
    padding-left: 12px;
}}
QPushButton#nav {{
    color: #AEBFDD;
    background: transparent;
    border: none;
    border-radius: 12px;
    padding: 10px 12px;
    text-align: left;
    font-size: 14px;
}}
QPushButton#nav:hover {{
    background: {c['sidebar_hi']};
    color: #FFFFFF;
}}
QPushButton#nav:checked {{
    background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #5B8DEF, stop:1 #3F6BD8);
    color: #FFFFFF;
    font-weight: 600;
}}
QLabel#pageTitle {{
    font-size: 26px;
    font-weight: 700;
    color: {c['ink']};
}}
QLabel#pageSub {{
    color: {c['muted']};
    font-size: 12px;
}}
QFrame#card {{
    background: {c['card']};
    border-radius: 18px;
    border: 1px solid {c['line']};
}}
QFrame#softCard {{
    background: {c['cream2']};
    border-radius: 16px;
    border: 1px solid #D5E3FA;
}}
QFrame#heroCard {{
    background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #14224A, stop:0.55 #1E3468, stop:1 #2C4E92);
    border-radius: 20px;
    border: 1px solid #33518F;
}}
QLabel#cardTitle {{
    font-size: 15px;
    font-weight: 700;
    color: {c['ink']};
}}
QLabel#cardHint {{
    color: {c['muted']};
    font-size: 12px;
}}
QLabel#heroTitle {{
    font-size: 30px;
    font-weight: 800;
    color: {c['ink']};
}}
QLabel#heroSub {{
    color: {c['muted']};
    font-size: 13px;
}}
QLabel#heroTitleOnDark {{
    color: #FFFFFF;
    font-size: 33px;
    font-weight: 800;
}}
QLabel#heroSubOnDark {{
    color: #BFD2F7;
    font-size: 13px;
}}
QLabel#hint {{
    color: {c['muted']};
    font-size: 12px;
}}
QLabel#mono {{
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
    color: {c['muted']};
}}
QPushButton#primary {{
    background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #5B8DEF, stop:1 #3F6BD8);
    color: #FFFFFF;
    border: none;
    border-radius: 12px;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 600;
}}
QPushButton#primary:hover {{
    background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #6C9BF5, stop:1 #4A76E2);
}}
QPushButton#primary:pressed {{ background: #355FC4; }}
QPushButton#primary:disabled {{ background: #B9CBF0; color: #FFFFFF; }}
QPushButton#onDark {{
    background: #FFFFFF;
    color: {c['coral_dark']};
    border: none;
    border-radius: 12px;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 700;
}}
QPushButton#onDark:hover {{ background: #EAF1FF; }}
QPushButton#onDarkGhost {{
    background: rgba(255, 255, 255, 0.10);
    color: #E6EFFF;
    border: 1px solid rgba(255, 255, 255, 0.32);
    border-radius: 12px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#onDarkGhost:hover {{ background: rgba(255, 255, 255, 0.18); }}
QPushButton#secondary {{
    background: #FFFFFF;
    color: {c['ink']};
    border: 1px solid {c['line']};
    border-radius: 12px;
    padding: 9px 18px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#secondary:hover {{ background: {c['cream2']}; border-color: #BFD2F2; }}
QPushButton#secondary:disabled {{ color: {c['faint']}; }}
QPushButton#ghost {{
    background: transparent;
    color: {c['muted']};
    border: none;
    padding: 6px 10px;
    border-radius: 8px;
}}
QPushButton#ghost:hover {{ color: {c['coral_dark']}; background: {c['coral_soft']}; }}
QPushButton#chip {{
    background: #FFFFFF;
    border: 1px solid {c['line']};
    border-radius: 14px;
    padding: 6px 12px;
    color: {c['ink2']};
    font-size: 12px;
}}
QPushButton#chip:hover {{ border-color: {c['coral']}; color: {c['coral_dark']}; }}
QPushButton#danger {{
    background: {c['red_soft']};
    color: {c['red']};
    border: none;
    border-radius: 10px;
    padding: 7px 14px;
    font-weight: 600;
}}
QPushButton#danger:hover {{ background: #FFD6DC; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: #FFFFFF;
    border: 1px solid {c['line']};
    border-radius: 10px;
    padding: 8px 10px;
    selection-background-color: {c['coral']};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {c['coral']};
}}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
    background: {c['cream']};
    color: {c['faint']};
}}
QComboBox {{ padding-right: 26px; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{
    image: url("{chevron_down}");
    width: 12px;
    height: 12px;
}}
QSpinBox, QDoubleSpinBox {{ padding-right: 24px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    height: 13px;
    border: none;
    background: transparent;
    margin: 2px 2px 0 0;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    height: 13px;
    border: none;
    background: transparent;
    margin: 0 2px 2px 0;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("{chevron_up}");
    width: 9px;
    height: 9px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("{chevron_down}");
    width: 9px;
    height: 9px;
}}
QComboBox QAbstractItemView {{
    background: #FFFFFF;
    border: 1px solid {c['line']};
    border-radius: 10px;
    selection-background-color: {c['coral_soft']};
    selection-color: {c['coral_dark']};
    outline: none;
}}
QProgressBar {{
    background: {c['cream2']};
    border: none;
    border-radius: 4px;
}}
QProgressBar::chunk {{
    background: {c['coral']};
    border-radius: 4px;
}}
QSlider::groove:horizontal {{
    height: 8px;
    border-radius: 4px;
    background: {c['cream2']};
}}
QSlider::sub-page:horizontal {{
    height: 8px;
    border-radius: 4px;
    background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #7FB2FF, stop:1 {c['coral']});
}}
QSlider::handle:horizontal {{
    width: 22px;
    height: 22px;
    margin: -7px 0;
    border-radius: 11px;
    background: #FFFFFF;
    border: 3px solid {c['coral']};
}}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 6px;
    border: 1px solid #C6D6F0;
    background: #FFFFFF;
}}
QCheckBox::indicator:checked {{
    background: {c['coral']};
    border: 1px solid {c['coral']};
    image: url("{check}");
}}
QScrollBar:vertical {{
    width: 10px;
    background: transparent;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: #C9D8F2;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #AFC4E8; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ height: 10px; background: transparent; }}
QScrollBar::handle:horizontal {{ background: #C9D8F2; border-radius: 5px; }}
QPlainTextEdit#logView {{
    background: {c['sidebar']};
    color: #D7E1F5;
    border: 1px solid #22345C;
    border-radius: 14px;
    padding: 12px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
}}
QPlainTextEdit#editor {{
    background: #FBFCFF;
    border: 1px solid {c['line']};
    border-radius: 14px;
    padding: 12px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
    line-height: 150%;
}}
QToolTip {{
    background: {c['ink']};
    color: #FFFFFF;
    border: none;
    padding: 6px 8px;
    border-radius: 8px;
}}
QMenu {{
    background: #FFFFFF;
    border: 1px solid {c['line']};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{ padding: 7px 18px; border-radius: 8px; }}
QMenu::item:selected {{ background: {c['coral_soft']}; color: {c['coral_dark']}; }}
QFrame#bubbleBot {{
    background: #FFFFFF;
    border: 1px solid {c['line']};
    border-radius: 14px;
}}
QFrame#bubbleMine {{
    background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #5B8DEF, stop:1 #3F6BD8);
    border: none;
    border-radius: 14px;
}}
QLabel#bubbleName {{
    color: {c['muted']};
    font-size: 10px;
    font-weight: 600;
    background: transparent;
}}
QLabel#bubbleNameMine {{
    color: rgba(255, 255, 255, 0.78);
    font-size: 10px;
    font-weight: 600;
    background: transparent;
}}
QLabel#bubbleText {{
    color: {c['text']};
    font-size: 13px;
    background: transparent;
}}
QLabel#bubbleTextMine {{
    color: #FFFFFF;
    font-size: 13px;
    background: transparent;
}}
"""


def status_color(kind: str) -> tuple[str, str]:
    return {
        "ok": (COLORS["green"], COLORS["green_soft"]),
        "warn": ("#A9721E", COLORS["yellow_soft"]),
        "error": (COLORS["red"], COLORS["red_soft"]),
        "info": (COLORS["coral_dark"], COLORS["coral_soft"]),
        "idle": (COLORS["muted"], "#EBF1FB"),
    }.get(kind, (COLORS["muted"], "#EBF1FB"))


__all__ = ["COLORS", "Qt", "app_font", "qss", "shadow", "status_color"]
