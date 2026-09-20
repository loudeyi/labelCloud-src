"""Run the multi-frame label passes in background threads.

Walking dozens of frames means reading a point cloud and writing a label file per
frame, which must not block the interface. Both passes (carry a box forward, fill the
frames between two keyframes) share the same plumbing: the thread owns the readers and
writers — reusing the point-cloud handler and the label format the application uses, so
the per-file encoding guard and the backup copy apply to every write — and reports
progress back through signals.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from ..io.pointclouds import BasePointCloudHandler
from ..model.bbox import BBox
from .config_manager import config
from .prediction import PointHistory
from .propagate import DEFAULT_MAX_FRAMES, PropagateOutcome, propagate_box


class LabelPassWorker(QThread):
    """Shared plumbing of the passes that write boxes into several frames."""

    #: index, total, written
    progress = pyqtSignal(int, int, int)
    finished_ok = pyqtSignal(object)  # the pass's outcome object
    failed = pyqtSignal(str)

    #: used in log messages ("Propagation could not read ...")
    pass_name = "Pass"

    def __init__(self, frames: List[Path], label_manager, parent=None) -> None:
        super().__init__(parent)
        self.frames = frames
        self.label_manager = label_manager
        self._cancelled = False

    def cancel(self) -> None:
        """Ask the running pass to stop after the frame it is working on."""
        self._cancelled = True

    # -- the readers/writers the pure logic needs --------------------------- #
    def _read_points(self, path: Path):
        if self._cancelled:
            return None
        try:
            handler = BasePointCloudHandler.get_handler(path.suffix)
            # the handler returns (points, colors); only the points are needed here
            points, _colors = handler.read_point_cloud(path=path)
            return points
        except Exception as error:  # noqa: BLE001 - a broken frame is skipped
            logging.warning("%s could not read %s: %s", self.pass_name, path.name, error)
            return None

    def _read_boxes(self, path: Path) -> List[BBox]:
        try:
            return self.label_manager.import_labels(path)
        except Exception as error:  # noqa: BLE001
            logging.warning(
                "%s could not read the labels of %s: %s", self.pass_name, path.name, error
            )
            return []

    def _write_boxes(self, path: Path, boxes: List[BBox]) -> None:
        # goes through the normal export path, so a file stored in another encoding
        # is refused and a .bak copy is kept
        self.label_manager.export_labels(path, boxes)

    def _report_progress(self, index: int, total: int, written: int) -> None:
        self.progress.emit(index, total, written)


class InterpolationWorker(LabelPassWorker):
    """Fill the frames between two keyframes in the background."""

    pass_name = "Interpolation"

    def __init__(self, anchor, target, frames, label_manager, parent=None) -> None:
        super().__init__(frames, label_manager, parent)
        self.anchor = anchor
        self.target = target

    def run(self) -> None:  # noqa: D102 - QThread entry point
        from .interpolate import interpolate_between

        try:
            outcome = interpolate_between(
                self.anchor,
                self.target,
                self.frames,
                read_points=self._read_points,
                read_boxes=self._read_boxes,
                write_boxes=self._write_boxes,
                refit=config.getboolean("LABEL", "propagate_refit", fallback=True),
                min_points=config.getint("LABEL", "predict_min_points", fallback=5),
                progress=self._report_progress,
            )
            if self._cancelled:
                outcome.reason = "cancelled"
            self.finished_ok.emit(outcome)
        except Exception as error:  # noqa: BLE001
            logging.error("Interpolation failed: %s", error, exc_info=True)
            self.failed.emit(str(error))


class PropagateWorker(LabelPassWorker):
    """Follow one box through the frames after the current one."""

    pass_name = "Propagation"

    def __init__(self, box: BBox, history: PointHistory, frames: List[Path], label_manager, parent=None) -> None:
        super().__init__(frames, label_manager, parent)
        self.box = box
        self.history = history

    def run(self) -> None:  # noqa: D102 - QThread entry point
        try:
            outcome: PropagateOutcome = propagate_box(
                self.box,
                self.history,
                self.frames,
                read_points=self._read_points,
                read_boxes=self._read_boxes,
                write_boxes=self._write_boxes,
                ratio=config.getfloat("LABEL", "predict_min_point_ratio", fallback=0.5),
                min_points=config.getint("LABEL", "predict_min_points", fallback=5),
                sensitivity=config.getfloat("LABEL", "predict_sensitivity", fallback=1.5),
                adaptive=config.getboolean("LABEL", "predict_adaptive", fallback=True),
                use_motion=config.getboolean("LABEL", "predict_use_motion", fallback=True),
                refit=config.getboolean("LABEL", "propagate_refit", fallback=True),
                max_frames=config.getint(
                    "LABEL", "propagate_max_frames", fallback=DEFAULT_MAX_FRAMES
                ),
                progress=self._report_progress,
            )
            if self._cancelled:
                outcome.reason = "cancelled"
            self.finished_ok.emit(outcome)
        except Exception as error:  # noqa: BLE001 - reported to the UI
            logging.error("Propagation failed: %s", error, exc_info=True)
            self.failed.emit(str(error))
