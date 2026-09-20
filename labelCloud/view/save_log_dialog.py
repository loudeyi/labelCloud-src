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
    """Recent activity: which frame was loaded, and what was written where."""

    def __init__(self, parent, entries: Sequence[Tuple], label_folder: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Activity Log"))
        self.resize(720, 420)
        layout = QtWidgets.QVBoxLayout(self)

        folder_label = QtWidgets.QLabel(
            self.tr("Label folder: %s") % f"<code>{label_folder}</code>"
        )
        folder_label.setTextFormat(1)  # Qt.RichText
        folder_label.setWordWrap(True)
        layout.addWidget(folder_label)

        table = QtWidgets.QTableWidget(len(entries), 4, self)
        table.setHorizontalHeaderLabels(
            [self.tr("Time"), self.tr("What"), self.tr("Result"), self.tr("File")]
        )
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QtWidgets.QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QTableWidget.SelectRows)

        for row, entry in enumerate(reversed(entries)):
            timestamp, kind, path, ok, message = (list(entry) + ["", "", "", True, ""])[:5]
            when = datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
            what = self.tr("loaded") if kind == "load" else self.tr("saved")
            if ok:
                result = self.tr("ok")
            else:
                result = self.tr("FAILED: %s") % message
            for column, value in enumerate((when, what, result, path)):
                item = QtWidgets.QTableWidgetItem(str(value))
                if not ok and column == 2:
                    item.setForeground(QtWidgets.QApplication.palette().link())
                table.setItem(row, column, item)
        table.resizeColumnsToContents()
        layout.addWidget(table)

        hint = QtWidgets.QLabel(
            self.tr(
                "Loading a frame, and every write of an edited frame, is listed here. "
                "The status bar shows the most recent of each."
            )
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        layout.addWidget(hint)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
