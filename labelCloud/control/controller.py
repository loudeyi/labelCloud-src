import logging
from typing import Optional

import numpy as np
from PyQt5 import QtGui
from PyQt5.QtCore import QPoint
from PyQt5.QtCore import Qt as Keys

from ..definitions import BBOX_SIDES, Colors, Context, LabelingMode
from ..io.labels.config import LabelConfig
from ..utils import oglhelper
from ..view.gui import GUI
from .alignmode import AlignMode
from .bbox_controller import BoundingBoxController
from .config_manager import config
from .keymap import KeyMap
from .drawing_manager import DrawingManager
from .pcd_manager import PointCloudManger
from PyQt5.QtCore import QCoreApplication


class Controller:
    MOVEMENT_THRESHOLD = 0.1

    def __init__(self) -> None:
        """Initializes all controllers and managers."""
        self.view: "GUI"
        self.pcd_manager = PointCloudManger()
        self.bbox_controller = BoundingBoxController()

        # Drawing states
        self.drawing_mode = DrawingManager(self.bbox_controller)
        self.align_mode = AlignMode(self.pcd_manager)

        # Control states
        self.curr_cursor_pos: Optional[QPoint] = None  # updated by mouse movement
        self.last_cursor_pos: Optional[QPoint] = None  # updated by mouse click
        self.ctrl_pressed = False
        self.scroll_mode = False  # to enable the side-pulling

        # Correction states
        self.side_mode = False
        self.selected_side: Optional[str] = None

        # Keyboard shortcuts (rebindable through the [SHORTCUTS] config section)
        self.keymap = KeyMap()

        # Focus view: shows only the points inside the active box
        self.focus_active = False
        self._focus_backup = None

    def startup(self, view: "GUI") -> None:
        """Sets the view in all controllers and dependent modules; Loads labels from file."""
        self.view = view
        self.bbox_controller.set_view(self.view)
        self.pcd_manager.set_view(self.view)
        self.drawing_mode.set_view(self.view)
        self.align_mode.set_view(self.view)
        self.view.gl_widget.set_bbox_controller(self.bbox_controller)
        self.bbox_controller.pcd_manager = self.pcd_manager

        # Read labels from folders
        self.pcd_manager.read_pointcloud_folder()
        self.next_pcd(save=False)

    def loop_gui(self) -> None:
        """Function collection called during each event loop iteration."""
        self.set_crosshair()
        self.set_selected_side()
        self.view.gl_widget.updateGL()

    # POINT CLOUD METHODS
    def next_pcd(self, save: bool = True) -> None:
        if save:
            self.save()
        if self.pcd_manager.pcds_left():
            previous_bboxes = self.bbox_controller.bboxes
            self.pcd_manager.get_next_pcd()
            self.reset()
            self.bbox_controller.set_bboxes(self.pcd_manager.get_labels_from_file())

            if not self.bbox_controller.bboxes and config.getboolean(
                "LABEL", "propagate_labels"
            ):
                self.bbox_controller.set_bboxes(previous_bboxes)
            self.bbox_controller.set_active_bbox(0)
        else:
            self.view.update_progress(len(self.pcd_manager.pcds))
            self.view.button_next_pcd.setEnabled(False)

    def prev_pcd(self) -> None:
        self.save()
        if self.pcd_manager.current_id > 0:
            self.pcd_manager.get_prev_pcd()
            self.reset()
            self.bbox_controller.set_bboxes(self.pcd_manager.get_labels_from_file())
            self.bbox_controller.set_active_bbox(0)

    def custom_pcd(self, custom: int) -> None:
        self.save()
        self.pcd_manager.get_custom_pcd(custom)
        self.reset()
        self.bbox_controller.set_bboxes(self.pcd_manager.get_labels_from_file())

    # CONTROL METHODS
    def save(self) -> None:
        """Saves all bounding boxes and optionally segmentation labels in the label file."""
        self.pcd_manager.save_labels_into_file(self.bbox_controller.bboxes)

        if LabelConfig().type == LabelingMode.SEMANTIC_SEGMENTATION:
            assert self.pcd_manager.pointcloud is not None
            self.pcd_manager.pointcloud.save_segmentation_labels()

    def activate_focus(self) -> None:
        """Show only the points inside the active box (helps in dense clouds)."""
        if self.focus_active:
            return
        pointcloud = self.pcd_manager.pointcloud
        bbox = self.bbox_controller.get_active_bbox()
        if pointcloud is None or bbox is None:
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "Select a box first to focus on its points."
                )
            )
            return
        inside = bbox.is_inside(pointcloud.points)
        if not inside.any():
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "No points inside the active box to focus on."
                )
            )
            return
        colors = pointcloud.colors
        self._focus_backup = (
            pointcloud.points,
            None if colors is None else colors.copy(),
        )
        pointcloud.points = pointcloud.points[inside]
        if colors is not None:
            pointcloud.colors = colors[inside]
        pointcloud.create_buffers()
        self.focus_active = True
        self.view.status_manager.set_message(
            QCoreApplication.translate(
                "labelCloud", "Focus on the active box (Ctrl+F shows everything again)."
            )
        )

    def clear_focus(self) -> None:
        """Restore the full point cloud."""
        pointcloud = self.pcd_manager.pointcloud
        if self._focus_backup is not None and pointcloud is not None:
            points, colors = self._focus_backup
            pointcloud.points = points
            if colors is not None:
                pointcloud.colors = colors
            pointcloud.create_buffers()
        self._focus_backup = None
        self.focus_active = False

    def reset(self) -> None:
        """Resets the controllers and bounding boxes from the current screen."""
        # the point cloud object is replaced on a frame change, so drop the focus
        # backup instead of writing it back into a discarded object
        self._focus_backup = None
        self.focus_active = False
        self.bbox_controller.reset()
        self.drawing_mode.reset()
        self.align_mode.reset()

    # CORRECTION METHODS
    def set_crosshair(self) -> None:
        """Sets the crosshair position in the glWidget to the current cursor position."""
        if self.curr_cursor_pos:
            self.view.gl_widget.crosshair_col = Colors.GREEN.value
            self.view.gl_widget.crosshair_pos = (
                self.curr_cursor_pos.x(),
                self.curr_cursor_pos.y(),
            )

    def set_selected_side(self) -> None:
        """Sets the currently hovered bounding box side in the glWidget."""
        if (
            (not self.side_mode)
            and self.curr_cursor_pos
            and self.bbox_controller.has_active_bbox()
            and (not self.scroll_mode)
        ):
            _, self.selected_side = oglhelper.get_intersected_sides(
                self.curr_cursor_pos.x(),
                self.curr_cursor_pos.y(),
                self.bbox_controller.get_active_bbox(),  # type: ignore
                self.view.gl_widget.modelview,
                self.view.gl_widget.projection,
            )
        if (
            self.selected_side
            and (not self.ctrl_pressed)
            and self.bbox_controller.has_active_bbox()
        ):
            self.view.gl_widget.crosshair_col = Colors.RED.value
            side_vertices = self.bbox_controller.get_active_bbox().get_vertices()  # type: ignore
            self.view.gl_widget.selected_side_vertices = side_vertices[
                BBOX_SIDES[self.selected_side]
            ]
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "Scroll to change the bounding box dimension."
                ),
                context=Context.SIDE_HOVERED,
            )
        else:
            self.view.gl_widget.selected_side_vertices = np.array([])
            self.view.status_manager.clear_message(Context.SIDE_HOVERED)

    # EVENT PROCESSING
    def mouse_clicked(self, a0: QtGui.QMouseEvent) -> None:
        """Triggers actions when the user clicks the mouse."""
        self.last_cursor_pos = a0.pos()

        if (
            self.drawing_mode.is_active()
            and (a0.buttons() & Keys.LeftButton)
            and (not self.ctrl_pressed)
        ):
            self.drawing_mode.register_point(a0.x(), a0.y(), correction=True)

        elif self.align_mode.is_active and (not self.ctrl_pressed):
            self.align_mode.register_point(
                self.view.gl_widget.get_world_coords(a0.x(), a0.y(), correction=False)
            )

        elif self.selected_side:
            self.side_mode = True

    def mouse_double_clicked(self, a0: QtGui.QMouseEvent) -> None:
        """Triggers actions when the user double clicks the mouse."""
        self.bbox_controller.select_bbox_by_ray(a0.x(), a0.y())

    def mouse_move_event(self, a0: QtGui.QMouseEvent) -> None:
        """Triggers actions when the user moves the mouse."""
        self.curr_cursor_pos = a0.pos()  # Updates the current mouse cursor position

        # Methods that use absolute cursor position
        if self.drawing_mode.is_active() and (not self.ctrl_pressed):
            self.drawing_mode.register_point(
                a0.x(), a0.y(), correction=True, is_temporary=True
            )

        elif self.align_mode.is_active and (not self.ctrl_pressed):
            self.align_mode.register_tmp_point(
                self.view.gl_widget.get_world_coords(a0.x(), a0.y(), correction=False)
            )

        if self.last_cursor_pos:
            dx = (
                self.last_cursor_pos.x() - a0.x()
            ) / 5  # Calculate relative movement from last click position
            dy = (self.last_cursor_pos.y() - a0.y()) / 5

            if (
                self.ctrl_pressed
                and (not self.drawing_mode.is_active())
                and (not self.align_mode.is_active)
            ):
                if a0.buttons() & Keys.LeftButton:  # bbox rotation
                    self.bbox_controller.rotate_with_mouse(-dx, -dy)
                elif a0.buttons() & Keys.RightButton:  # bbox translation
                    new_center = self.view.gl_widget.get_world_coords(
                        a0.x(), a0.y(), correction=True
                    )
                    self.bbox_controller.set_center(*new_center)  # absolute positioning
            else:
                if a0.buttons() & Keys.LeftButton:  # pcd rotation
                    self.pcd_manager.rotate_around_x(dy)
                    self.pcd_manager.rotate_around_z(dx)
                elif a0.buttons() & Keys.RightButton:  # pcd translation
                    self.pcd_manager.translate_along_x(dx)
                    self.pcd_manager.translate_along_y(dy)

            # Reset scroll locks of "side scrolling" for significant cursor movements
            if dx > Controller.MOVEMENT_THRESHOLD or dy > Controller.MOVEMENT_THRESHOLD:
                if self.side_mode:
                    self.side_mode = False
                else:
                    self.scroll_mode = False
        self.last_cursor_pos = a0.pos()

    def mouse_scroll_event(self, a0: QtGui.QWheelEvent) -> None:
        """Triggers actions when the user scrolls the mouse wheel."""
        if self.selected_side:
            self.side_mode = True

        if (
            self.drawing_mode.is_active()
            and (not self.ctrl_pressed)
            and self.drawing_mode.drawing_strategy is not None
        ):
            self.drawing_mode.drawing_strategy.register_scrolling(a0.angleDelta().y())
        elif self.side_mode and self.bbox_controller.has_active_bbox():
            self.bbox_controller.get_active_bbox().change_side(  # type: ignore
                self.selected_side, -a0.angleDelta().y() / 4000  # type: ignore
            )  # ToDo implement method
        else:
            self.pcd_manager.zoom_into(a0.angleDelta().y())
            self.scroll_mode = True

    # KEY DISPATCH

    #: command name from the keymap -> method on this controller
    COMMANDS = {
        "prev_pcd": "cmd_prev_pcd",
        "next_pcd": "cmd_next_pcd",
        "reset_view": "cmd_reset_view",
        "save": "cmd_save",
        "translate_backward": "cmd_translate_backward",
        "translate_forward": "cmd_translate_forward",
        "translate_left": "cmd_translate_left",
        "translate_right": "cmd_translate_right",
        "translate_up": "cmd_translate_up",
        "translate_down": "cmd_translate_down",
        "translate_local_x": "cmd_translate_local_x",
        "translate_local_x_neg": "cmd_translate_local_x_neg",
        "translate_local_y": "cmd_translate_local_y",
        "translate_local_y_neg": "cmd_translate_local_y_neg",
        "rotate_z_ccw": "cmd_rotate_z_ccw",
        "rotate_z_cw": "cmd_rotate_z_cw",
        "rotate_y_ccw": "cmd_rotate_y_ccw",
        "rotate_y_cw": "cmd_rotate_y_cw",
        "rotate_x_ccw": "cmd_rotate_x_ccw",
        "rotate_x_cw": "cmd_rotate_x_cw",
        "scale_length_up": "cmd_scale_length_up",
        "scale_length_down": "cmd_scale_length_down",
        "scale_width_up": "cmd_scale_width_up",
        "scale_width_down": "cmd_scale_width_down",
        "scale_height_up": "cmd_scale_height_up",
        "scale_height_down": "cmd_scale_height_down",
        "select_prev_bbox": "cmd_select_prev_bbox",
        "select_next_bbox": "cmd_select_next_bbox",
        "class_prev": "cmd_class_prev",
        "class_next": "cmd_class_next",
        "delete_bbox": "cmd_delete_bbox",
        "escape": "cmd_escape",
        "undo": "cmd_undo",
        "redo": "cmd_redo",
        "copy_box": "cmd_copy_box",
        "paste_box": "cmd_paste_box",
        "duplicate_box": "cmd_duplicate_box",
        "toggle_dimension_lock": "cmd_toggle_dimension_lock",
        "apply_template": "cmd_apply_template",
        "toggle_focus": "cmd_toggle_focus",
        "show_shortcuts": "cmd_show_shortcuts",
    }

    def key_press_event(self, a0: QtGui.QKeyEvent) -> None:
        """Dispatch a key press through the shortcut table.

        See ``control/keymap.py``: bindings are matched with their modifiers, so
        Ctrl combinations no longer fall through to the single-key commands, and
        Shift/Alt act as coarse/fine step multipliers.
        """
        if a0.key() == Keys.Key_Control:
            self.ctrl_pressed = True
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "Hold right mouse button to translate or left mouse button to rotate "
                    "the bounding box."
                ),
                context=Context.CONTROL_PRESSED,
            )
            return

        # 1-9 jump straight to a box
        digit = a0.key() - Keys.Key_0
        if (
            1 <= digit <= 9
            and not a0.modifiers() & (Keys.ControlModifier | Keys.AltModifier)
        ):
            self.bbox_controller.set_active_bbox(digit - 1)
            return

        binding, factor = self.keymap.resolve(a0.modifiers(), a0.key())
        if binding is None:
            return
        handler_name = self.COMMANDS.get(binding.command)
        if handler_name is None:
            logging.warning("No handler implemented for command '%s'.", binding.command)
            return
        getattr(self, handler_name)(factor)

    # COMMAND HANDLERS (all take the step multiplier so Shift/Alt work everywhere)

    def cmd_prev_pcd(self, factor: float = 1.0) -> None:
        self.prev_pcd()

    def cmd_next_pcd(self, factor: float = 1.0) -> None:
        self.next_pcd()

    def cmd_reset_view(self, factor: float = 1.0) -> None:
        self.pcd_manager.reset_transformations()
        logging.info("Reseted position to default.")

    def cmd_save(self, factor: float = 1.0) -> None:
        self.save()

    def _translation_step(self, factor: float) -> float:
        return config.getfloat("LABEL", "std_translation") * factor

    def _rotation_step(self, factor: float) -> float:
        return config.getfloat("LABEL", "std_rotation") * factor

    def _scaling_step(self, factor: float) -> float:
        return config.getfloat("LABEL", "std_scaling") * factor

    def cmd_translate_backward(self, factor: float = 1.0) -> None:
        self.bbox_controller.translate_along_y(self._translation_step(factor))

    def cmd_translate_forward(self, factor: float = 1.0) -> None:
        self.bbox_controller.translate_along_y(self._translation_step(factor), forward=True)

    def cmd_translate_left(self, factor: float = 1.0) -> None:
        self.bbox_controller.translate_along_x(self._translation_step(factor), left=True)

    def cmd_translate_right(self, factor: float = 1.0) -> None:
        self.bbox_controller.translate_along_x(self._translation_step(factor))

    def cmd_translate_up(self, factor: float = 1.0) -> None:
        self.bbox_controller.translate_along_z(self._translation_step(factor))

    def cmd_translate_down(self, factor: float = 1.0) -> None:
        self.bbox_controller.translate_along_z(self._translation_step(factor), down=True)

    def cmd_translate_local_x(self, factor: float = 1.0) -> None:
        self.bbox_controller.translate_local("x", factor=factor)

    def cmd_translate_local_x_neg(self, factor: float = 1.0) -> None:
        self.bbox_controller.translate_local("x", negative=True, factor=factor)

    def cmd_translate_local_y(self, factor: float = 1.0) -> None:
        self.bbox_controller.translate_local("y", factor=factor)

    def cmd_translate_local_y_neg(self, factor: float = 1.0) -> None:
        self.bbox_controller.translate_local("y", negative=True, factor=factor)

    def cmd_rotate_z_ccw(self, factor: float = 1.0) -> None:
        self.bbox_controller.rotate_around_z(self._rotation_step(factor))

    def cmd_rotate_z_cw(self, factor: float = 1.0) -> None:
        self.bbox_controller.rotate_around_z(self._rotation_step(factor), clockwise=True)

    def cmd_rotate_y_ccw(self, factor: float = 1.0) -> None:
        self.bbox_controller.rotate_around_y(self._rotation_step(factor))

    def cmd_rotate_y_cw(self, factor: float = 1.0) -> None:
        self.bbox_controller.rotate_around_y(self._rotation_step(factor), clockwise=True)

    def cmd_rotate_x_ccw(self, factor: float = 1.0) -> None:
        self.bbox_controller.rotate_around_x(self._rotation_step(factor))

    def cmd_rotate_x_cw(self, factor: float = 1.0) -> None:
        self.bbox_controller.rotate_around_x(self._rotation_step(factor), clockwise=True)

    def cmd_scale_length_up(self, factor: float = 1.0) -> None:
        self.bbox_controller.scale_along_length(self._scaling_step(factor))

    def cmd_scale_length_down(self, factor: float = 1.0) -> None:
        self.bbox_controller.scale_along_length(self._scaling_step(factor), decrease=True)

    def cmd_scale_width_up(self, factor: float = 1.0) -> None:
        self.bbox_controller.scale_along_width(self._scaling_step(factor))

    def cmd_scale_width_down(self, factor: float = 1.0) -> None:
        self.bbox_controller.scale_along_width(self._scaling_step(factor), decrease=True)

    def cmd_scale_height_up(self, factor: float = 1.0) -> None:
        self.bbox_controller.scale_along_height(self._scaling_step(factor))

    def cmd_scale_height_down(self, factor: float = 1.0) -> None:
        self.bbox_controller.scale_along_height(self._scaling_step(factor), decrease=True)

    def cmd_select_prev_bbox(self, factor: float = 1.0) -> None:
        self.select_relative_bbox(-1)

    def cmd_select_next_bbox(self, factor: float = 1.0) -> None:
        self.select_relative_bbox(1)

    def cmd_class_prev(self, factor: float = 1.0) -> None:
        self.select_relative_class(-1)

    def cmd_class_next(self, factor: float = 1.0) -> None:
        self.select_relative_class(1)

    def cmd_delete_bbox(self, factor: float = 1.0) -> None:
        self.bbox_controller.delete_current_bbox()

    def cmd_escape(self, factor: float = 1.0) -> None:
        if self.drawing_mode.is_active():
            self.drawing_mode.reset()
            logging.info("Resetted drawn points!")
        elif self.align_mode.is_active:
            self.align_mode.reset()
            logging.info("Resetted selected points!")
        else:
            self.bbox_controller.deselect_bbox()

    # EDITING COMMANDS

    def cmd_undo(self, factor: float = 1.0) -> None:
        if self.bbox_controller.undo():
            self.view.status_manager.set_message(
                QCoreApplication.translate("labelCloud", "Undone the last change.")
            )
            self.view.update_bbox_stats(self.bbox_controller.get_active_bbox())
        else:
            self.view.status_manager.set_message(
                QCoreApplication.translate("labelCloud", "Nothing to undo.")
            )

    def cmd_redo(self, factor: float = 1.0) -> None:
        if self.bbox_controller.redo():
            self.view.status_manager.set_message(
                QCoreApplication.translate("labelCloud", "Redone the last change.")
            )
            self.view.update_bbox_stats(self.bbox_controller.get_active_bbox())
        else:
            self.view.status_manager.set_message(
                QCoreApplication.translate("labelCloud", "Nothing to redo.")
            )

    def cmd_copy_box(self, factor: float = 1.0) -> None:
        self.bbox_controller.copy_current_bbox()
        if self.bbox_controller.clipboard is not None:
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "Copied the box; Ctrl+V pastes it (also in the next frame)."
                )
            )

    def cmd_paste_box(self, factor: float = 1.0) -> None:
        if self.bbox_controller.paste_bbox():
            self.view.status_manager.set_message(
                QCoreApplication.translate("labelCloud", "Pasted the box.")
            )
        else:
            self.view.status_manager.set_message(
                QCoreApplication.translate("labelCloud", "Nothing to paste: copy a box first.")
            )

    def cmd_duplicate_box(self, factor: float = 1.0) -> None:
        self.bbox_controller.duplicate_current_bbox()

    def cmd_toggle_dimension_lock(self, factor: float = 1.0) -> None:
        self.bbox_controller.toggle_dimension_lock()
        locked = self.bbox_controller.is_active_locked()
        self.view.status_manager.set_message(
            QCoreApplication.translate("labelCloud", "Box size locked (Ctrl+L).")
            if locked
            else QCoreApplication.translate("labelCloud", "Box size unlocked (Ctrl+L).")
        )

    def cmd_apply_template(self, factor: float = 1.0) -> None:
        self.bbox_controller.apply_template()

    def cmd_toggle_focus(self, factor: float = 1.0) -> None:
        if self.focus_active:
            self.clear_focus()
        else:
            self.activate_focus()

    def cmd_show_shortcuts(self, factor: float = 1.0) -> None:
        from ..view.shortcut_dialog import ShortcutDialog

        ShortcutDialog(self.view, self.keymap).exec_()

    def select_relative_class(self, step: int):
        if step == 0:
            return
        curr_class = self.bbox_controller.get_active_bbox().get_classname()  # type: ignore
        new_class = LabelConfig().get_relative_class(curr_class, step)
        self.bbox_controller.get_active_bbox().set_classname(new_class)  # type: ignore
        self.bbox_controller.update_all()  # updates UI in SelectBox

    def select_relative_bbox(self, step: int):
        if step == 0:
            return
        max_id = len(self.bbox_controller.bboxes) - 1
        curr_id = self.bbox_controller.active_bbox_id
        new_id = curr_id + step
        corner_case_id = 0 if step > 0 else max_id
        new_id = new_id if new_id in range(max_id + 1) else corner_case_id
        self.bbox_controller.set_active_bbox(new_id)

    def key_release_event(self, a0: QtGui.QKeyEvent) -> None:
        """Triggers actions when the user releases a key."""
        if a0.key() == Keys.Key_Control:
            self.ctrl_pressed = False
            self.view.status_manager.clear_message(Context.CONTROL_PRESSED)

    def crop_pointcloud_inside_active_bbox(self) -> None:
        bbox = self.bbox_controller.get_active_bbox()
        assert bbox is not None
        assert self.pcd_manager.pointcloud is not None
        points_inside = bbox.is_inside(self.pcd_manager.pointcloud.points)
        pointcloud = self.pcd_manager.pointcloud.get_filtered_pointcloud(points_inside)
        if pointcloud is None:
            logging.warning("No points found inside the box. Ignored.")
            return
        self.view.save_point_cloud_as(pointcloud)
