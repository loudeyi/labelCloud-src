"""Visual log of every label write, opened from the save indicator.

"Did it save?" and "where did it go?" were answerable only from the terminal log,
which is easy to miss while annotating. The status bar now carries a save
indicator and this dialog lists the recent writes with their exact paths.
"""
from __future__ import annotations

import datetime
from typing import List, Sequence, Tuple

from PyQt5 import QtWidgets
from PyQt5.QtCore import QCoreApplication


class SaveLogDialog(QtWidgets.QDialog):
    """Recent save attempts: time, result and target file."""

    def __init__(self, parent, entries: Sequence[Tuple[float, str, bool, str]], label_folder: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Save Log"))
        self.resize(720, 420)
        layout = QtWidgets.QVBoxLayout(self)

        folder_label = QtWidgets.QLabel(
            self.tr("Label folder: %s") % f"<code>{label_folder}</code>"
        )
        folder_label.setTextFormat(1)  # Qt.RichText
        folder_label.setWordWrap(True)
        layout.addWidget(folder_label)

        table = QtWidgets.QTableWidget(len(entries), 3, self)
        table.setHorizontalHeaderLabels(
            [self.tr("Time"), self.tr("Result"), self.tr("File")]
        )
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QtWidgets.QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QTableWidget.SelectRows)

        for row, (timestamp, path, ok, message) in enumerate(reversed(entries)):
            when = datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
            result = self.tr("saved") if ok else self.tr("FAILED: %s") % message
            for column, value in enumerate((when, result, path)):
                item = QtWidgets.QTableWidgetItem(str(value))
                if not ok and column == 1:
                    item.setForeground(QtWidgets.QApplication.palette().link())
                table.setItem(row, column, item)
        table.resizeColumnsToContents()
        layout.addWidget(table)

        hint = QtWidgets.QLabel(
            self.tr(
                "Every frame is written when you move to another frame or press "
                "Ctrl+S; autosave writes the current frame periodically."
            )
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        layout.addWidget(hint)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
