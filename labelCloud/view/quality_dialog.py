"""F-27: the quality check a dataset needs before it is handed over.

The rules live in :mod:`labelCloud.control.quality`; this is the window around them.
It scans the whole point cloud folder when it opens (label files only, so it stays
fast), lists every suspicious box sorted by frame, and jumps to the frame when a row is
double-clicked — because the only useful reaction to "this pole is 3x the usual height"
is to look at it.

The dialog is deliberately read-only: it never edits or rewrites labels, and it re-scans
on demand so a fix can be verified immediately.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from typing import Dict, List, Optional

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QCoreApplication

from ..control.config_manager import config
from ..control.quality import (
    DETAIL_TEMPLATES,
    KIND_ORDER,
    QualityReport,
    QualitySettings,
    check_dataset,
    read_label_file,
)
from ..io.labels.config import LabelConfig

#: Human wording for every issue kind (also the filter entries of the combo box).
KIND_LABELS = {
    "unknown_class": "Class not in _classes.json",
    "degenerate": "Impossible size",
    "not_upright": "Tilted although the class is upright",
    "axis_convention": "Long axis in length instead of width",
    "size_outlier": "Size far from the usual size of its class",
    "duplicate": "Duplicate or overlapping box",
    "few_points": "Covers (almost) no points",
    "unreadable": "Label file cannot be read",
}


def class_rules() -> Dict[str, object]:
    """The class configuration, translated into the vocabulary of the checks."""
    label_config = LabelConfig()
    classes = label_config.get_classes()
    upright: List[str] = [
        name for name in classes if label_config.is_z_rotation_only(name)
    ]
    width_axis: List[str] = []
    for name, class_config in classes.items():
        dimensions = class_config.default_dimensions or {}
        length = dimensions.get("length") or 0.0
        width = dimensions.get("width") or 0.0
        if width > length > 0.0:
            # a cable-shaped template: the long axis belongs in ``width``
            width_axis.append(name)
    return {
        "known_classes": set(classes),
        "upright_classes": upright,
        "width_axis_classes": width_axis,
    }


#: Label folders the check can read. Everything else is refused with a message
#: instead of reporting every frame as unreadable.
READABLE_FORMATS = ("centroid_abs", "centroid_rel")


def make_reader(label_folder, relative_rotation: bool):
    """A read-only reader for the ``centroid`` JSON files of a folder.

    Deliberately *not* ``LabelManager.import_labels``: that one registers class names
    it meets, which rewrites ``_classes.json`` — and the quality check promises to
    change nothing at all. Reading the JSON directly also keeps a broken file an
    error (reported as *unreadable*) instead of a silently empty frame.
    """
    ending = ".json"

    def read(pcd_path):
        label_path = label_folder.joinpath(pcd_path.stem + ending)
        if not label_path.is_file():
            return []
        return read_label_file(label_path, rotations_in_radians=relative_rotation)

    return read


def scan(controller, check_points: bool = True) -> QualityReport:
    """Check the folder that is open in the application."""
    label_config = LabelConfig()
    if label_config.format not in READABLE_FORMATS:
        raise ValueError(
            QCoreApplication.translate(
                "QualityDialog",
                "the quality check reads 'centroid' JSON labels; this session uses "
                "'%s'"
            )
            % label_config.format
        )
    rules = class_rules()
    frames = list(controller.pcd_manager.pcds)
    current = controller.pcd_manager.current_id
    points = None
    if check_points and 0 <= current < len(frames):
        pointcloud = getattr(controller.pcd_manager, "pointcloud", None)
        points = getattr(pointcloud, "points", None)
    settings = QualitySettings.from_config(config)
    if not check_points:
        settings = replace(settings, min_points=0)
    return check_dataset(
        frames,
        make_reader(
            controller.pcd_manager.label_manager.label_folder,
            relative_rotation=label_config.format == "centroid_rel",
        ),
        known_classes=rules["known_classes"],
        upright_classes=rules["upright_classes"],
        width_axis_classes=rules["width_axis_classes"],
        settings=settings,
        current_frame=current,
        current_points=points,
    )


class QualityDialog(QtWidgets.QDialog):
    def __init__(self, parent, controller) -> None:
        super().__init__(parent)
        self.controller = controller
        self.report: Optional[QualityReport] = None
        self.setWindowTitle(self.tr("Quality Check"))
        self.resize(960, 560)
        layout = QtWidgets.QVBoxLayout(self)

        self.summary = QtWidgets.QLabel(self.tr("Scanning the label files ..."))
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(QtWidgets.QLabel(self.tr("Show")))
        self.kind_combo = QtWidgets.QComboBox()
        self.kind_combo.addItem(self.tr("All issues"), "all")
        for kind in KIND_ORDER:
            self.kind_combo.addItem(self.tr(KIND_LABELS[kind]), kind)
        self.kind_combo.currentIndexChanged.connect(self.populate)
        controls.addWidget(self.kind_combo)
        self.points_checkbox = QtWidgets.QCheckBox(
            self.tr("Check the points of the current frame (slower)")
        )
        self.points_checkbox.setChecked(min_points_enabled(controller))
        self.points_checkbox.stateChanged.connect(lambda _state: self.rescan())
        controls.addWidget(self.points_checkbox)
        controls.addStretch(1)
        self.rescan_button = QtWidgets.QPushButton(self.tr("Check again"))
        self.rescan_button.clicked.connect(self.rescan)
        controls.addWidget(self.rescan_button)
        layout.addLayout(controls)

        self.table = QtWidgets.QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(
            [
                self.tr("Frame"),
                self.tr("File"),
                self.tr("Class"),
                self.tr("Issue"),
                self.tr("Detail"),
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QTableWidget.SelectRows)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemDoubleClicked.connect(lambda _item: self.go_to_selected())
        layout.addWidget(self.table)

        buttons = QtWidgets.QDialogButtonBox(self)
        self.go_button = buttons.addButton(
            self.tr("Go to Frame"), QtWidgets.QDialogButtonBox.ActionRole
        )
        self.go_button.clicked.connect(self.go_to_selected)
        self.go_button.setEnabled(False)
        close_button = buttons.addButton(QtWidgets.QDialogButtonBox.Close)
        close_button.setText(self.tr("Close"))
        close_button.clicked.connect(self.reject)
        self.table.itemSelectionChanged.connect(
            lambda: self.go_button.setEnabled(bool(self.table.selectedItems()))
        )
        layout.addWidget(buttons)

        self.rescan()

    # ------------------------------------------------------------------ #
    def rescan(self) -> None:
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            self.report = scan(
                self.controller, check_points=self.points_checkbox.isChecked()
            )
        except Exception as error:  # noqa: BLE001 - the dialog stays usable
            logging.error("Quality check failed: %s", error, exc_info=True)
            self.summary.setText(self.tr("The check failed: %s") % error)
            return
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

        counts = self.report.counts_by_kind()
        parts = [
            self.tr("%s of %s frames hold boxes (%s boxes)")
            % (self.report.frames_labelled, self.report.frames, self.report.boxes),
            self.tr("Frames with at least one issue: %s")
            % self.report.frames_with_issues(),
        ]
        for kind in KIND_ORDER:
            if counts.get(kind):
                parts.append("%s: %s" % (self.tr(KIND_LABELS[kind]), counts[kind]))
        self.summary.setText("  ·  ".join(parts) + "<br/>" + self.tr(
            "Double-click a row (or press Go to Frame) to open that frame. "
            "The check never edits your labels."
        ))
        self.populate()

    def populate(self) -> None:
        if self.report is None:
            return
        wanted = self.kind_combo.currentData()
        issues = [
            issue
            for issue in self.report.issues
            if wanted in (None, "all") or issue.kind == wanted
        ]
        self.table.setRowCount(len(issues))
        for row, issue in enumerate(issues):
            frame_item = QtWidgets.QTableWidgetItem(str(issue.frame + 1))
            frame_item.setData(QtCore.Qt.UserRole, issue.frame)
            self.table.setItem(row, 0, frame_item)
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(issue.filename))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(issue.classname))
            self.table.setItem(
                row, 3, QtWidgets.QTableWidgetItem(self.tr(KIND_LABELS[issue.kind]))
            )
            self.table.setItem(
                row, 4, QtWidgets.QTableWidgetItem(self.describe(issue))
            )
        self.table.resizeColumnsToContents()
        self.kind_combo.setEnabled(True)

    def describe(self, issue) -> str:
        """The issue in the user's language (the module builds the numbers only)."""
        template = DETAIL_TEMPLATES.get(issue.detail_key or issue.kind)
        if template is None:
            return issue.detail
        try:
            return self.tr(template) % issue.params
        except (KeyError, TypeError, ValueError):  # pragma: no cover - defensive
            return issue.detail

    def go_to_selected(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        frame = self.table.item(items[0].row(), 0).data(QtCore.Qt.UserRole)
        if frame is None:
            return
        self.controller.cmd_go_to_frame(int(frame))
        self.accept()


def min_points_enabled(controller) -> bool:
    """The point rule needs the current frame's points; it is only worth it if loaded."""
    pointcloud = getattr(controller.pcd_manager, "pointcloud", None)
    return getattr(pointcloud, "points", None) is not None
