"""
A class to handle all user manipulations of the bounding boxes and collect all labeling
settings in one place.
Bounding Box Management: adding, selecting updating, deleting bboxes;
Possible Active Bounding Box Manipulations: rotation, translation, scaling
"""

import logging
import math
from functools import wraps
from typing import TYPE_CHECKING, List, Optional

import numpy as np

from ..definitions import Mode
from ..io.labels.config import LabelConfig
from ..model.bbox import BBox
from ..utils import oglhelper
from .config_manager import config
from .pcd_manager import PointCloudManger
from .undo import BBoxState, FrameState, UndoStack
from PyQt5.QtCore import QCoreApplication

if TYPE_CHECKING:
    from ..view.gui import GUI


# DECORATORS
def has_active_bbox_decorator(func):
    """
    Only execute bounding box manipulation if there is an active bounding box.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        if args[0].has_active_bbox():
            return func(*args, **kwargs)
        else:
            logging.warning("There is currently no active bounding box to manipulate.")

    return wrapper


def undoable(description: str, coalesce: Optional[str] = None):
    """Record the state before an edit, but only when the edit changed something.

    Comparing before/after keeps refused operations (locked dimensions, blocked
    tilt, no active box) off the undo stack, so Ctrl+Z always undoes something the
    user actually did.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if self.undo_suppressed:
                return func(self, *args, **kwargs)
            before = self.history_capture(description)
            result = func(self, *args, **kwargs)
            if not before.same_as(self.history_capture("")):
                self.history.record(before, description, coalesce)
                self.dirty = True
            return result

        return wrapper

    return decorator


def only_zrotation_decorator(func):
    """
    Only execute x- and y-rotation when the active box's class allows tilting.

    The permission is looked up per class (``_classes.json``), falling back to the
    global ``USER_INTERFACE/z_rotation_only`` option: a pole only ever needs yaw,
    while a sagging wire has to be tilted out of the ground plane.
    """

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        classname = self.get_classname() if self.has_active_bbox() else None
        if not LabelConfig().is_z_rotation_only(classname):
            return func(self, *args, **kwargs)
        logging.warning(
            "Rotations around the x- or y-axis are disabled for class '%s' "
            "(z_rotation_only). Set \"z_rotation_only\": false for that class in "
            "the class definition file to allow tilting.",
            classname,
        )

    return wrapper


class BoundingBoxController(object):
    STD_SCALING = config.getfloat("LABEL", "std_scaling")

    def __init__(self) -> None:
        self.view: GUI
        self.pcd_manager: PointCloudManger
        self.bboxes: List[BBox] = []
        self.active_bbox_id = -1  # -1 means zero bboxes
        #: Undo/redo history of the current frame (cleared on frame change).
        self.history = UndoStack()
        #: Copied box, kept across frames on purpose: pasting a pole or wire into
        #: the next frame is the fastest way to label a sequence.
        self.clipboard: Optional[BBoxState] = None
        #: Set while a mouse drag is running, so the whole drag collapses into a
        #: single undo step instead of one per mouse-move event.
        self.undo_suppressed = False
        #: True while the current frame has edits that are not on disk yet.
        self.dirty = False

    # GETTERS
    def has_active_bbox(self) -> bool:
        return 0 <= self.active_bbox_id < len(self.bboxes)

    def get_active_bbox(self) -> Optional[BBox]:
        if self.has_active_bbox():
            return self.bboxes[self.active_bbox_id]
        else:
            return None

    @has_active_bbox_decorator
    def get_classname(self) -> str:
        return self.get_active_bbox().get_classname()  # type: ignore

    # SETTERS

    def set_view(self, view: "GUI") -> None:
        self.view = view

    @undoable("Add bounding box")
    def add_bbox(self, bbox: BBox) -> None:
        if isinstance(bbox, BBox):
            self.bboxes.append(bbox)
            self.set_active_bbox(self.bboxes.index(bbox))
            self.view.current_class_dropdown.setCurrentText(
                self.get_active_bbox().classname  # type: ignore
            )
            self.view.status_manager.update_status(
                QCoreApplication.translate(
                    "labelCloud", "Bounding Box added, it can now be corrected."
                ), Mode.CORRECTION
            )

    def update_bbox(self, bbox_id: int, bbox: BBox) -> None:
        if isinstance(bbox, BBox) and (0 <= bbox_id < len(self.bboxes)):
            self.bboxes[bbox_id] = bbox
            self.update_label_list()

    @undoable("Delete bounding box")
    def delete_bbox(self, bbox_id: int) -> None:
        if 0 <= bbox_id < len(self.bboxes):
            del self.bboxes[bbox_id]
            if bbox_id == self.active_bbox_id:
                self.set_active_bbox(len(self.bboxes) - 1)
            else:
                self.update_label_list()

    def delete_current_bbox(self) -> None:
        selected_item_id = self.view.label_list.currentRow()
        self.delete_bbox(selected_item_id)

    def set_active_bbox(self, bbox_id: int) -> None:
        if 0 <= bbox_id < len(self.bboxes):
            self.active_bbox_id = bbox_id
            self.update_all()
            self.view.status_manager.update_status(
                QCoreApplication.translate(
                    "labelCloud", "Bounding Box selected, it can now be corrected."
                ), mode=Mode.CORRECTION
            )
        else:
            self.deselect_bbox()

    @undoable("Change class")
    @has_active_bbox_decorator
    def set_classname(self, new_class: str) -> None:
        self.get_active_bbox().set_classname(new_class)  # type: ignore
        self.update_label_list()

    @undoable("Move bounding box", coalesce="translate")
    @has_active_bbox_decorator
    def set_center(self, cx: float, cy: float, cz: float) -> None:
        self.get_active_bbox().center = (cx, cy, cz)  # type: ignore

    def set_bboxes(self, bboxes: List[BBox]) -> None:
        self.bboxes = bboxes
        self.dirty = False
        self.history.clear()  # never undo across a frame boundary
        self.deselect_bbox()
        self.update_label_list()

    def reset(self) -> None:
        self.deselect_bbox()
        self.set_bboxes([])

    def deselect_bbox(self) -> None:
        self.active_bbox_id = -1
        self.update_all()
        self.view.status_manager.set_mode(Mode.NAVIGATION)

    # MANIPULATORS
    @undoable("Edit position")
    @has_active_bbox_decorator
    def update_position(self, axis: str, value: float) -> None:
        if axis == "pos_x":
            self.get_active_bbox().set_x_translation(value)  # type: ignore
        elif axis == "pos_y":
            self.get_active_bbox().set_y_translation(value)  # type: ignore
        elif axis == "pos_z":
            self.get_active_bbox().set_z_translation(value)  # type: ignore
        else:
            raise Exception("Wrong axis describtion.")

    @undoable("Edit dimension")
    @has_active_bbox_decorator
    def update_dimension(self, dimension: str, value: float) -> None:
        if dimension == "length":
            self.get_active_bbox().set_length(value)  # type: ignore
        elif dimension == "width":
            self.get_active_bbox().set_width(value)  # type: ignore
        elif dimension == "height":
            self.get_active_bbox().set_height(value)  # type: ignore
        else:
            raise Exception("Wrong dimension describtion.")

    @undoable("Edit rotation")
    @has_active_bbox_decorator
    def update_rotation(self, axis: str, value: float) -> None:
        if axis == "rot_x":
            self.get_active_bbox().set_x_rotation(value)  # type: ignore
        elif axis == "rot_y":
            self.get_active_bbox().set_y_rotation(value)  # type: ignore
        elif axis == "rot_z":
            self.get_active_bbox().set_z_rotation(value)  # type: ignore
        else:
            raise Exception("Wrong axis describtion.")

    @only_zrotation_decorator
    @undoable("Rotate around x", coalesce="rotate")
    @has_active_bbox_decorator
    def rotate_around_x(
        self, dangle: Optional[float] = None, clockwise: bool = False
    ) -> None:
        dangle = dangle or config.getfloat("LABEL", "std_rotation")
        if clockwise:
            dangle *= -1
        self.get_active_bbox().set_x_rotation(  # type: ignore
            self.get_active_bbox().get_x_rotation() + dangle  # type: ignore
        )

    @only_zrotation_decorator
    @undoable("Rotate around y", coalesce="rotate")
    @has_active_bbox_decorator
    def rotate_around_y(
        self, dangle: Optional[float] = None, clockwise: bool = False
    ) -> None:
        dangle = dangle or config.getfloat("LABEL", "std_rotation")
        if clockwise:
            dangle *= -1
        self.get_active_bbox().set_y_rotation(  # type: ignore
            self.get_active_bbox().get_y_rotation() + dangle  # type: ignore
        )

    @undoable("Rotate around z", coalesce="rotate")
    @has_active_bbox_decorator
    def rotate_around_z(
        self,
        dangle: Optional[float] = None,
        clockwise: bool = False,
        absolute: bool = False,
    ) -> None:
        dangle = dangle or config.getfloat("LABEL", "std_rotation")
        if clockwise:
            dangle *= -1
        if absolute:
            self.get_active_bbox().set_z_rotation(dangle)  # type: ignore
        else:
            self.get_active_bbox().set_z_rotation(  # type: ignore
                self.get_active_bbox().get_z_rotation() + dangle  # type: ignore
            )
        self.update_all()

    @has_active_bbox_decorator
    def rotate_with_mouse(
        self, x_angle: float, y_angle: float
    ) -> None:  # TODO: Make more intuitive
        # Get bbox perspective
        assert self.pcd_manager.pointcloud is not None
        pcd_z_rotation = self.pcd_manager.pointcloud.rot_z
        bbox_z_rotation = self.get_active_bbox().get_z_rotation()  # type: ignore
        total_z_rotation = pcd_z_rotation + bbox_z_rotation

        bbox_cosz = round(np.cos(np.deg2rad(total_z_rotation)), 0)
        bbox_sinz = -round(np.sin(np.deg2rad(total_z_rotation)), 0)

        self.rotate_around_x(y_angle * bbox_cosz)
        self.rotate_around_y(y_angle * bbox_sinz)
        self.rotate_around_z(x_angle)

    @undoable("Move along x", coalesce="translate")
    @has_active_bbox_decorator
    def translate_along_x(
        self, distance: Optional[float] = None, left: bool = False
    ) -> None:
        distance = distance or config.getfloat("LABEL", "std_translation")
        if left:
            distance *= -1

        cosz, sinz, bu = self.pcd_manager.get_perspective()

        active_bbox: Bbox = self.get_active_bbox()  # type: ignore
        active_bbox.set_x_translation(active_bbox.center[0] + distance * cosz)
        active_bbox.set_y_translation(active_bbox.center[1] + distance * sinz)

    @undoable("Move along y", coalesce="translate")
    @has_active_bbox_decorator
    def translate_along_y(
        self, distance: Optional[float] = None, forward: bool = False
    ) -> None:
        distance = distance or config.getfloat("LABEL", "std_translation")
        if forward:
            distance *= -1

        cosz, sinz, bu = self.pcd_manager.get_perspective()

        active_bbox: Bbox = self.get_active_bbox()  # type: ignore
        active_bbox.set_x_translation(active_bbox.center[0] + distance * bu * -sinz)
        active_bbox.set_y_translation(active_bbox.center[1] + distance * bu * cosz)

    @undoable("Move along z", coalesce="translate")
    @has_active_bbox_decorator
    def translate_along_z(
        self, distance: Optional[float] = None, down: bool = False
    ) -> None:
        distance = distance or config.getfloat("LABEL", "std_translation")
        if down:
            distance *= -1

        active_bbox: Bbox = self.get_active_bbox()  # type: ignore
        active_bbox.set_z_translation(active_bbox.center[2] + distance)

    @undoable("Scale bounding box", coalesce="scale")
    @has_active_bbox_decorator
    def scale(
        self, length_increase: Optional[float] = None, decrease: bool = False
    ) -> None:
        """Scales a bounding box while keeping the previous aspect ratio.

        :param length_increase: factor by which the length should be increased
        :param decrease: if True, reverses the length_increasee (* -1)
        :return: None
        """
        if self.is_active_locked():
            self.warn_dimensions_locked()
            return
        length_increase = length_increase or config.getfloat("LABEL", "std_scaling")
        if decrease:
            length_increase *= -1
        length, width, height = self.get_active_bbox().get_dimensions()  # type: ignore
        width_length_ratio = width / length
        height_length_ratio = height / length

        new_length = length + length_increase
        new_width = new_length * width_length_ratio
        new_height = new_length * height_length_ratio

        self.get_active_bbox().set_dimensions(new_length, new_width, new_height)  # type: ignore

    @undoable("Scale length", coalesce="scale")
    @has_active_bbox_decorator
    def scale_along_length(
        self, step: Optional[float] = None, decrease: bool = False
    ) -> None:
        if self.is_active_locked():
            self.warn_dimensions_locked()
            return
        step = step or config.getfloat("LABEL", "std_scaling")
        if decrease:
            step *= -1

        active_bbox: Bbox = self.get_active_bbox()  # type: ignore
        length, width, height = active_bbox.get_dimensions()
        new_length = length + step
        active_bbox.set_dimensions(new_length, width, height)

    @undoable("Scale width", coalesce="scale")
    @has_active_bbox_decorator
    def scale_along_width(
        self, step: Optional[float] = None, decrease: bool = False
    ) -> None:
        if self.is_active_locked():
            self.warn_dimensions_locked()
            return
        step = step or config.getfloat("LABEL", "std_scaling")
        if decrease:
            step *= -1

        active_bbox: Bbox = self.get_active_bbox()  # type: ignore
        length, width, height = active_bbox.get_dimensions()
        new_width = width + step
        active_bbox.set_dimensions(length, new_width, height)

    @undoable("Scale height", coalesce="scale")
    @has_active_bbox_decorator
    def scale_along_height(
        self, step: Optional[float] = None, decrease: bool = False
    ) -> None:
        if self.is_active_locked():
            self.warn_dimensions_locked()
            return
        step = step or config.getfloat("LABEL", "std_scaling")
        if decrease:
            step *= -1

        active_bbox: Bbox = self.get_active_bbox()  # type: ignore
        length, width, height = active_bbox.get_dimensions()
        new_height = height + step
        active_bbox.set_dimensions(length, width, new_height)

    def select_bbox_by_ray(self, x: int, y: int) -> None:
        intersected_bbox_id = oglhelper.get_intersected_bboxes(
            x,
            y,
            self.bboxes,
            self.view.gl_widget.modelview,
            self.view.gl_widget.projection,
        )
        if intersected_bbox_id is not None:
            self.set_active_bbox(intersected_bbox_id)
            logging.info("Selected bounding box %s." % intersected_bbox_id)


    # UNDO / REDO

    def history_capture(self, description: str = "") -> FrameState:
        return FrameState.capture(self.bboxes, self.active_bbox_id, description)

    def _restore(self, state: FrameState) -> None:
        self.bboxes = [bbox_state.to_bbox() for bbox_state in state.bboxes]
        self.active_bbox_id = (
            state.active_id if 0 <= state.active_id < len(self.bboxes) else -1
        )
        self.update_all()
        if not self.bboxes:
            self.view.status_manager.set_mode(Mode.NAVIGATION)

    def undo(self) -> bool:
        """Restore the state before the last edit. Returns True if anything changed."""
        target = self.history.undo(self.history_capture())
        if target is None:
            return False
        self._restore(target)
        self.dirty = True
        return True

    def redo(self) -> bool:
        target = self.history.redo(self.history_capture())
        if target is None:
            return False
        self._restore(target)
        self.dirty = True
        return True

    # COPY / PASTE / DUPLICATE

    @has_active_bbox_decorator
    def copy_current_bbox(self) -> None:
        """Keep a copy of the active box; it survives switching frames."""
        self.clipboard = BBoxState.from_bbox(self.get_active_bbox())  # type: ignore[arg-type]
        logging.info("Copied bounding box for pasting (also in the next frame).")

    def paste_bbox(self) -> bool:
        """Paste the copied box next to the active one (or as the only box)."""
        if self.clipboard is None:
            logging.warning("Nothing to paste: copy a bounding box first.")
            return False

        before = self.history_capture("Paste bounding box")
        pasted = self.clipboard.to_bbox()
        self.bboxes.append(pasted)
        self.active_bbox_id = len(self.bboxes) - 1
        self.update_all()
        self.view.current_class_dropdown.setCurrentText(pasted.get_classname())
        self.history.record(before, "Paste bounding box")
        self.dirty = True
        return True

    @has_active_bbox_decorator
    def duplicate_current_bbox(self) -> None:
        """Copy + paste in place, ready to be nudged to the next object."""
        active = self.get_active_bbox()
        self.clipboard = BBoxState.from_bbox(active)  # type: ignore[arg-type]
        self.paste_bbox()

    # DIMENSION LOCK + CLASS TEMPLATE

    @undoable("Toggle dimension lock")
    @has_active_bbox_decorator
    def toggle_dimension_lock(self) -> None:
        bbox = self.get_active_bbox()
        bbox.locked = not bbox.locked  # type: ignore[union-attr]
        logging.info(
            "Dimensions of the active bounding box are now %s.",
            "locked" if bbox.locked else "unlocked",  # type: ignore[union-attr]
        )

    def is_active_locked(self) -> bool:
        bbox = self.get_active_bbox()
        return bool(bbox is not None and getattr(bbox, "locked", False))

    @undoable("Apply class template")
    @has_active_bbox_decorator
    def apply_template(self) -> None:
        """Apply the class's size template and upright orientation.

        A missing dimension in the template keeps the current value, so a pole
        template can fix the cross-section while the height stays whatever the
        structure needs.
        """
        bbox = self.get_active_bbox()
        classname = bbox.get_classname()  # type: ignore[union-attr]
        template = LabelConfig().get_default_dimensions(classname)
        if not template:
            logging.warning("Class '%s' has no size template defined.", classname)
            return

        length, width, height = bbox.get_dimensions()  # type: ignore[union-attr]
        if template.get("length"):
            length = float(template["length"])
        if template.get("width"):
            width = float(template["width"])
        if template.get("height"):
            height = float(template["height"])
        bbox.set_dimensions(length, width, height)  # type: ignore[union-attr]

        if LabelConfig().is_z_rotation_only(classname):
            bbox.set_x_rotation(0)  # type: ignore[union-attr]
            bbox.set_y_rotation(0)  # type: ignore[union-attr]
        logging.info(
            "Applied template %s to '%s': L%.2f W%.2f H%.2f.",
            template,
            classname,
            length,
            width,
            height,
        )

    # LOCAL-AXIS TRANSLATION (the box's own frame, not the view's)

    @undoable("Move along local axis", coalesce="translate")
    @has_active_bbox_decorator
    def translate_local(
        self,
        axis: str,
        distance: Optional[float] = None,
        negative: bool = False,
        factor: float = 1.0,
    ) -> None:
        """Move the box along its own x/y axis.

        The view-aligned WASD keys become useless as soon as a box is rotated;
        poles and wires are usually long and rotated, so nudging has to follow the
        box, not the camera.
        """
        distance = distance or config.getfloat("LABEL", "std_translation")
        distance *= factor
        if negative:
            distance *= -1

        bbox = self.get_active_bbox()
        yaw = math.radians(bbox.get_z_rotation())  # type: ignore[union-attr]
        if axis == "x":
            dx, dy = math.cos(yaw), math.sin(yaw)
        elif axis == "y":
            dx, dy = -math.sin(yaw), math.cos(yaw)
        else:
            raise Exception("Local translation only supports the x- and y-axis.")

        bbox.set_x_translation(bbox.center[0] + distance * dx)  # type: ignore[union-attr]
        bbox.set_y_translation(bbox.center[1] + distance * dy)  # type: ignore[union-attr]

    # RELATIVE NUDGES (numeric panel, ± buttons)

    @undoable("Edit position", coalesce="nudge-position")
    @has_active_bbox_decorator
    def nudge_position(self, axis: str, delta: float) -> None:
        bbox = self.get_active_bbox()
        if axis == "pos_x":
            bbox.set_x_translation(bbox.center[0] + delta)  # type: ignore[union-attr]
        elif axis == "pos_y":
            bbox.set_y_translation(bbox.center[1] + delta)  # type: ignore[union-attr]
        elif axis == "pos_z":
            bbox.set_z_translation(bbox.center[2] + delta)  # type: ignore[union-attr]

    @undoable("Edit dimension", coalesce="nudge-dimension")
    @has_active_bbox_decorator
    def nudge_dimension(self, dimension: str, delta: float) -> None:
        if self.is_active_locked():
            self.warn_dimensions_locked()
            return
        current = dict(
            zip(("length", "width", "height"), self.get_active_bbox().get_dimensions())  # type: ignore[union-attr]
        )
        value = current.get(dimension, 0.0) + delta
        if value <= BBox.MIN_DIMENSION:
            logging.warning("New dimension is too small.")
            return
        current[dimension] = value
        self.get_active_bbox().set_dimensions(  # type: ignore[union-attr]
            current["length"], current["width"], current["height"]
        )

    @undoable("Edit rotation", coalesce="nudge-rotation")
    @has_active_bbox_decorator
    def nudge_rotation(self, axis: str, delta: float) -> None:
        bbox = self.get_active_bbox()
        if axis == "rot_x":
            if LabelConfig().is_z_rotation_only(bbox.get_classname()):  # type: ignore[union-attr]
                logging.warning("Tilting is disabled for this class.")
                return
            bbox.set_x_rotation(bbox.get_x_rotation() + delta)  # type: ignore[union-attr]
        elif axis == "rot_y":
            if LabelConfig().is_z_rotation_only(bbox.get_classname()):  # type: ignore[union-attr]
                logging.warning("Tilting is disabled for this class.")
                return
            bbox.set_y_rotation(bbox.get_y_rotation() + delta)  # type: ignore[union-attr]
        elif axis == "rot_z":
            bbox.set_z_rotation(bbox.get_z_rotation() + delta)  # type: ignore[union-attr]

    # MOUSE DRAG SUPPORT

    def begin_drag(self, description: str) -> None:
        """Start a drag: one undo step for the whole gesture."""
        self.history.record(self.history_capture(description), description)
        self.dirty = True
        self.undo_suppressed = True

    def end_drag(self) -> None:
        self.undo_suppressed = False

    @undoable("Resize bounding box", coalesce="scale")
    @has_active_bbox_decorator
    def resize_side(self, side: str, amount: float) -> None:
        """Grow/shrink one side of the active box (side scrolling and face dragging)."""
        if self.is_active_locked():
            self.warn_dimensions_locked()
            return
        if not side:
            return
        self.get_active_bbox().change_side(side, amount)  # type: ignore[union-attr]

    def warn_dimensions_locked(self) -> None:
        logging.warning("Dimensions are locked; press Ctrl+L to unlock them.")
        self.view.status_manager.set_message(
            QCoreApplication.translate(
                "labelCloud", "The box size is locked (Ctrl+L unlocks it)."
            )
        )

    # HELPER

    def update_all(self) -> None:
        self.update_z_dial()
        self.update_curr_class()
        self.update_label_list()
        self.view.update_bbox_stats(self.get_active_bbox())

    @has_active_bbox_decorator
    def update_z_dial(self) -> None:
        self.view.dial_bbox_z_rotation.blockSignals(True)  # To brake signal loop
        self.view.dial_bbox_z_rotation.setValue(int(self.get_active_bbox().get_z_rotation()))  # type: ignore
        self.view.dial_bbox_z_rotation.blockSignals(False)

    def update_curr_class(self) -> None:
        if self.has_active_bbox():
            self.view.current_class_dropdown.setCurrentText(
                self.get_active_bbox().classname  # type: ignore
            )
        else:
            self.view.controller.pcd_manager.populate_class_dropdown()

    def update_label_list(self) -> None:
        """Updates the list of drawn labels and highlights the active label.

        Should be always called if the bounding boxes changed.
        :return: None
        """
        self.view.label_list.blockSignals(True)  # To brake signal loop
        self.view.label_list.clear()
        for bbox in self.bboxes:
            self.view.label_list.addItem(bbox.get_classname())
        if self.has_active_bbox():
            self.view.label_list.setCurrentRow(self.active_bbox_id)
            current_item = self.view.label_list.currentItem()
            if current_item:
                current_item.setSelected(True)
        self.view.label_list.blockSignals(False)

    def assign_point_label_in_active_box(self) -> None:
        box = self.get_active_bbox()
        if box is not None:
            self.pcd_manager.assign_point_label_in_box(box)
            if config.getboolean("USER_INTERFACE", "delete_box_after_assign"):
                self.delete_current_bbox()
