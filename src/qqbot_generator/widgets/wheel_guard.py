"""全局滚轮守卫：页面滚动时不误调滑块、数字框和下拉框。"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QAbstractScrollArea, QAbstractSpinBox, QApplication, QComboBox, QSlider, QWidget


class WheelGuard(QObject):
    """滚轮经过可调控件时，无 Ctrl 就转发给外层滚动区，不改变数值。"""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.Wheel or not isinstance(obj, QWidget):
            return False
        if not isinstance(obj, (QSlider, QAbstractSpinBox, QComboBox)):
            return False
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return False
        if isinstance(obj, QComboBox):
            popup = getattr(obj, "_popup", None)
            if popup is not None and popup.isVisible():
                return False
            if obj.view().isVisible():
                return False
        area = obj.parentWidget()
        while area is not None and not isinstance(area, QAbstractScrollArea):
            area = area.parentWidget()
        if area is not None:
            wheel = event
            forwarded = QWheelEvent(
                wheel.position(),
                wheel.globalPosition(),
                wheel.pixelDelta(),
                wheel.angleDelta(),
                wheel.buttons(),
                wheel.modifiers(),
                wheel.phase(),
                wheel.inverted(),
            )
            QApplication.sendEvent(area.viewport(), forwarded)
        return True
