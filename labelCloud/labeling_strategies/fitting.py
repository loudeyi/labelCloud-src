"""Click-to-fit: pick a point on a pole or wire and get a fitted box.

This is the strategy behind the "Fit Box" button and Ctrl+G. Unlike the picking
strategy — which drops a fixed-size 0.75 x 0.55 x 0.15 m box at the cursor — it
grows a region around the clicked point and fits an oriented box of the current
class, using the size template and the conventions described in
``control/assist.py``.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..control import assist
from ..definitions import Mode, Point3D
from ..io.labels.config import LabelConfig
from ..model import BBox
from . import BaseLabelingStrategy

if TYPE_CHECKING:
    from ..view.gui import GUI


class FittingStrategy(BaseLabelingStrategy):
    POINTS_NEEDED = 1
    PREVIEW = False
    #: Stay active after a successful fit so objects can be labelled one click
    #: after another (see DrawingManager.register_point).
    STICKY = True

    def __init__(self, view: "GUI") -> None:
        super().__init__(view)
        logging.info("Enabled click-to-fit mode.")
        self.view.status_manager.update_status(
            "Click a pole or a wire to fit a box around it.", mode=Mode.DRAWING
        )
        self.fitted_bbox: BBox = None  # type: ignore[assignment]
        self.failed = False

    def register_point(self, new_point: Point3D) -> None:
        self.point_1 = new_point
        self.points_registered += 1
        self._fit(new_point)

    def _fit(self, point: Point3D) -> None:
        controller = self.view.controller
        pointcloud = controller.pcd_manager.pointcloud
        if pointcloud is None:
            self.failed = True
            return

        classname = (
            controller.bbox_controller.get_classname()
            if controller.bbox_controller.has_active_bbox()
            else controller.new_box_class()
        )
        seed_index = assist.nearest_point_index(pointcloud.points, point)
        if seed_index is None:
            self.failed = True
            return

        fitted = assist.fit_box(pointcloud.points, seed_index, classname)
        if fitted is None:
            self.failed = True
            self.view.status_manager.set_message(
                "Could not fit a box here - try clicking directly on the object."
            )
            return
        self.fitted_bbox = fitted

    def get_bbox(self) -> BBox:
        return self.fitted_bbox

    def reset(self) -> None:
        super().reset()
        self.fitted_bbox = None  # type: ignore[assignment]
        self.failed = False
        # the button stays pressed on purpose: the mode is sticky so several
        # objects can be fitted in a row
