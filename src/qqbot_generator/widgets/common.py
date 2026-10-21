"""通用控件：卡片、状态胶囊、字段行、Toast。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QVBoxLayout,
    QWidget,
)

from ..theme import COLORS, shadow, status_color


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, padding: int = 22, soft: bool = False):
        super().__init__(parent)
        self.setObjectName("softCard" if soft else "card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(padding, padding, padding, padding)
        self._layout.setSpacing(12)
        if not soft:
            shadow(self, radius=30, alpha=18, dy=8)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget) -> QWidget:
        self._layout.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)

    def add_stretch(self, value: int = 1) -> None:
        self._layout.addStretch(value)


class SectionTitle(QWidget):
    def __init__(self, title: str, hint: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.title = QLabel(title)
        self.title.setObjectName("cardTitle")
        layout.addWidget(self.title)
        self.hint = QLabel(hint)
        self.hint.setObjectName("cardHint")
        self.hint.setWordWrap(True)
        self.hint.setVisible(bool(hint))
        layout.addWidget(self.hint)


class StatusPill(QLabel):
    def __init__(self, text: str = "未启动", kind: str = "idle", parent: QWidget | None = None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_status(kind, text)

    def set_status(self, kind: str, text: str) -> None:
        fg, bg = status_color(kind)
        self.setText(f"●  {text}")
        self.setStyleSheet(
            f"color:{fg}; background:{bg}; border-radius:11px; padding:3px 10px; font-size:12px; font-weight:600;"
        )
        self.setFixedHeight(24)


class Field(QWidget):
    """标签在上、控件在下的表单行。"""

    def __init__(self, label: str, widget: QWidget, hint: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.label = QLabel(label)
        self.label.setStyleSheet(f"color:{COLORS['ink2']}; font-size:12px; font-weight:600;")
        layout.addWidget(self.label)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(widget)
        self.widget = widget
        if hint:
            tip = QLabel(hint)
            tip.setObjectName("hint")
            tip.setWordWrap(True)
            layout.addWidget(tip)


class Row(QWidget):
    """水平排列的一组控件，自动等宽。"""

    def __init__(self, *widgets: QWidget, spacing: int = 14, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        for widget in widgets:
            layout.addWidget(widget, 1)


class Divider(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setStyleSheet(f"background:{COLORS['line']}; border:none;")


class Toast(QLabel):
    """浮在窗口底部的轻提示。"""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet(
            "background:#182033; color:#FFFFFF; border-radius:16px; padding:10px 18px;"
            "font-size:13px; font-weight:600;"
        )
        self.setVisible(False)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(220)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)

    def show_message(self, text: str, msec: int = 1800) -> None:
        self.setText(text)
        self.adjustSize()
        self._reposition()
        self.setVisible(True)
        self.raise_()
        self._effect.setOpacity(0.0)
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(msec)

    def _fade_out(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self._hide_once)
        self._anim.start()

    def _hide_once(self) -> None:
        try:
            self._anim.finished.disconnect(self._hide_once)
        except (RuntimeError, TypeError):
            pass
        self.setVisible(False)

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.setMaximumWidth(max(240, parent.width() - 120))
        self.adjustSize()
        self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 28)


class ClickableCard(Card):
    clicked = Signal()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


def small_button(text: str, kind: str = "secondary", icon=None) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(kind)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if icon is not None:
        button.setIcon(icon)
    return button


def dot(color: str, size: int = 8) -> QLabel:
    label = QLabel()
    label.setFixedSize(size, size)
    label.setStyleSheet(f"background:{color}; border-radius:{size // 2}px;")
    return label


def muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


def strong(text: str, size: int = 15) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color:{COLORS['ink']}; font-size:{size}px; font-weight:700;")
    return label


def color_swatch(color: str, size: int = 10) -> QLabel:
    label = QLabel()
    label.setFixedSize(size, size)
    label.setStyleSheet(f"background:{color}; border-radius:{size // 2}px;")
    return label


class DragOnlySlider(QSlider):
    """只有按住 handle 才能拖动；点击轨道不跳值，滚轮/键盘保留。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dragging = False

    def _on_handle(self, pos) -> bool:
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        handle = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self)
        return handle.adjusted(-4, -8, 4, 8).contains(pos)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._on_handle(event.position().toPoint()):
            self._dragging = False
            event.accept()
            return
        self._dragging = event.button() == Qt.MouseButton.LeftButton
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            super().mouseMoveEvent(event)
        else:
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False
        super().mouseReleaseEvent(event)

class WheelSlider(DragOnlySlider):
    """鼠标滚轮直接调值，不会被外层滚动区抢走。"""

    def wheelEvent(self, event):
        step = 1 if event.angleDelta().y() > 0 else -1
        self.setValue(self.value() + step * max(1, (self.maximum() - self.minimum()) // 50))
        event.accept()


class _ComboPopup(QFrame):
    """自绘下拉弹层：外层透明，内层圆角卡片，列表项独立圆角。"""

    def __init__(self, combo: RoundedComboBox):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.combo = combo
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        self.card = QFrame()
        self.card.setObjectName("comboCard")
        self.card.setStyleSheet(
            "QFrame#comboCard{background:#FFFFFF;border:1px solid #DDE5F2;border-radius:12px;}"
            "QListWidget{background:transparent;border:none;outline:none;padding:4px;}"
            "QListWidget::item{min-height:32px;padding:4px 12px;margin:2px 4px;border-radius:8px;color:#1F2A44;}"
            "QListWidget::item:selected{background:#FFE9E2;color:#C85A3F;}"
        )
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(6, 6, 6, 6)
        self.list = QListWidget(self.card)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemClicked.connect(self._choose)
        self.list.itemActivated.connect(self._choose)
        card_layout.addWidget(self.list)
        outer.addWidget(self.card)
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(20, 35, 60, 60))
        self.card.setGraphicsEffect(shadow)
        self.list.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.list and event.type() == event.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.close()
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._choose(self.list.currentItem())
                return True
        return super().eventFilter(obj, event)

    def _choose(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        self.combo.setCurrentIndex(self.list.row(item))
        self.close()

    def open_for(self, index: int) -> None:
        self.list.clear()
        for i in range(self.combo.count()):
            item = QListWidgetItem(self.combo.itemText(i))
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.list.addItem(item)
        self.list.setCurrentRow(max(0, index))
        combo_pos = self.combo.mapToGlobal(QPoint(0, self.combo.height() + 4))
        screen = QGuiApplication.screenAt(combo_pos) or QGuiApplication.primaryScreen()
        width = max(self.combo.width(), 220)
        height = min(360, self.list.count() * 38 + 28)
        if screen is not None:
            area = screen.availableGeometry()
            x = min(combo_pos.x(), area.right() - width - 12)
            y = combo_pos.y()
            if y + height > area.bottom():
                y = self.combo.mapToGlobal(QPoint(0, 0)).y() - height - 4
            self.setGeometry(x, max(area.top(), y), width, height)
        else:
            self.setGeometry(combo_pos.x(), combo_pos.y(), width, height)
        self.show()
        self.raise_()
        self.activateWindow()
        self.list.setFocus()
        self.list.scrollToItem(self.list.currentItem())


class RoundedComboBox(QComboBox):
    """全局统一：完全自绘弹层，避开原生容器的黑边和方角。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._popup: _ComboPopup | None = None

    def showPopup(self) -> None:
        if self.count() == 0:
            return
        if self._popup is None:
            self._popup = _ComboPopup(self)
        self._popup.open_for(self.currentIndex())

    def hidePopup(self) -> None:
        if self._popup is not None:
            self._popup.close()


