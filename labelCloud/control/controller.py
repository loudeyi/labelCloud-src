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

        # Mouse dragging of the active box (no modifier needed)
        self.bbox_drag_active = False
        self.bbox_drag_offset = (0.0, 0.0, 0.0)
        self.bbox_rotate_active = False

        # Focus view: shows only the points inside the active box
        self.focus_active = False
        self._focus_backup = None

        # Save safety
        self.save_error_count = 0

        # Background pre-annotation (offline pole/wire tool)
        self.preannotate_worker = None

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
        if self.curr_cursor_pos is not None:
            self.view.status_manager.set_cursor_position(
                self.view.gl_widget.get_world_coords(
                    self.curr_cursor_pos.x(), self.curr_cursor_pos.y(), correction=True
                )
            )
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
    def save(self, quiet: bool = False) -> bool:
        """Save the current frame. Returns True on success.

        A failing save (read-only folder, full disk, another process holding the
        file) used to raise out of the event loop and take the edits with it. It is
        now reported loudly and the frame stays marked as unsaved.
        """
        try:
            self.pcd_manager.save_labels_into_file(self.bbox_controller.bboxes)

            if LabelConfig().type == LabelingMode.SEMANTIC_SEGMENTATION:
                assert self.pcd_manager.pointcloud is not None
                self.pcd_manager.pointcloud.save_segmentation_labels()
        except Exception as error:  # noqa: BLE001 - must never kill the event loop
            logging.error("Could not save the labels: %s", error, exc_info=True)
            self.save_error_count += 1
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "Saving failed - your edits are NOT on disk (see the log)."
                )
            )
            # the modal dialog is only worth showing for a user-triggered save;
            # a failing autosave reports through the status bar instead of
            # interrupting the annotation with a popup every minute
            if self.save_error_count == 1 and not quiet:
                from PyQt5.QtWidgets import QMessageBox

                QMessageBox.critical(
                    self.view,
                    QCoreApplication.translate("labelCloud", "Saving failed"),
                    QCoreApplication.translate(
                        "labelCloud",
                        "The labels could not be written:\n\n%s\n\n"
                        "The frame stays marked as unsaved; check the folder "
                        "permissions and free space.",
                    )
                    % error,
                )
            return False

        self.bbox_controller.dirty = False
        if not quiet:
            logging.info("Saved labels of %s.", self.pcd_manager.pcd_path)
        return True

    def autosave(self) -> None:
        """Periodic save of unsaved edits (interval from LABEL/autosave_interval_seconds)."""
        if not self.bbox_controller.dirty:
            return
        if self.save(quiet=True):
            self.view.status_manager.set_message(
                QCoreApplication.translate("labelCloud", "Autosaved.")
            )

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

        elif (a0.buttons() & Keys.LeftButton) and (
            a0.modifiers() & Keys.ShiftModifier
        ):
            # Shift+click builds a group: several boxes can be moved/rotated/
            # deleted together instead of one at a time
            hit = oglhelper.get_intersected_bboxes(
                a0.x(),
                a0.y(),
                self.bbox_controller.bboxes,
                self.view.gl_widget.modelview,
                self.view.gl_widget.projection,
            )
            if hit is not None:
                self.bbox_controller.toggle_selection(int(hit))
                size = self.bbox_controller.selection_size()
                self.view.status_manager.set_message(
                    QCoreApplication.translate(
                        "labelCloud", "Group selection: %s boxes."
                    )
                    % size
                )
                return

        elif a0.buttons() & Keys.MiddleButton:
            # middle drag rotates around z: the missing "grab the box" gesture
            if self.bbox_controller.has_active_bbox():
                self.bbox_rotate_active = True
                self.bbox_controller.begin_drag("Rotate around z")

        elif self.selected_side:
            self.side_mode = True

        elif (a0.buttons() & Keys.LeftButton) and (not self.ctrl_pressed):
            # dragging the box body moves it; dragging anywhere else navigates
            if self.start_bbox_drag(a0):
                pass

    def start_bbox_drag(self, a0: QtGui.QMouseEvent) -> bool:
        """Begin moving the active box when the click landed on it."""
        if not self.bbox_controller.has_active_bbox():
            return False
        active = self.bbox_controller.get_active_bbox()
        if oglhelper.get_intersected_bboxes(
            a0.x(),
            a0.y(),
            [active],  # type: ignore[list-item]
            self.view.gl_widget.modelview,
            self.view.gl_widget.projection,
        ) is None:
            return False

        world = self.view.gl_widget.get_world_coords(a0.x(), a0.y(), correction=True)
        center = active.get_center()  # type: ignore[union-attr]
        self.bbox_drag_offset = (
            center[0] - world[0],
            center[1] - world[1],
            center[2] - world[2],
        )
        self.bbox_drag_active = True
        self.bbox_controller.begin_drag("Move bounding box")
        return True

    def mouse_released(self, a0: QtGui.QMouseEvent) -> None:
        """End any drag gesture started on the bounding box."""
        if self.bbox_drag_active or self.bbox_rotate_active:
            self.bbox_controller.end_drag()
        self.bbox_drag_active = False
        self.bbox_rotate_active = False
        self.side_mode = False
        self.scroll_mode = False

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

            # --- dragging the active box (no modifier required) ----------------
            if self.bbox_drag_active and (a0.buttons() & Keys.LeftButton):
                world = self.view.gl_widget.get_world_coords(
                    a0.x(), a0.y(), correction=True
                )
                self.bbox_controller.set_center(
                    world[0] + self.bbox_drag_offset[0],
                    world[1] + self.bbox_drag_offset[1],
                    world[2] + self.bbox_drag_offset[2],
                )
                self.last_cursor_pos = a0.pos()
                return
            if self.bbox_rotate_active and (a0.buttons() & Keys.MiddleButton):
                active = self.bbox_controller.get_active_bbox()
                if active is not None:
                    active.set_z_rotation(
                        active.get_z_rotation() - dx * 5.0
                    )
                self.last_cursor_pos = a0.pos()
                return
            if self.side_mode and (a0.buttons() & Keys.LeftButton) and self.selected_side:
                # dragging a hovered face resizes it (the wheel still works too)
                self.bbox_controller.resize_side(self.selected_side, dy / 20.0)
                self.last_cursor_pos = a0.pos()
                return


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
            self.bbox_controller.resize_side(
                self.selected_side, -a0.angleDelta().y() / 4000  # type: ignore[arg-type]
            )
        else:
            self.pcd_manager.zoom_into(a0.angleDelta().y())
            self.scroll_mode = True

    #: Parameters offered by the ± stepper next to the bounding box panel.
    STEP_PARAMETERS = (
        ("pos_x", "X position"),
        ("pos_y", "Y position"),
        ("pos_z", "Z position"),
        ("length", "Length"),
        ("width", "Width"),
        ("height", "Height"),
        ("rot_x", "Rotation X"),
        ("rot_y", "Rotation Y"),
        ("rot_z", "Rotation Z"),
    )

    def step_parameter(self, parameter: str, direction: int = 1, factor: float = 1.0) -> None:
        """Nudge one bounding box parameter by one configured step."""
        direction = 1 if direction >= 0 else -1
        if parameter.startswith("pos_"):
            self.bbox_controller.nudge_position(
                parameter, self._translation_step(factor) * direction
            )
        elif parameter in ("length", "width", "height"):
            self.bbox_controller.nudge_dimension(
                parameter, self._scaling_step(factor) * direction
            )
        elif parameter.startswith("rot_"):
            self.bbox_controller.nudge_rotation(
                parameter, self._rotation_step(factor) * direction
            )
        else:
            logging.warning("Unknown bounding box parameter '%s'.", parameter)
            return
        self.view.update_bbox_stats(self.bbox_controller.get_active_bbox())

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
        "fit_box_at_cursor": "cmd_fit_box_at_cursor",
        "refit_box": "cmd_refit_box",
        "snap_box": "cmd_snap_box",
        "preannotate_frame": "cmd_preannotate_frame",
        "accept_candidate": "cmd_accept_candidate",
        "next_candidate": "cmd_next_candidate",
        "prev_candidate": "cmd_prev_candidate",
        "reject_candidates": "cmd_reject_candidates",
        "flip_180": "cmd_flip_180",
        "show_statistics": "cmd_show_statistics",
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

    def _group_call(self, function) -> None:
        """Apply a box operation to the whole selection when there is one."""
        applied = self.bbox_controller.apply_to_group(function)
        if applied > 1:
            self.view.status_manager.set_message(
                QCoreApplication.translate("labelCloud", "Changed %s boxes.") % applied
            )

    def _translation_step(self, factor: float) -> float:
        return config.getfloat("LABEL", "std_translation") * factor

    def _rotation_step(self, factor: float) -> float:
        return config.getfloat("LABEL", "std_rotation") * factor

    def _scaling_step(self, factor: float) -> float:
        return config.getfloat("LABEL", "std_scaling") * factor

    def cmd_translate_backward(self, factor: float = 1.0) -> None:
        self._group_call(
            lambda: self.bbox_controller.translate_along_y(self._translation_step(factor))
        )

    def cmd_translate_forward(self, factor: float = 1.0) -> None:
        self._group_call(
            lambda: self.bbox_controller.translate_along_y(
                self._translation_step(factor), forward=True
            )
        )

    def cmd_translate_left(self, factor: float = 1.0) -> None:
        self._group_call(
            lambda: self.bbox_controller.translate_along_x(
                self._translation_step(factor), left=True
            )
        )

    def cmd_translate_right(self, factor: float = 1.0) -> None:
        self._group_call(
            lambda: self.bbox_controller.translate_along_x(self._translation_step(factor))
        )

    def cmd_translate_up(self, factor: float = 1.0) -> None:
        self._group_call(
            lambda: self.bbox_controller.translate_along_z(self._translation_step(factor))
        )

    def cmd_translate_down(self, factor: float = 1.0) -> None:
        self._group_call(
            lambda: self.bbox_controller.translate_along_z(
                self._translation_step(factor), down=True
            )
        )

    def cmd_translate_local_x(self, factor: float = 1.0) -> None:
        self.bbox_controller.translate_local("x", factor=factor)

    def cmd_translate_local_x_neg(self, factor: float = 1.0) -> None:
        self.bbox_controller.translate_local("x", negative=True, factor=factor)

    def cmd_translate_local_y(self, factor: float = 1.0) -> None:
        self.bbox_controller.translate_local("y", factor=factor)

    def cmd_translate_local_y_neg(self, factor: float = 1.0) -> None:
        self.bbox_controller.translate_local("y", negative=True, factor=factor)

    def cmd_rotate_z_ccw(self, factor: float = 1.0) -> None:
        self._group_call(
            lambda: self.bbox_controller.rotate_around_z(self._rotation_step(factor))
        )

    def cmd_rotate_z_cw(self, factor: float = 1.0) -> None:
        self._group_call(
            lambda: self.bbox_controller.rotate_around_z(
                self._rotation_step(factor), clockwise=True
            )
        )

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
        self._group_call(lambda: self.select_relative_class(-1))

    def cmd_class_next(self, factor: float = 1.0) -> None:
        self._group_call(lambda: self.select_relative_class(1))

    def cmd_delete_bbox(self, factor: float = 1.0) -> None:
        if self.bbox_controller.selection_size() > 1:
            deleted = self.bbox_controller.delete_group()
            self.view.status_manager.set_message(
                QCoreApplication.translate("labelCloud", "Deleted %s boxes.") % deleted
            )
        else:
            self.bbox_controller.delete_current_bbox()

    def cmd_escape(self, factor: float = 1.0) -> None:
        if self.bbox_controller.selected_ids:
            self.bbox_controller.clear_selection()
            self.view.status_manager.set_message(
                QCoreApplication.translate("labelCloud", "Cleared the group selection.")
            )
        elif self.drawing_mode.is_active():
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

    # ASSIST COMMANDS

    def _current_class(self) -> str:
        if self.bbox_controller.has_active_bbox():
            return self.bbox_controller.get_classname()
        return LabelConfig().get_default_class_name()

    def cmd_fit_box_at_cursor(self, factor: float = 1.0) -> None:
        """Grow a region under the mouse cursor and fit a box (F-20)."""
        from . import assist

        pointcloud = self.pcd_manager.pointcloud
        if pointcloud is None or self.curr_cursor_pos is None:
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "Move the mouse over an object first."
                )
            )
            return
        world = self.view.gl_widget.get_world_coords(
            self.curr_cursor_pos.x(), self.curr_cursor_pos.y(), correction=True
        )
        seed_index = assist.nearest_point_index(pointcloud.points, world)
        if seed_index is None:
            return
        classname = self._current_class()
        fitted = assist.fit_box(pointcloud.points, seed_index, classname)
        if fitted is None:
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "Could not fit a box here - click closer to the object."
                )
            )
            return
        fitted.locked = False
        self.bbox_controller.add_bbox(fitted)
        self.view.status_manager.set_message(
            QCoreApplication.translate("labelCloud", "Fitted a %s box.") % classname
        )

    def cmd_refit_box(self, factor: float = 1.0) -> None:
        """Refit the active box to the points inside it (F-21)."""
        from . import assist

        pointcloud = self.pcd_manager.pointcloud
        bbox = self.bbox_controller.get_active_bbox()
        if pointcloud is None or bbox is None:
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "Select a box first, then refit it."
                )
            )
            return
        if self.bbox_controller.is_active_locked():
            self.bbox_controller.warn_dimensions_locked()
            return
        refitted = assist.refit_box(bbox, pointcloud.points)
        if refitted is None:
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "Not enough points inside the box to refit it."
                )
            )
            return
        self.bbox_controller.replace_active_bbox(refitted, "Refit bounding box")
        self.view.status_manager.set_message(
            QCoreApplication.translate("labelCloud", "Refit the box to the points inside it.")
        )

    def cmd_snap_box(self, factor: float = 1.0) -> None:
        """Snap the active box onto the local ground (F-22)."""
        from . import assist

        pointcloud = self.pcd_manager.pointcloud
        bbox = self.bbox_controller.get_active_bbox()
        if pointcloud is None or bbox is None:
            return
        if assist.snap_box(bbox, pointcloud.points):
            self.bbox_controller.replace_active_bbox(bbox, "Snap box to ground")
            self.view.update_bbox_stats(bbox)
            self.view.status_manager.set_message(
                QCoreApplication.translate("labelCloud", "Snapped the box onto the ground.")
            )
        else:
            self.view.status_manager.set_message(
                QCoreApplication.translate("labelCloud", "The box already sits on the ground.")
            )

    def cmd_preannotate_frame(self, factor: float = 1.0) -> None:
        """Run the offline pre-annotation on this frame, in a background thread (F-24)."""
        from .assist_worker import worker_for

        if self.preannotate_worker is not None and self.preannotate_worker.isRunning():
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "Pre-annotation is still running ..."
                )
            )
            return

        worker = worker_for(getattr(self.pcd_manager, "pcd_path", None), self.view)
        if worker is None:
            return
        worker.proposals_ready.connect(self.on_proposals_ready)
        worker.failed.connect(self.on_proposals_failed)
        self.preannotate_worker = worker
        self.view.status_manager.set_message(
            QCoreApplication.translate(
                "labelCloud", "Running pre-annotation in the background ..."
            )
        )
        worker.start()

    def on_proposals_ready(self, proposals: list, message: str) -> None:
        from .assist_worker import to_bboxes

        boxes = to_bboxes(proposals)
        added = self.bbox_controller.add_candidates(boxes)
        self.view.status_manager.set_message(
            QCoreApplication.translate(
                "labelCloud",
                "%s proposals added; Enter confirms one, Ctrl+Right jumps to the next.",
            )
            % added
        )

    def on_proposals_failed(self, message: str) -> None:
        self.view.status_manager.set_message(
            QCoreApplication.translate(
                "labelCloud", "Pre-annotation failed - see the log for details."
            )
        )

    def cmd_accept_candidate(self, factor: float = 1.0) -> None:
        """Confirm the active proposal and jump to the next one (F-23)."""
        if self.bbox_controller.accept_candidate():
            remaining = self.bbox_controller.candidate_count()
            self.bbox_controller.select_relative_candidate(1)
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "Confirmed. %s proposals left in this frame."
                )
                % remaining
            )

    def cmd_reject_candidates(self, factor: float = 1.0) -> None:
        rejected = self.bbox_controller.reject_all_candidates()
        if rejected:
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "Rejected %s proposals in this frame."
                )
                % rejected
            )

    def cmd_next_candidate(self, factor: float = 1.0) -> None:
        self.bbox_controller.select_relative_candidate(1)

    def cmd_prev_candidate(self, factor: float = 1.0) -> None:
        self.bbox_controller.select_relative_candidate(-1)

    def cmd_flip_180(self, factor: float = 1.0) -> None:
        """Flip the box by 180 degrees (heading is often ambiguous)."""

        def flip() -> None:
            bbox = self.bbox_controller.get_active_bbox()
            if bbox is None:
                return
            self.bbox_controller.update_rotation(
                "rot_z", (bbox.get_z_rotation() + 180.0) % 360.0
            )

        self._group_call(flip)
        self.view.update_bbox_stats(self.bbox_controller.get_active_bbox())

    def cmd_show_statistics(self, factor: float = 1.0) -> None:
        from ..view.statistics_dialog import StatisticsDialog

        StatisticsDialog(self.view, self).exec_()

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
