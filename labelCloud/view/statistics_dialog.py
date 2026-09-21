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

import logging
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

from PyQt5 import QtWidgets
from PyQt5.QtCore import QCoreApplication

from ..control.config_manager import config
from ..control.quality import read_label_file
from ..io.labels.config import LabelConfig
from ..io.pointclouds import BasePointCloudHandler


def collect_statistics(
    pointcloud_folder: Path,
    label_folder: Path,
    limit: int = 20000,
    extensions: Optional[set] = None,
    label_ending: str = ".json",
    read_labels=None,
) -> Dict[str, object]:
    """Scan both folders and summarise the labelling progress.

    The point cloud extensions come from the handlers rather than being hard-coded, so
    a folder of ``.ply`` clouds is counted like one of ``.pcd`` files. ``read_labels``
    defaults to the plain JSON reader the quality check also uses; a KITTI (``.txt``)
    session passes the label manager instead, because its files are not JSON.
    """
    suffixes = extensions or BasePointCloudHandler.get_supported_extensions()
    pcd_files = sorted(
        path for path in pointcloud_folder.rglob("*") if path.suffix in suffixes
    )[:limit]

    reader = read_labels or (
        lambda pcd_path: read_label_file(
            label_folder.joinpath(pcd_path.stem + label_ending)
        )
    )

    with_boxes = 0
    empty = 0
    per_class: Dict[str, int] = {}
    unreadable = 0

    for pcd in pcd_files:
        if not label_folder.joinpath(pcd.stem + label_ending).is_file():
            continue  # never opened: not labelled yet
        try:
            boxes = reader(pcd)
        except (OSError, ValueError, KeyError, TypeError):
            unreadable += 1
            continue
        if not boxes:
            empty += 1
            continue
        with_boxes += 1
        for box in boxes:
            name = box.get_classname()
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


def manager_reader(label_manager):
    """A reader for sessions whose labels are not the centroid JSON ones.

    ``import_labels`` returns an empty list both for "nothing labelled here" and for
    "this file holds another encoding" (the format guard refuses to convert it). The
    statistics must not call the second case an empty frame, so a refusal is turned
    into an error here.
    """

    def read(pcd_path: Path):
        boxes = label_manager.import_labels(pcd_path)
        if pcd_path.stem in label_manager.format_guard.refusals:
            raise ValueError("another label format on disk")
        return boxes

    return read


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

        label_manager = controller.pcd_manager.label_manager
        ending = label_manager.label_strategy.FILE_ENDING
        # KITTI (.txt) and vertices folders need their own reader; centroid files are
        # read directly (no class registration, nothing written)
        reader = (
            None
            if LabelConfig().format in ("centroid_abs", "centroid_rel")
            else manager_reader(label_manager)
        )
        statistics = collect_statistics(
            pointcloud_folder,
            label_folder,
            label_ending=ending,
            read_labels=reader,
        )
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
        # the standard button's text comes from Qt's own catalogue, which this
        # application does not ship: name it here so a Chinese session is complete
        buttons.button(QtWidgets.QDialogButtonBox.Close).setText(self.tr("Close"))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        logging.info("Dataset statistics: %s", statistics)
