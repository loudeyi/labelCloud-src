from typing import Optional

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import QCoreApplication

from ..definitions import Context, Mode


class StatusManager:
    """The status bar: a persistent mode label plus a transient hint message.

    Mode labels are translated through :meth:`_mode_text` so that switching the
    interface language updates them immediately. Transient messages are set by the
    caller (already translated with its own ``tr()``); they are cleared on a
    language change because Qt cannot re-translate a string after the fact — the
    next user action re-sets them in the new language.
    """

    def __init__(self, status_bar: QtWidgets.QStatusBar) -> None:
        self.status_bar = status_bar

        # Add permanent status label
        self.mode_label = QtWidgets.QLabel()
        self.mode_label.setStyleSheet(
            "font-weight: bold; font-size: 14px; min-width: 275px;"
        )
        self.mode_label.setAlignment(QtCore.Qt.AlignCenter)
        self.status_bar.addWidget(self.mode_label, stretch=0)

        # Add a permanent readout of the world position under the cursor
        self.position_label = QtWidgets.QLabel()
        self.position_label.setStyleSheet("font-size: 13px; color: #555;")
        self.status_bar.addPermanentWidget(self.position_label, stretch=0)

        # Add temporary status message / tips
        self.message_label = QtWidgets.QLabel()
        self.message_label.setStyleSheet("font-size: 14px;")
        self.message_label.setAlignment(QtCore.Qt.AlignLeft)
        self.status_bar.addWidget(self.message_label, stretch=1)

        self.msg_context = Context.DEFAULT
        self.mode = Mode.NAVIGATION
        self.set_mode(Mode.NAVIGATION)

    @staticmethod
    def _mode_text(mode: Mode) -> str:
        if mode == Mode.ALIGNMENT:
            return QCoreApplication.translate("StatusManager", "Alignment Mode")
        if mode == Mode.CORRECTION:
            return QCoreApplication.translate("StatusManager", "Correction Mode")
        if mode == Mode.DRAWING:
            return QCoreApplication.translate("StatusManager", "Drawing Mode")
        return QCoreApplication.translate("StatusManager", "Navigation Mode")

    def set_cursor_position(self, position) -> None:
        """Show the world coordinates under the cursor (helps place boxes exactly)."""
        if position is None:
            self.position_label.setText("")
            return
        self.position_label.setText(
            "X %6.2f   Y %6.2f   Z %6.2f" % (position[0], position[1], position[2])
        )

    def set_mode(self, mode: Mode) -> None:
        self.mode = mode
        self.mode_label.setText(self._mode_text(mode))

    def set_message(self, message: str, context: Context = Context.DEFAULT) -> None:
        if context >= self.msg_context:
            self.message_label.setText(message)
            self.msg_context = context

    def clear_message(self, context: Optional[Context] = None):
        if context == None or context == self.msg_context:
            self.msg_context = Context.DEFAULT
            self.set_message("")

    def retranslate(self) -> None:
        """Re-render everything that can be re-rendered (see class docstring)."""
        self.set_mode(self.mode)
        self.clear_message()

    def update_status(
        self,
        message: str,
        mode: Optional[Mode] = None,
        context: Context = Context.DEFAULT,
    ):
        self.set_message(message, context)

        if mode:
            self.set_mode(mode)
