"""F-26: a small progress/statistics overview of the folder being labelled.

Answers the questions that were previously only answerable by running external
scripts: how much of the dataset is labelled, how many boxes per class exist, and
what is still pending in this frame. "Labelled" distinguishes three states that
labelCloud's file-per-frame storage makes easy to confuse:

* **no label file** — never touched,
* **empty file** — opened and confirmed to contain nothing,
* **has boxes** — at least one object.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

from PyQt5 import QtWidgets
from PyQt5.QtCore import QCoreApplication

from ..control.config_manager import config
from ..io.labels.config import LabelConfig


def collect_statistics(
    pointcloud_folder: Path, label_folder: Path, limit: int = 20000
) -> Dict[str, object]:
    """Scan both folders and summarise the labelling progress."""
    pcd_files = sorted(pointcloud_folder.glob("*.pcd"))[:limit]
    label_files = {path.stem: path for path in label_folder.glob("*.json")}

    with_boxes = 0
    empty = 0
    per_class: Dict[str, int] = {}
    unreadable = 0

    for pcd in pcd_files:
        label_file = label_files.get(pcd.stem)
        if label_file is None:
            continue
        try:
            with label_file.open("r") as stream:
                objects = json.load(stream).get("objects", [])
        except (OSError, json.JSONDecodeError):
            unreadable += 1
            continue
        if not objects:
            empty += 1
            continue
        with_boxes += 1
        for obj in objects:
            name = str(obj.get("name", "?"))
            per_class[name] = per_class.get(name, 0) + 1

    total = len(pcd_files)
    return {
        "total": total,
        "labelled": with_boxes,
        "empty": empty,
        "unlabelled": total - with_boxes - empty - unreadable,
        "unreadable": unreadable,
        "per_class": dict(sorted(per_class.items(), key=lambda item: -item[1])),
        "boxes": sum(per_class.values()),
        "label_folder": str(label_folder),
        "pointcloud_folder": str(pointcloud_folder),
    }


class StatisticsDialog(QtWidgets.QDialog):
    def __init__(self, parent, controller) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Dataset Statistics"))
        self.resize(460, 420)
        layout = QtWidgets.QVBoxLayout(self)

        pointcloud_folder = config.getpath("FILE", "pointcloud_folder")
        label_folder = config.getpath("FILE", "label_folder")

        summary = QtWidgets.QLabel(self.tr("Scanning %s ...") % label_folder)
        layout.addWidget(summary)
        QtWidgets.QApplication.processEvents()

        statistics = collect_statistics(pointcloud_folder, label_folder)
        rows = [
            (self.tr("Frames found"), statistics["total"]),
            (self.tr("Frames with boxes"), statistics["labelled"]),
            (self.tr("Frames confirmed empty"), statistics["empty"]),
            (self.tr("Frames not labelled yet"), statistics["unlabelled"]),
            (self.tr("Unreadable label files"), statistics["unreadable"]),
            (self.tr("Boxes in total"), statistics["boxes"]),
        ]

        table = QtWidgets.QTableWidget(len(rows), 2, self)
        table.setHorizontalHeaderLabels([self.tr("Item"), self.tr("Count")])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QtWidgets.QTableWidget.NoEditTriggers)
        for row, (label, value) in enumerate(rows):
            table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(label)))
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()
        layout.addWidget(table)

        per_class_label = QtWidgets.QLabel(self.tr("Boxes per class"))
        font = per_class_label.font()
        font.setBold(True)
        per_class_label.setFont(font)
        layout.addWidget(per_class_label)

        per_class_table = QtWidgets.QTableWidget(
            max(len(statistics["per_class"]), 1), 2, self
        )
        per_class_table.setHorizontalHeaderLabels([self.tr("Class"), self.tr("Boxes")])
        per_class_table.verticalHeader().setVisible(False)
        per_class_table.setEditTriggers(QtWidgets.QTableWidget.NoEditTriggers)
        for row, (name, count) in enumerate(statistics["per_class"].items()):
            per_class_table.setItem(row, 0, QtWidgets.QTableWidgetItem(name))
            per_class_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(count)))
        per_class_table.resizeColumnsToContents()
        layout.addWidget(per_class_table)

        pending = controller.bbox_controller.candidate_count()
        frame_info = QtWidgets.QLabel(
            self.tr("This frame: %s boxes, %s of them unconfirmed proposals.")
            % (len(controller.bbox_controller.bboxes), pending)
        )
        layout.addWidget(frame_info)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        logging.info("Dataset statistics: %s", statistics)
