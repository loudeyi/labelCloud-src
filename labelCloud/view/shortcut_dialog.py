"""F1: the keyboard shortcut overview.

labelCloud 1.1.1 documented its shortcuts only in the README, while the status bar
showed a few of them in tooltips. This dialog renders the live table from
``control/keymap.py``, so it always matches what the application actually does —
including any rebinding done through the ``[SHORTCUTS]`` section of ``config.ini``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import QCoreApplication

from ..control.keymap import ALT_FACTOR, SHIFT_FACTOR, KeyMap

if TYPE_CHECKING:
    pass


class ShortcutDialog(QtWidgets.QDialog):
    """Modal list of every binding, grouped by topic."""

    def __init__(self, parent, keymap: KeyMap) -> None:
        super().__init__(parent)
        self.keymap = keymap
        self.setWindowTitle(self.tr("Keyboard Shortcuts"))
        self.resize(560, 640)

        layout = QtWidgets.QVBoxLayout(self)

        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidgetResizable(True)
        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)

        for group, bindings in self.keymap.groups():
            # group names live in the binding table, so they are registered under
            # the "keymap" context by tools/update_translations.py
            group_label = QtWidgets.QLabel(
                QCoreApplication.translate("keymap", group)
            )
            font = group_label.font()
            font.setBold(True)
            group_label.setFont(font)
            content_layout.addWidget(group_label)

            grid = QtWidgets.QGridLayout()
            grid.setColumnStretch(1, 1)
            for row, binding in enumerate(bindings):
                keys = QtWidgets.QLabel(f"<b>{binding.sequence}</b>")
                keys.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                description = QtWidgets.QLabel(
                    QCoreApplication.translate("keymap", binding.label)
                )
                description.setWordWrap(True)
                grid.addWidget(keys, row, 0)
                grid.addWidget(description, row, 1)
            content_layout.addLayout(grid)
            content_layout.addSpacing(12)

        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        note = QtWidgets.QLabel(
            self.tr(
                "Shift multiplies the step by %s, Alt by %s (movement, rotation and "
                "scaling keys)."
            )
            % (int(SHIFT_FACTOR), ALT_FACTOR)
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        hint = QtWidgets.QLabel(
            self.tr(
                "Any binding can be changed in the [SHORTCUTS] section of config.ini, "
                'for example "copy_box = Ctrl+C".'
            )
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        layout.addWidget(hint)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
