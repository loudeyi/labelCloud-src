import logging
from pathlib import Path
from typing import List, NamedTuple, Optional

import numpy as np
from PyQt5 import QtGui
from PyQt5.QtCore import QPoint
from PyQt5.QtCore import Qt as Keys

from ..definitions import BBOX_SIDES, Colors, Context, LabelingMode
from ..io.labels.config import LabelConfig
from ..model.point_cloud import PointCloud
from ..view.status_manager import shorten_filename
from ..utils import oglhelper
from ..view.gui import GUI
from .alignmode import AlignMode
from .bbox_controller import BoundingBoxController
from .config_manager import config
from .keymap import KeyMap
from .prediction import (
    DEFAULT_MIN_POINTS,
    DEFAULT_RATIO,
    DEFAULT_SENSITIVITY,
    PointHistory,
    decide,
)
from .undo import BBoxState
from .drawing_manager import DrawingManager
from .pcd_manager import PointCloudManger
from PyQt5.QtCore import QCoreApplication


class ActivityEntry(NamedTuple):
    """One line of the activity log (shown by ``Ctrl+Shift+S``).

    A named tuple rather than a plain 5-tuple so the fields are documented, while the
    existing unpacking (``for timestamp, kind, path, ok, message in ...``) keeps
    working.
    """

    timestamp: float
    kind: str  # "load" or "save"
    path: str
    ok: bool
    message: str


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

        # Mouse dragging of the active box (no modifier needed).
        # `drag_target` freezes what the gesture started on, so the mode cannot
        # flip between "resize a face" and "rotate the cloud" while the button is
        # held — that flip is what made the view jitter during a face drag.
        self.drag_target: Optional[str] = None  # None | "box" | "face" | "rotate"
        self.drag_side: Optional[str] = None  # side frozen at press time
        self.drag_start_pos = None
        #: dimension of the dragged side when the gesture started, so the resize is
        #: computed from the total cursor movement instead of accumulating deltas
        #: (accumulation drifts and made the box oscillate under the cursor)
        self.drag_start_extent: Optional[float] = None
        #: pixels of vertical drag per metre when resizing a face
        self.FACE_DRAG_PIXELS_PER_METER = 20.0
        self.bbox_drag_offset = (0.0, 0.0, 0.0)
        self.pending_draw_kind: Optional[str] = None  # "drawing" | "align"
        #: a click that moved more than this many pixels counts as a drag
        self.CLICK_MAX_MOVE_PX = 5

        # Focus view: shows only the points inside the active box
        self.focus_active = False
        self._focus_backup = None

        # Save safety
        self.save_error_count = 0
        #: every load and every write, newest last (see :class:`ActivityEntry`)
        self.activity_log: List[ActivityEntry] = []
        #: kept for compatibility with anything reading the old name
        self.save_log = self.activity_log
        self.SAVE_LOG_LIMIT = 200
        self._last_save_state = "unknown"
        self._last_saved_at = ""
        self._last_saved_path = ""

        # Background pre-annotation (offline pole/wire tool)
        self.preannotate_worker = None
        # Background forward propagation ("label this object to the end")
        self.propagate_worker = None

        # Interpolation anchor: (frame index, box state) of the first keyframe
        self.interpolation_anchor = None

        #: the rotation-unit warning is shown once per session
        self.rotation_unit_warned = False

        # Points of the previous frames, drawn dimmed as a viewing aid
        self.ghost_cloud = None
        self._ghost_source_id = None

        #: Class every *new* box gets, frame after frame. ``None`` follows the
        #: active box / the class definition. Lets one pass label poles and the
        #: next pass wires instead of re-picking the class in every frame.
        self.next_box_class: Optional[str] = None

    def startup(self, view: "GUI") -> None:
        """Sets the view in all controllers and dependent modules; Loads labels from file."""
        self.view = view
        self.bbox_controller.set_view(self.view)
        self.pcd_manager.set_view(self.view)
        self.drawing_mode.set_view(self.view)
        self.align_mode.set_view(self.view)
        self.view.gl_widget.set_bbox_controller(self.bbox_controller)
        self.view.gl_widget.ghost_provider = lambda: self.ghost_cloud
        self.bbox_controller.pcd_manager = self.pcd_manager

        # Read labels from folders
        self.pcd_manager.read_pointcloud_folder()
        self.next_pcd(save=False)

    def loop_gui(self) -> None:
        """Function collection called during each event loop iteration."""
        self.set_crosshair()
        self.refresh_save_state()
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
            prediction_sources = self.capture_prediction_sources()
            previous_bboxes = list(self.bbox_controller.bboxes)
            self.pcd_manager.get_next_pcd()
            self.reset()
            self.bbox_controller.set_bboxes(self.pcd_manager.get_labels_from_file())
            self.on_frame_loaded(prediction_sources, previous_bboxes)
        else:
            self.view.update_progress(len(self.pcd_manager.pcds))
            self.view.button_next_pcd.setEnabled(False)

    def prev_pcd(self) -> None:
        self.save()
        if self.pcd_manager.current_id > 0:
            prediction_sources = self.capture_prediction_sources()
            previous_bboxes = list(self.bbox_controller.bboxes)
            self.pcd_manager.get_prev_pcd()
            self.reset()
            self.bbox_controller.set_bboxes(self.pcd_manager.get_labels_from_file())
            self.on_frame_loaded(prediction_sources, previous_bboxes)

    def custom_pcd(self, custom: int) -> None:
        self.save()
        self.pcd_manager.get_custom_pcd(custom)
        self.reset()
        self.bbox_controller.set_bboxes(self.pcd_manager.get_labels_from_file())
        self.on_frame_loaded([], [])

    # MULTI-FRAME OVERLAY (viewing aid)

    def accumulate_frames(self) -> int:
        from .config_manager import config

        return config.getint("POINTCLOUD", "accumulate_frames", fallback=0)

    def set_accumulate_frames(self, count: int) -> None:
        """How many previous frames to draw dimmed behind the current one."""
        from .config_manager import config, config_manager

        config.set("POINTCLOUD", "accumulate_frames", str(max(0, int(count))))
        config_manager.write_into_file()
        self.refresh_ghost_cloud(force=True)
        if count:
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "Overlaying the %s previous frames."
                )
                % count
            )
        else:
            self.view.status_manager.set_message(
                QCoreApplication.translate("labelCloud", "Overlay off.")
            )

    def refresh_ghost_cloud(self, force: bool = False) -> None:
        """(Re)build the dimmed overlay of the previous frames.

        The overlay is only rebuilt when the frame or the setting changed: reading a
        point cloud per frame is cheap, but doing it on every 20 ms tick would not be.
        """
        count = self.accumulate_frames()
        pointcloud = self.pcd_manager.pointcloud
        if count <= 0 or pointcloud is None:
            self.ghost_cloud = None
            self._ghost_source_id = None
            return
        key = (self.pcd_manager.current_id, count)
        if not force and key == self._ghost_source_id and self.ghost_cloud is not None:
            return
        self._ghost_source_id = key

        start = max(0, self.pcd_manager.current_id - count)
        previous = list(self.pcd_manager.pcds[start : self.pcd_manager.current_id])
        clouds = []
        for path in previous:
            try:
                from ..io.pointclouds import BasePointCloudHandler

                handler = BasePointCloudHandler.get_handler(path.suffix)
                points, _colors = handler.read_point_cloud(path=path)
                clouds.append(points)
            except Exception as error:  # noqa: BLE001 - overlay is optional
                logging.debug("Overlay could not read %s: %s", path, error)
        if not clouds:
            self.ghost_cloud = None
            return

        points = np.vstack(clouds).astype(np.float32)
        colour = np.array([0.45, 0.45, 0.55], dtype=np.float32)
        colors = np.tile(colour, (len(points), 1))
        ghost = PointCloud(
            path=self.pcd_manager.pcd_path,
            points=points,
            colors=colors,
            write_buffer=True,
        )
        # share the transform of the current cloud so both are drawn in the same place
        ghost.pcd_mins = pointcloud.pcd_mins
        ghost.pcd_maxs = pointcloud.pcd_maxs
        ghost.set_translations(*pointcloud.get_translation())
        ghost.set_rotations(*pointcloud.get_rotations())
        self.ghost_cloud = ghost
        logging.info("Overlaying %s previous frames (%s points).", len(clouds), len(points))

    # FRAME LOADING: STATUS, CLASS PIN, PREDICTION

    def warn_about_rotation_unit(self) -> None:
        """Tell the user once when a folder's label files can only be in degrees.

        ``LabelManager`` flags the frames it reads; a mismatch means every box of the
        folder is rotated wrongly, which is worth one loud sentence.
        """
        if self.rotation_unit_warned:
            return
        guard = getattr(
            getattr(self.pcd_manager, "label_manager", None), "format_guard", None
        )
        if not getattr(guard, "mismatches", None):
            return
        self.rotation_unit_warned = True
        self.view.status_manager.set_message(
            QCoreApplication.translate(
                "labelCloud", "These label files store rotations in degrees, but this session reads radians: the boxes are rotated wrongly. Check the class configuration."
            )
        )

    def on_frame_loaded(self, prediction_sources, previous_bboxes) -> None:
        """Common work after a frame was loaded."""
        pcd_path = getattr(self.pcd_manager, "pcd_path", None)
        if pcd_path is not None:
            self.record_load(pcd_path)
        # Select the first box of the frame (and deselect when there is none), like
        # upstream did: the box actions (refit, carry forward) need an active box,
        # and having to click one first is pure friction right after a frame load.
        self.bbox_controller.set_active_bbox(0)
        self.apply_next_class_to_view()
        self.predict_into_current_frame(prediction_sources, previous_bboxes)
        self.refresh_ghost_cloud(force=True)
        self.warn_about_rotation_unit()

    def capture_prediction_sources(self):
        """Boxes of the current frame plus how many points each one holds.

        Collected *before* switching frames, because the check for "is this object
        still there?" compares the new frame's point count against the old one's.
        """
        if not config.getboolean("LABEL", "predict_next_frame", fallback=False):
            return []
        pointcloud = self.pcd_manager.pointcloud
        if pointcloud is None:
            return []
        sources = []
        # only decided boxes are a basis for the next frame: predicting from an
        # unconfirmed proposal would build a guess on top of a guess
        for bbox in self.bbox_controller.confirmed_boxes():
            try:
                count = int(bbox.is_inside(pointcloud.points).sum())
            except Exception:  # noqa: BLE001 - prediction must never break loading
                count = 0
            state = BBoxState.from_bbox(bbox)
            sources.append((state, count, PointHistory.from_bbox(bbox)))
        return sources

    def predict_into_current_frame(self, sources, previous_bboxes) -> int:
        """Show boxes predicted from the previous frame in the frame just loaded."""
        if self.bbox_controller.bboxes and not config.getboolean(
            "LABEL", "predict_over_existing", fallback=False
        ):
            # by default a frame with its own labels is left alone; the option exists
            # for the "predict anyway and compare" workflow
            return 0

        if sources:
            predicted, dropped = self.predict_from(sources)
            if predicted:
                # proposals stay unconfirmed (and unwritten) until Enter
                confirmed = not any(box.candidate for box in predicted)
                added = self.bbox_controller.add_predicted(predicted, confirmed=confirmed)
                self.view.status_manager.set_message(
                    QCoreApplication.translate(
                        "labelCloud", "Predicted %s boxes from the previous frame (%s dropped)."
                    )
                    % (added, dropped)
                )
                return added
            if dropped:
                self.view.status_manager.set_message(
                    QCoreApplication.translate(
                        "labelCloud", "No box predicted: the objects are no longer there."
                    )
                )
            return 0

        # legacy upstream behaviour, kept working (and now actually saved)
        if previous_bboxes and config.getboolean("LABEL", "propagate_labels", fallback=False):
            copies = [BBoxState.from_bbox(bbox).to_bbox() for bbox in previous_bboxes]
            # propagate_labels means "these are the labels of this frame"
            self.bbox_controller.add_predicted(copies, confirmed=True)
            return len(copies)
        return 0

    def predict_from(self, sources):
        """Turn (box, previous point count) pairs into predictions for this frame.

        The size and orientation are carried over (the objects are rigid), the
        position is optionally re-fitted to the points inside, and a box whose
        points have nearly disappeared is dropped: that is the signal that the
        object is behind the vehicle and should not be predicted any more.
        """
        from . import assist

        pointcloud = self.pcd_manager.pointcloud
        if pointcloud is None:
            return [], len(sources)
        points = pointcloud.points

        sources = [
            (entry[0], entry[1], entry[2]) if len(entry) == 3
            else (entry[0], entry[1], PointHistory())
            for entry in sources
        ]
        min_points = config.getint("LABEL", "predict_min_points", fallback=DEFAULT_MIN_POINTS)
        ratio = config.getfloat("LABEL", "predict_min_point_ratio", fallback=DEFAULT_RATIO)
        sensitivity = config.getfloat(
            "LABEL", "predict_sensitivity", fallback=DEFAULT_SENSITIVITY
        )
        adaptive = config.getboolean("LABEL", "predict_adaptive", fallback=True)
        do_refit = config.getboolean("LABEL", "predict_refit", fallback=True)
        as_candidates = config.getboolean("LABEL", "predict_as_candidates", fallback=True)

        use_motion = config.getboolean("LABEL", "predict_use_motion", fallback=True)
        predicted, dropped = [], 0
        for state, previous_count, history in sources:
            bbox = state.to_bbox()

            # --- follow the object's motion instead of copying the last box ------
            if use_motion:
                velocity = history.velocity()
                if velocity is not None:
                    centre = bbox.get_center()
                    bbox.set_x_translation(centre[0] + velocity[0])
                    bbox.set_y_translation(centre[1] + velocity[1])
                    bbox.set_z_translation(centre[2] + velocity[2])
                yaw_velocity = history.yaw_velocity()
                if yaw_velocity:
                    bbox.set_z_rotation(bbox.get_z_rotation() + yaw_velocity)
                stable = history.stable_dimensions()
                # Size is rigid, so the median of the last frames beats a single
                # (possibly badly fitted) box. A locked box keeps exactly its size.
                if stable and not getattr(bbox, "locked", False):
                    bbox.set_dimensions(*stable)

            try:
                count = int(bbox.is_inside(points).sum())
            except Exception:  # noqa: BLE001
                count = 0
            keep, mode = decide(
                count, history, ratio, min_points, sensitivity, adaptive
            )
            if not keep:
                logging.info(
                    "Dropping the prediction of a %s box: %s points left "
                    "(previous frame %s, %s rule).",
                    bbox.get_classname(),
                    count,
                    previous_count,
                    mode,
                )
                dropped += 1
                continue
            history.observe(count, bbox)
            if do_refit:
                refitted = assist.refit_box(bbox, points)
                if refitted is not None:
                    refitted.candidate = as_candidates
                    history.attach_to(refitted)
                    predicted.append(refitted)
                    continue
            bbox.candidate = as_candidates
            history.attach_to(bbox)
            predicted.append(bbox)
        return predicted, dropped

    def prediction_summary(self) -> str:
        """One line describing the prediction state, for the session panel."""
        if not config.getboolean("LABEL", "predict_next_frame", fallback=False):
            return QCoreApplication.translate("labelCloud", "Prediction: off")
        ratio = int(
            100 * config.getfloat("LABEL", "predict_min_point_ratio", fallback=DEFAULT_RATIO)
        )
        adaptive = config.getboolean("LABEL", "predict_adaptive", fallback=True)
        mode = (
            QCoreApplication.translate("labelCloud", "adaptive %s%%") % ratio
            if adaptive
            else QCoreApplication.translate("labelCloud", "fixed %s%%") % ratio
        )
        return QCoreApplication.translate("labelCloud", "Prediction: on · %s") % mode

    def refresh_prediction_state(self) -> None:
        """Update anything that shows the prediction state."""
        view = getattr(self, "view", None)
        if view is None:
            return
        view.update_session_panel()

    def toggle_predict_next_frame(self, enabled: Optional[bool] = None) -> bool:
        """Turn the next-frame prediction on or off and persist it."""
        current = config.getboolean("LABEL", "predict_next_frame", fallback=False)
        value = (not current) if enabled is None else bool(enabled)
        config.set("LABEL", "predict_next_frame", str(value))
        from .config_manager import config_manager

        config_manager.write_into_file()
        logging.info("Predicting boxes for the next frame: %s.", value)
        view = getattr(self, "view", None)
        if view is not None:
            view.status_manager.set_message(
                QCoreApplication.translate("labelCloud", "Next-frame prediction enabled.")
                if value
                else QCoreApplication.translate(
                    "labelCloud", "Next-frame prediction disabled."
                )
            )
        return value

    # CONTROL METHODS
    def save(self, quiet: bool = False, force: bool = False) -> bool:
        """Save the current frame. Returns True on success.

        A failing save (read-only folder, full disk, another process holding the
        file) used to raise out of the event loop and take the edits with it. It is
        now reported loudly and the frame stays marked as unsaved.

        Unless ``force`` is set, a frame that was not edited is left alone: moving
        through a dataset used to rewrite every visited label file (changing its
        ``path`` field and creating a backup copy each time) even though nothing had
        been edited. ``Ctrl+S`` passes ``force`` so a frame can still be marked as
        deliberately checked and empty.
        """
        if not force and not self.bbox_controller.dirty:
            # Nothing was edited: browsing through a dataset must not create or
            # rewrite label files. Ctrl+S passes force=True, which is how a frame
            # gets recorded as "checked, and it is empty".
            self.refresh_save_state()
            return True

        try:
            written = self.pcd_manager.save_labels_into_file(
                self.bbox_controller.confirmed_boxes()
            )
            if written is False:
                # the format guard refused: the file holds another encoding, so
                # nothing was written. Reporting "saved" here (and clearing the dirty
                # flag) used to lose the edits silently.
                self.save_error_count += 1
                self.record_save(
                    self.label_file_path(), False, "another label format on disk"
                )
                self.view.status_manager.set_message(
                    QCoreApplication.translate(
                        "labelCloud",
                        "NOT saved: this file holds labels in another format "
                        "(see the log). Nothing was written."
                    )
                )
                logging.error(
                    "Refused to overwrite %s: it holds another label format.",
                    self.label_file_path(),
                )
                return False

            if LabelConfig().type == LabelingMode.SEMANTIC_SEGMENTATION:
                assert self.pcd_manager.pointcloud is not None
                self.pcd_manager.pointcloud.save_segmentation_labels()
        except Exception as error:  # noqa: BLE001 - must never kill the event loop
            logging.error("Could not save the labels: %s", error, exc_info=True)
            self.save_error_count += 1
            self.record_save(self.label_file_path(), False, str(error))
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
                        "permissions and free space."
                    )
                    % error,
                )
            return False

        self.bbox_controller.dirty = False
        self.record_save(self.label_file_path(), True, "")
        if not quiet:
            logging.info("Saved labels of %s.", self.pcd_manager.pcd_path)
        return True

    def label_file_path(self):
        """Path the current frame is written to (best effort).

        Must never raise: it is used while *reporting* a failed save, and an
        exception there would replace the useful error message with a traceback.
        """
        try:
            # `pcd_path` is a property that indexes the file list, so it raises
            # IndexError while no point cloud is loaded — and this runs from the
            # 20 ms GUI loop, where an exception would take the window down.
            pcd_path = self.pcd_manager.pcd_path
            manager = self.pcd_manager.label_manager
            return manager.label_folder.joinpath(
                pcd_path.stem + manager.label_strategy.FILE_ENDING
            )
        except (AttributeError, IndexError, TypeError):
            return Path("?")

    def record_load(self, path) -> None:
        """Remember which frame was loaded (shown in the status bar and log)."""
        self.record_save(path, True, "", kind="load")

    def record_save(self, path, ok: bool, message: str = "", kind: str = "save") -> None:
        """Remember a load or a write and refresh the status-bar indicator."""
        import time as _time

        path = str(path)
        name = shorten_filename(path)
        if kind == "load":
            self.activity_log.append(ActivityEntry(_time.time(), "load", path, True, ""))
            del self.activity_log[: max(0, len(self.activity_log) - self.SAVE_LOG_LIMIT)]
            self.view.status_manager.set_loaded_file(
                path,
                getattr(self.pcd_manager, "current_id", 0),
                len(getattr(self.pcd_manager, "pcds", []) or []),
            )
            return
        self.activity_log.append(
            ActivityEntry(_time.time(), "save", path, bool(ok), message)
        )
        del self.save_log[: max(0, len(self.save_log) - self.SAVE_LOG_LIMIT)]

        # the status bar has room for the file itself; the full path goes into the
        # tooltip (and the save log), because a long absolute path would push the
        # other indicators off the screen
        short = name if path not in ("", "?") else path
        if ok:
            stamp = _time.strftime("%H:%M:%S")
            self._last_saved_at = stamp
            self._last_saved_path = path
            self._last_save_state = "saved"
            self.view.status_manager.set_save_state(
                "saved", f"{stamp}  {short}", tooltip=path
            )
        else:
            self.view.status_manager.set_save_state(
                "failed", message[:60], tooltip=f"{path}\n{message}"
            )

    def refresh_save_state(self) -> None:
        """Keep the indicator in sync with the dirty flag (called from the loop)."""
        dirty = self.bbox_controller.dirty
        if dirty:
            if self._last_save_state != "dirty":
                self.view.status_manager.set_save_state("dirty")
            self._last_save_state = "dirty"
            return

        # not edited: either already on disk, or nothing to write at all
        path = self.label_file_path()
        if path in (Path("?"), None):
            self._last_save_state = "unknown"
            return
        exists = False
        try:
            exists = path.is_file()
        except OSError:
            exists = False
        short = shorten_filename(path, keep=18)
        if exists:
            if self._last_save_state != "saved":
                detail = "  ".join(
                    part for part in (getattr(self, "_last_saved_at", ""), short) if part
                )
                self.view.status_manager.set_save_state(
                    "saved", detail, tooltip=str(path)
                )
        elif self._last_save_state != "unchanged":
            self.view.status_manager.set_save_state(
                "unchanged",
                short,
                tooltip=QCoreApplication.translate(
                    "labelCloud",
                    "This frame was not edited, so nothing is written to %s."
                )
                % path,
            )
        self._last_save_state = "saved" if exists else "unchanged"

    def cancel_background_passes(self) -> None:
        """Ask every running background pass to stop (called when the window closes).

        ``LabelPassWorker.cancel`` sets a flag the pass checks before each frame, so the
        application stops writing labels instead of finishing the queue invisibly.
        """
        for name in ("propagate_worker", "preannotate_worker"):
            worker = getattr(self, name, None)
            if worker is not None and hasattr(worker, "cancel"):
                worker.cancel()

    def cmd_toggle_predict_next_frame(self, factor: float = 1.0) -> None:
        self.toggle_predict_next_frame()

    def cmd_show_save_log(self, factor: float = 1.0) -> None:
        from ..view.save_log_dialog import SaveLogDialog

        SaveLogDialog(
            self.view,
            self.save_log,
            str(self.pcd_manager.label_manager.label_folder),
        ).exec_()

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
        if self.drag_target is not None:
            # a gesture owns the highlight: recomputing it moves the red side to
            # whatever the growing box happens to be under the cursor (flicker)
            pass
        elif (
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
        """Triggers actions when the user presses the mouse."""
        self.last_cursor_pos = a0.pos()
        self.drag_start_pos = a0.pos()
        # Trust the event's own modifiers as well as the key state: the key flag is
        # only set by a KeyPress event, so pressing Ctrl after the button went down
        # (or losing the KeyPress to another widget) used to change the gesture.
        ctrl_held = bool(self.ctrl_pressed or (a0.modifiers() & Keys.ControlModifier))

        # Building a box happens on *release* and only for a real click: dragging
        # to rotate the cloud while a drawing mode is armed used to drop a box at
        # the release position, which is how a stray (and huge) box appeared every
        # time the fit mode was left switched on.
        if (
            (a0.buttons() & Keys.LeftButton)
            and (not ctrl_held)
            and (self.drawing_mode.is_active() or self.align_mode.is_active)
        ):
            self.pending_draw_kind = (
                "drawing" if self.drawing_mode.is_active() else "align"
            )
            return

        if (a0.buttons() & Keys.LeftButton) and (
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
                self.drag_target = "rotate"
                self.bbox_controller.begin_drag("Rotate around z")

        elif self.selected_side and not ctrl_held:
            # freeze the side now; the hovered side can change while dragging.
            # Ctrl is excluded on purpose: Ctrl+drag is labelCloud's own "rotate the
            # box" gesture, and stealing it for resizing broke the muscle memory of
            # everyone who used the original tool.
            self.begin_face_drag(self.selected_side)

        elif (a0.buttons() & Keys.LeftButton) and (not ctrl_held):
            # dragging the box body moves it; dragging anywhere else navigates
            if self.start_bbox_drag(a0):
                self.drag_target = "box"

    #: which bounding box dimension a side belongs to (length, width, height)
    SIDE_DIMENSION_INDEX = {
        "left": 0,
        "right": 0,
        "front": 1,
        "back": 1,
        "bottom": 2,
        "top": 2,
    }

    def begin_face_drag(self, side: str) -> bool:
        bbox = self.bbox_controller.get_active_bbox()
        if bbox is None or side not in self.SIDE_DIMENSION_INDEX:
            return False
        self.drag_target = "face"
        self.drag_side = side
        self.drag_start_extent = bbox.get_dimensions()[
            self.SIDE_DIMENSION_INDEX[side]
        ]
        self.side_mode = True
        self.bbox_controller.begin_drag("Resize bounding box")
        return True

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
        self.bbox_controller.begin_drag("Move bounding box")
        return True

    def mouse_released(self, a0: QtGui.QMouseEvent) -> None:
        """End the gesture, and register a drawing click if it really was a click."""
        if self.pending_draw_kind is not None:
            kind = self.pending_draw_kind
            self.pending_draw_kind = None
            moved = 0
            if self.drag_start_pos is not None:
                delta = a0.pos() - self.drag_start_pos
                moved = abs(delta.x()) + abs(delta.y())
            if moved <= self.CLICK_MAX_MOVE_PX:
                if kind == "drawing" and self.drawing_mode.is_active():
                    self.drawing_mode.register_point(
                        a0.x(), a0.y(), correction=True
                    )
                elif kind == "align" and self.align_mode.is_active:
                    self.align_mode.register_point(
                        self.view.gl_widget.get_world_coords(
                            a0.x(), a0.y(), correction=False
                        )
                    )

        if self.drag_target is not None:
            self.bbox_controller.end_drag()
        self.drag_target = None
        self.drag_side = None
        self.drag_start_pos = None
        self.drag_start_extent = None
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

            # --- an active gesture owns the mouse until it is released --------
            if self.drag_target == "box" and (a0.buttons() & Keys.LeftButton):
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
            if self.drag_target == "rotate" and (a0.buttons() & Keys.MiddleButton):
                active = self.bbox_controller.get_active_bbox()
                if active is not None:
                    active.set_z_rotation(active.get_z_rotation() - dx * 5.0)
                self.last_cursor_pos = a0.pos()
                return
            if self.drag_target == "face" and (a0.buttons() & Keys.LeftButton):
                # Absolute target: extent at press time plus the *total* vertical
                # movement. Incremental deltas made the box chase the cursor and
                # visibly vibrate, because every resize also moves the box centre.
                bbox = self.bbox_controller.get_active_bbox()
                if bbox is not None and self.drag_start_extent is not None:
                    index = self.SIDE_DIMENSION_INDEX.get(self.drag_side or "", 0)
                    total = (self.drag_start_pos.y() - a0.y()) if self.drag_start_pos else 0
                    target = self.drag_start_extent + total / self.FACE_DRAG_PIXELS_PER_METER
                    current = bbox.get_dimensions()[index]
                    self.bbox_controller.resize_side(self.drag_side, target - current)
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

            # Reset the wheel-scroll lock on significant movement, but never while
            # a gesture is being dragged (that is what made face resizing jitter)
            if self.drag_target is None and (
                dx > Controller.MOVEMENT_THRESHOLD
                or dy > Controller.MOVEMENT_THRESHOLD
            ):
                self.side_mode = False
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
        "go_to_frame": "cmd_go_to_frame",
        "quality_check": "cmd_show_quality_check",
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
        "refit_box_settings": "cmd_refit_with_settings",
        "propagate_to_end": "cmd_propagate_to_end",
        "set_interpolation_anchor": "cmd_set_interpolation_anchor",
        "interpolate_to_here": "cmd_interpolate_to_here",
        "preannotate_frame": "cmd_preannotate_frame",
        "accept_candidate": "cmd_accept_candidate",
        "next_candidate": "cmd_next_candidate",
        "prev_candidate": "cmd_prev_candidate",
        "reject_candidates": "cmd_reject_candidates",
        "flip_180": "cmd_flip_180",
        "show_statistics": "cmd_show_statistics",
        "show_save_log": "cmd_show_save_log",
        "toggle_predict_next_frame": "cmd_toggle_predict_next_frame",
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
        # explicit save: also writes an untouched frame, which is how a frame is
        # marked as "checked, nothing in it"
        self.save(force=True)

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
        elif self.drawing_mode.is_active() or self.align_mode.is_active:
            # Esc really leaves the drawing mode: the buttons follow, so the checked
            # button always says which mode the next click starts
            self.view.activate_pointer_mode()
            logging.info("Resetted the active drawing mode!")
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

    def new_box_class(self) -> str:
        """Class a newly created box should get."""
        if self.next_box_class:
            return self.next_box_class
        return LabelConfig().get_default_class_name()

    def set_next_box_class(self, classname: Optional[str]) -> None:
        """Pin the class used for new boxes (``None`` = follow the active one)."""
        self.next_box_class = classname or None
        logging.info(
            "New boxes use class '%s'.",
            self.next_box_class or "the active/default class",
        )
        self.apply_next_class_to_view()

    def apply_next_class_to_view(self) -> None:
        """Show the pinned class in the dropdown while no box is selected."""
        if self.next_box_class and not self.bbox_controller.has_active_bbox():
            self.view.current_class_dropdown.setCurrentText(self.next_box_class)

    def _current_class(self) -> str:
        if self.bbox_controller.has_active_bbox():
            return self.bbox_controller.get_classname()
        return self.new_box_class()

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
        """Refit the active box to its object (Ctrl+R)."""
        if self.bbox_controller.get_active_bbox() is None:
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "Select a box first, then refit it."
                )
            )
            return
        self.refit_active_box_with_feedback()

    def refit_active_box_with_feedback(self) -> bool:
        """Refit the active box and report what changed (used by settings + key)."""
        from . import assist

        pointcloud = self.pcd_manager.pointcloud
        bbox = self.bbox_controller.get_active_bbox()
        if pointcloud is None or bbox is None:
            return False
        if self.bbox_controller.is_active_locked():
            self.bbox_controller.warn_dimensions_locked()
            return False
        before = bbox.get_dimensions()
        refitted = assist.refit_box(bbox, pointcloud.points)
        if refitted is None:
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "Not enough points inside the box to refit it."
                )
            )
            return False
        self.bbox_controller.replace_active_bbox(refitted, "Refit bounding box")
        after = refitted.get_dimensions()
        self.view.update_bbox_stats(refitted)
        self.view.status_manager.set_message(
            QCoreApplication.translate(
                "labelCloud", "Refit: length %.2f -> %.2f, height %.2f -> %.2f m."
            )
            % (before[0], after[0], before[2], after[2])
        )
        return True

    def cmd_refit_with_settings(self, factor: float = 1.0) -> None:
        """Refit without asking (Ctrl+Shift+R) — the settings live in the dialog."""
        self.refit_active_box_with_feedback()

    # KEYFRAME INTERPOLATION

    def cmd_set_interpolation_anchor(self, factor: float = 1.0) -> None:
        """Remember the active box as the first keyframe."""
        bbox = self.bbox_controller.get_active_bbox()
        if bbox is None:
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "Select a box first: it becomes the first keyframe."
                )
            )
            return
        self.interpolation_anchor = (
            self.pcd_manager.current_id,
            BBoxState.from_bbox(bbox),
        )
        self.view.status_manager.set_message(
            QCoreApplication.translate(
                "labelCloud", "Keyframe 1 set on frame %s (%s)."
            )
            % (self.pcd_manager.current_id + 1, bbox.get_classname())
        )
        self.view.update_session_panel()
        logging.info("Interpolation anchor set on frame %s.", self.pcd_manager.current_id)

    def cmd_interpolate_to_here(self, factor: float = 1.0) -> None:
        """Fill the frames between the anchor keyframe and the current box."""
        from .propagate_worker import InterpolationWorker

        if self.interpolation_anchor is None:
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud",
                    "Set a keyframe first (Ctrl+Shift+I) in the earlier frame."
                )
            )
            return
        if self.propagate_worker is not None and self.propagate_worker.isRunning():
            self.view.status_manager.set_message(
                QCoreApplication.translate("labelCloud", "A fill job is still running ...")
            )
            return

        anchor_index, anchor_state = self.interpolation_anchor
        target_index = self.pcd_manager.current_id
        target = self.bbox_controller.get_active_bbox()
        if target is None:
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "Select the box of the second keyframe in this frame."
                )
            )
            return
        if target_index <= anchor_index:
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "The second keyframe must be a later frame."
                )
            )
            return

        frames = list(self.pcd_manager.pcds[anchor_index + 1 : target_index])
        if not frames:
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "The two keyframes are adjacent: nothing to fill."
                )
            )
            return

        worker = InterpolationWorker(
            anchor_state.to_bbox(),
            BBoxState.from_bbox(target).to_bbox(),
            frames,
            self.pcd_manager.label_manager,
            self.view,
        )
        worker.progress.connect(self.on_propagate_progress)
        worker.finished_ok.connect(self.on_interpolation_done)
        worker.failed.connect(self.on_propagate_failed)
        self.propagate_worker = worker
        self.view.status_manager.set_message(
            QCoreApplication.translate(
                "labelCloud", "Interpolating %s frames between the keyframes ..."
            )
            % len(frames)
        )
        worker.start()

    def on_interpolation_done(self, outcome) -> None:
        self.bbox_controller.dirty = True
        message = QCoreApplication.translate(
            "labelCloud", "Interpolation: %s"
        ) % outcome.reason
        self.view.status_manager.set_message(message)
        logging.info("Interpolation finished: %s", message)
        self.refresh_save_state()
        self.view.update_session_panel()

    # PROPAGATE ONE BOX THROUGH THE FOLLOWING FRAMES

    def cmd_propagate_to_end(self, factor: float = 1.0) -> None:
        """Follow the active box forward until its object leaves the view."""
        from .prediction import PointHistory
        from .propagate_worker import PropagateWorker

        if self.propagate_worker is not None and self.propagate_worker.isRunning():
            self.view.status_manager.set_message(
                QCoreApplication.translate("labelCloud", "Propagation is still running ...")
            )
            return

        bbox = self.bbox_controller.get_active_bbox()
        pointcloud = self.pcd_manager.pointcloud
        if bbox is None or pointcloud is None:
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "Select a box first: it will be carried forward."
                )
            )
            return

        current_id = self.pcd_manager.current_id
        frames = list(self.pcd_manager.pcds[current_id + 1 :])
        if not frames:
            self.view.status_manager.set_message(
                QCoreApplication.translate("labelCloud", "There are no later frames.")
            )
            return

        # seed the history with this frame so the motion model has a starting point
        try:
            count = int(bbox.is_inside(pointcloud.points).sum())
        except Exception:  # noqa: BLE001
            count = 0
        history = PointHistory()
        history.observe(count, bbox)

        worker = PropagateWorker(
            bbox, history, frames, self.pcd_manager.label_manager, self.view
        )
        worker.progress.connect(self.on_propagate_progress)
        worker.finished_ok.connect(self.on_propagate_done)
        worker.failed.connect(self.on_propagate_failed)
        self.propagate_worker = worker
        self.view.status_manager.set_message(
            QCoreApplication.translate(
                "labelCloud", "Carrying the box forward through the next frames ..."
            )
        )
        worker.start()

    def on_propagate_progress(self, index: int, total: int, written: int) -> None:
        self.view.status_manager.set_message(
            QCoreApplication.translate(
                "labelCloud", "Propagating: frame %s/%s, %s written."
            )
            % (index + 1, total, written)
        )
        self.view.update_session_panel()

    def on_propagate_done(self, outcome) -> None:
        self.bbox_controller.dirty = True
        message = QCoreApplication.translate(
            "labelCloud", "Propagated to %s frames (%s skipped): %s."
        ) % (outcome.frames_written, outcome.frames_skipped, outcome.reason)
        self.view.status_manager.set_message(message)
        logging.info("Propagation finished: %s", message)
        self.view.update_session_panel()
        # the frames on disk changed, so refresh the statistics view if it is open
        self.refresh_save_state()

    def on_propagate_failed(self, message: str) -> None:
        self.view.status_manager.set_message(
            QCoreApplication.translate(
                "labelCloud", "Propagation failed - see the log for details."
            )
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
        self.view.update_session_panel()
        self.view.status_manager.set_message(
            QCoreApplication.translate(
                "labelCloud",
                "%s proposals added; Enter confirms one, Ctrl+Right jumps to the next."
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
            self.view.update_session_panel()
            self.view.status_manager.set_message(
                QCoreApplication.translate(
                    "labelCloud", "Confirmed. %s proposals left in this frame."
                )
                % remaining
            )

    def cmd_reject_candidates(self, factor: float = 1.0) -> None:
        rejected = self.bbox_controller.reject_all_candidates()
        if rejected:
            self.view.update_session_panel()
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

    def cmd_go_to_frame(self, index: int, factor: float = 1.0) -> None:
        """Jump to a frame of the folder (used by the quality check)."""
        index = int(index)
        if index < 0 or index >= len(self.pcd_manager.pcds):
            self.view.status_manager.set_message(
                QCoreApplication.translate("labelCloud", "There is no frame %s.")
                % (index + 1)
            )
            return
        if index == self.pcd_manager.current_id:
            return
        self.custom_pcd(index)
        self.bbox_controller.set_active_bbox(0)

    def cmd_show_quality_check(self, factor: float = 1.0) -> None:
        from ..view.quality_dialog import QualityDialog

        QualityDialog(self.view, self).exec_()

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
