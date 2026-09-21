"""Next-frame prediction settings, editable from the interface.

The prediction thresholds decide when a box stops being carried into the next
frame. They are the difference between "it does nothing" and "it works", so they
belong in the interface rather than only in ``config.ini``:

* **adaptive** (default) compares a box's point count with *its own* recent history
  (an exponential moving average), so a pole that is progressively occluded by a
  tree is still followed while a pole that leaves the field of view — whose count
  collapses — is dropped;
* **fixed ratio** asks for a share of the previous frame's count, for example 50 %
  ("halved → drop");
* an absolute minimum count always applies, so a box holding two stray points is
  never predicted.
"""
from __future__ import annotations

import logging

from PyQt5 import QtWidgets

from ..control.config_manager import config
from ..control.prediction import (
    DEFAULT_MIN_POINTS,
    DEFAULT_RATIO,
    DEFAULT_SENSITIVITY,
)
from ..control.propagate import DEFAULT_MAX_FRAMES

SECTION = "LABEL"


class PredictionSettingsDialog(QtWidgets.QDialog):
    """Enable/disable prediction and tune when a box is dropped."""

    def __init__(self, parent, controller) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle(self.tr("Next-Frame Prediction"))
        self.resize(460, 420)
        layout = QtWidgets.QVBoxLayout(self)

        self.check_enabled = QtWidgets.QCheckBox(
            self.tr("Carry boxes into the next frame")
        )
        self.check_enabled.setChecked(
            config.getboolean(SECTION, "predict_next_frame", fallback=False)
        )
        layout.addWidget(self.check_enabled)

        self.check_candidates = QtWidgets.QCheckBox(
            self.tr("Show them as unconfirmed proposals (Enter confirms)")
        )
        self.check_candidates.setChecked(
            config.getboolean(SECTION, "predict_as_candidates", fallback=True)
        )
        layout.addWidget(self.check_candidates)

        self.check_refit = QtWidgets.QCheckBox(
            self.tr("Re-fit each prediction to the points inside it")
        )
        self.check_refit.setChecked(
            config.getboolean(SECTION, "predict_refit", fallback=True)
        )
        layout.addWidget(self.check_refit)

        line = QtWidgets.QFrame(self)
        line.setFrameShape(QtWidgets.QFrame.HLine)
        layout.addWidget(line)

        self.check_adaptive = QtWidgets.QCheckBox(
            self.tr("Adaptive threshold (compare with the object's own history)")
        )
        self.check_adaptive.setChecked(
            config.getboolean(SECTION, "predict_adaptive", fallback=True)
        )
        layout.addWidget(self.check_adaptive)

        sensitivity_row = QtWidgets.QHBoxLayout()
        sensitivity_row.addWidget(
            QtWidgets.QLabel(self.tr("Adaptive sensitivity (mean - k x deviation):"))
        )
        self.spin_sensitivity = QtWidgets.QDoubleSpinBox(self)
        self.spin_sensitivity.setRange(0.5, 5.0)
        self.spin_sensitivity.setSingleStep(0.5)
        self.spin_sensitivity.setValue(
            config.getfloat(SECTION, "predict_sensitivity", fallback=DEFAULT_SENSITIVITY)
        )
        sensitivity_row.addWidget(self.spin_sensitivity)
        layout.addLayout(sensitivity_row)

        ratio_row = QtWidgets.QHBoxLayout()
        ratio_row.addWidget(
            QtWidgets.QLabel(self.tr("Drop when fewer than this share of the previous points:"))
        )
        self.spin_ratio = QtWidgets.QSpinBox(self)
        self.spin_ratio.setRange(5, 100)
        self.spin_ratio.setSuffix(" %")
        self.spin_ratio.setValue(
            int(
                round(
                    100
                    * config.getfloat(
                        SECTION, "predict_min_point_ratio", fallback=DEFAULT_RATIO
                    )
                )
            )
        )
        ratio_row.addWidget(self.spin_ratio)
        layout.addLayout(ratio_row)

        points_row = QtWidgets.QHBoxLayout()
        points_row.addWidget(
            QtWidgets.QLabel(self.tr("... and always below this absolute count:"))
        )
        self.spin_points = QtWidgets.QSpinBox(self)
        self.spin_points.setRange(1, 1000)
        self.spin_points.setValue(
            config.getint(SECTION, "predict_min_points", fallback=DEFAULT_MIN_POINTS)
        )
        points_row.addWidget(self.spin_points)
        layout.addLayout(points_row)

        self.check_over_existing = QtWidgets.QCheckBox(
            self.tr("Predict even when the frame already has its own labels")
        )
        self.check_over_existing.setChecked(
            config.getboolean(SECTION, "predict_over_existing", fallback=False)
        )
        layout.addWidget(self.check_over_existing)

        self.check_motion = QtWidgets.QCheckBox(
            self.tr("Follow the object's motion (extrapolate from the last frames)")
        )
        self.check_motion.setChecked(
            config.getboolean(SECTION, "predict_use_motion", fallback=True)
        )
        layout.addWidget(self.check_motion)

        propagate_row = QtWidgets.QHBoxLayout()
        propagate_row.addWidget(
            QtWidgets.QLabel(self.tr("Carry forward writes this many frames:"))
        )
        self.spin_propagate = QtWidgets.QSpinBox(self)
        self.spin_propagate.setRange(1, 100)
        self.spin_propagate.setValue(
            config.getint(SECTION, "propagate_max_frames", fallback=DEFAULT_MAX_FRAMES)
        )
        propagate_row.addWidget(self.spin_propagate)
        layout.addLayout(propagate_row)

        hint = QtWidgets.QLabel(
            self.tr(
                "Example: with 50 %, a pole whose points halve between two frames is "
                "dropped, so it is not predicted once it is behind the vehicle. The "
                "adaptive threshold follows each object separately and is usually the "
                "better choice."
            )
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        layout.addWidget(hint)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel, self
        )
        # Qt's own catalogue is not shipped with the application, so the standard
        # buttons are named here (otherwise a Chinese session shows OK / Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.Ok).setText(self.tr("OK"))
        buttons.button(QtWidgets.QDialogButtonBox.Cancel).setText(self.tr("Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:  # noqa: D102 - QDialog API
        from ..control.config_manager import config_manager

        config.set(SECTION, "predict_next_frame", str(self.check_enabled.isChecked()))
        config.set(
            SECTION, "predict_as_candidates", str(self.check_candidates.isChecked())
        )
        config.set(SECTION, "predict_refit", str(self.check_refit.isChecked()))
        config.set(SECTION, "predict_adaptive", str(self.check_adaptive.isChecked()))
        config.set(SECTION, "predict_sensitivity", str(self.spin_sensitivity.value()))
        config.set(
            SECTION, "predict_min_point_ratio", str(self.spin_ratio.value() / 100.0)
        )
        config.set(SECTION, "predict_min_points", str(self.spin_points.value()))
        config.set(
            SECTION, "predict_over_existing", str(self.check_over_existing.isChecked())
        )
        config.set(SECTION, "predict_use_motion", str(self.check_motion.isChecked()))
        config.set(SECTION, "propagate_max_frames", str(self.spin_propagate.value()))
        config_manager.write_into_file()
        logging.info(
            "Prediction settings saved: enabled=%s adaptive=%s ratio=%.2f min_points=%s",
            self.check_enabled.isChecked(),
            self.check_adaptive.isChecked(),
            self.spin_ratio.value() / 100.0,
            self.spin_points.value(),
        )
        self.controller.refresh_prediction_state()
        super().accept()
