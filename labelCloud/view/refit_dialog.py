"""Ctrl+R refit settings, editable from the interface.

Two complaints shaped these knobs:

* the refit used to **miss points** that sat just outside the box, so the box stayed
  too small — ``grow_margin`` and ``max_link_distance`` decide how far the search
  reaches and what still counts as the same object;
* it used to **cover stretches with no points** — ``max_empty_gap`` trims those off,
  and ``min_cluster_points`` ignores detached specks.
"""
from __future__ import annotations

import logging

from PyQt5 import QtWidgets

from ..control.assist import (
    DEFAULT_GROW_MARGIN,
    DEFAULT_MAX_EMPTY_GAP,
    DEFAULT_MAX_LINK_DISTANCE,
    DEFAULT_MIN_CLUSTER_POINTS,
)
from ..control.config_manager import config

SECTION = "REFIT"


class RefitSettingsDialog(QtWidgets.QDialog):
    """How far the refit looks, and when it stops covering empty space."""

    def __init__(self, parent, controller) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle(self.tr("Refit Settings"))
        self.resize(470, 380)
        layout = QtWidgets.QVBoxLayout(self)

        def add_spin(label, key, minimum, maximum, step, fallback, suffix=" m", decimals=2):
            row = QtWidgets.QHBoxLayout()
            row.addWidget(QtWidgets.QLabel(label))
            spin = QtWidgets.QDoubleSpinBox(self)
            spin.setRange(minimum, maximum)
            spin.setSingleStep(step)
            spin.setDecimals(decimals)
            spin.setSuffix(suffix)
            spin.setValue(config.getfloat(SECTION, key, fallback=fallback))
            row.addWidget(spin)
            layout.addLayout(row)
            return spin

        self.spin_margin = add_spin(
            self.tr("Look this far beyond the box:"),
            "grow_margin", 0.0, 5.0, 0.1, DEFAULT_GROW_MARGIN,
        )
        self.spin_link = add_spin(
            self.tr("A point further than this is not part of the object:"),
            "max_link_distance", 0.05, 10.0, 0.05, DEFAULT_MAX_LINK_DISTANCE,
        )
        self.spin_gap = add_spin(
            self.tr("Trim empty stretches longer than:"),
            "max_empty_gap", 0.1, 20.0, 0.1, DEFAULT_MAX_EMPTY_GAP,
        )

        points_row = QtWidgets.QHBoxLayout()
        points_row.addWidget(
            QtWidgets.QLabel(self.tr("Ignore clusters smaller than:"))
        )
        self.spin_points = QtWidgets.QSpinBox(self)
        self.spin_points.setRange(1, 500)
        self.spin_points.setSuffix(self.tr(" points"))
        self.spin_points.setValue(
            config.getint(SECTION, "min_cluster_points", fallback=DEFAULT_MIN_CLUSTER_POINTS)
        )
        points_row.addWidget(self.spin_points)
        layout.addLayout(points_row)

        self.check_cross_section = QtWidgets.QCheckBox(
            self.tr("Also re-fit the cross-section (off keeps the size you set)")
        )
        self.check_cross_section.setChecked(
            config.getboolean(SECTION, "refit_cross_section", fallback=False)
        )
        layout.addWidget(self.check_cross_section)

        hint = QtWidgets.QLabel(
            self.tr(
                "Raise \"look beyond the box\" and \"not part of the object\" when the "
                "refit leaves points out; lower \"trim empty stretches\" when the box "
                "covers a section without points. Ctrl+Shift+R applies the settings to "
                "the active box."
            )
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        layout.addWidget(hint)

        reset_row = QtWidgets.QHBoxLayout()
        button_reset = QtWidgets.QPushButton(self.tr("Restore defaults"), self)
        button_reset.clicked.connect(self.restore_defaults)
        reset_row.addWidget(button_reset)
        reset_row.addStretch(1)
        layout.addLayout(reset_row)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def restore_defaults(self) -> None:
        self.spin_margin.setValue(DEFAULT_GROW_MARGIN)
        self.spin_link.setValue(DEFAULT_MAX_LINK_DISTANCE)
        self.spin_gap.setValue(DEFAULT_MAX_EMPTY_GAP)
        self.spin_points.setValue(DEFAULT_MIN_CLUSTER_POINTS)
        self.check_cross_section.setChecked(False)

    def accept(self) -> None:  # noqa: D102 - QDialog API
        from ..control.config_manager import config_manager

        config.set(SECTION, "grow_margin", str(self.spin_margin.value()))
        config.set(SECTION, "max_link_distance", str(self.spin_link.value()))
        config.set(SECTION, "max_empty_gap", str(self.spin_gap.value()))
        config.set(SECTION, "min_cluster_points", str(self.spin_points.value()))
        config.set(
            SECTION, "refit_cross_section", str(self.check_cross_section.isChecked())
        )
        config_manager.write_into_file()
        logging.info(
            "Refit settings saved: margin=%s link=%s gap=%s min_points=%s cross_section=%s",
            self.spin_margin.value(),
            self.spin_link.value(),
            self.spin_gap.value(),
            self.spin_points.value(),
            self.check_cross_section.isChecked(),
        )
        self.controller.refit_active_box_with_feedback()
        super().accept()
