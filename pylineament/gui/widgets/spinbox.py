"""Spin boxes that are easy to type into.

* The whole value is selected when the box gets focus (click or Tab), so typing replaces it.
  Without this, clicking at the end of "1.2000" and typing a digit is rejected (all decimals are
  used) and integer boxes append ("40" -> "405").
* Numbers always use "." as decimal separator, whatever the Windows regional settings.
"""

from PyQt5.QtCore import QEvent, QLocale, QTimer
from PyQt5.QtWidgets import QDoubleSpinBox, QSpinBox

_C_LOCALE = QLocale(QLocale.C)
_C_LOCALE.setNumberOptions(QLocale.OmitGroupSeparator | QLocale.RejectGroupSeparator)


class _SelectAllMixin:
    def _setup(self):
        self.setLocale(_C_LOCALE)
        self._select_on_release = False
        self.lineEdit().installEventFilter(self)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        # after the mouse press has placed the cursor, select everything
        QTimer.singleShot(0, self.selectAll)
        self._select_on_release = True

    def eventFilter(self, obj, event):
        if (obj is self.lineEdit() and event.type() == QEvent.MouseButtonRelease
                and self._select_on_release):
            self._select_on_release = False
            QTimer.singleShot(0, self.selectAll)
        return super().eventFilter(obj, event)


class SpinBox(_SelectAllMixin, QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup()


class DoubleSpinBox(_SelectAllMixin, QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup()
