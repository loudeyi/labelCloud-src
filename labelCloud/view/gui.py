import logging
import os
import re
import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Set

import pkg_resources
from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtCore import QCoreApplication, QEvent
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QAction,
    QActionGroup,
    QColorDialog,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMessageBox,
)

from ..control.config_manager import config
from ..definitions import Color3f, LabelingMode
from ..i18n import (
    CHINESE,
    ENGLISH,
    SYSTEM,
    current_setting,
    set_language,
)
from ..io.labels.config import LabelConfig
from ..io.pointclouds import BasePointCloudHandler
from ..labeling_strategies import (
    FittingStrategy,
    PickingStrategy,
    SpanningStrategy,
)
from ..model.point_cloud import PointCloud
from .settings_dialog import SettingsDialog  # type: ignore
from .startup.dialog import StartupDialog
from .status_manager import StatusManager, shorten_filename
from .viewer import GLWidget

if TYPE_CHECKING:
    from ..control.controller import Controller


def string_is_float(string: str, recect_negative: bool = False) -> bool:
    """Returns True if string can be converted to float"""
    try:
        decimal = float(string)
    except ValueError:
        return False
    if recect_negative and decimal < 0:
        return False
    return True


def set_floor_visibility(state: bool) -> None:
    logging.info(
        "%s floor grid (SHOW_FLOOR: %s).",
        "Activated" if state else "Deactivated",
        state,
    )
    config.set("USER_INTERFACE", "show_floor", str(state))


def set_orientation_visibility(state: bool) -> None:
    config.set("USER_INTERFACE", "show_orientation", str(state))


def set_zrotation_only(state: bool) -> None:
    config.set("USER_INTERFACE", "z_rotation_only", str(state))


def set_color_with_label(state: bool) -> None:
    config.set("POINTCLOUD", "color_with_label", str(state))


def set_keep_perspective(state: bool) -> None:
    config.set("USER_INTERFACE", "keep_perspective", str(state))


def set_propagate_labels(state: bool) -> None:
    config.set("LABEL", "propagate_labels", str(state))


# CSS file paths need to be set dynamically
STYLESHEET = """
    * {{
        background-color: #FFF;
        font-family: "DejaVu Sans", Arial;
    }}

    QMenu::item:selected {{
        background-color: #0000DD;
    }}

    QListWidget#label_list::item {{
        padding-left: 22px;
        padding-top: 7px;
        padding-bottom: 7px;
        background: url("{icons_dir}/cube-outline.svg") center left no-repeat;
    }}

    QListWidget#label_list::item:selected {{
        color: #FFF;
        border: none;
        background: rgb(0, 0, 255);
        background: url("{icons_dir}/cube-outline_white.svg") center left no-repeat, #0000ff;
    }}

    QComboBox#current_class_dropdown::item:checked{{
        color: gray;
    }}

    QComboBox#current_class_dropdown::item:selected {{
        color: #FFFFFF;
    }}

    QComboBox#current_class_dropdown{{
        selection-background-color: #0000FF;
    }}
"""


# The generated form class is kept around so the window can re-translate itself
# when the user switches the interface language (see `GUI.changeEvent`).
Ui_MainWindow, _QtBaseClass = uic.loadUiType(
    pkg_resources.resource_filename("labelCloud.resources.interfaces", "interface.ui")
)


class GUI(QtWidgets.QMainWindow, Ui_MainWindow):
    def __init__(self, control: "Controller") -> None:
        QtWidgets.QMainWindow.__init__(self)
        # `setupUi` instead of `uic.loadUi` so that the generated
        # `retranslateUi` stays reachable — that is what makes switching the
        # interface language work without restarting the application.
        self.setupUi(self)
        self.resize(1500, 900)
        self.setWindowTitle(self.tr("labelCloud"))
        self.setStyleSheet(
            STYLESHEET.format(
                icons_dir=str(
                    Path(__file__)
                    .resolve()
                    .parent.parent.joinpath("resources")
                    .joinpath("icons")
                    .as_posix()
                )
            )
        )

        # MENU BAR
        # File
        self.act_set_pcd_folder: QtWidgets.QAction
        self.act_set_label_folder: QtWidgets.QAction

        # Labels
        self.act_delete_all_labels: QtWidgets.QAction
        self.act_set_default_class: QtWidgets.QMenu
        self.actiongroup_default_class = QActionGroup(self.act_set_default_class)
        self.act_propagate_labels: QtWidgets.QAction

        # Settings
        self.act_z_rotation_only: QtWidgets.QAction
        self.act_color_with_label: QtWidgets.QAction
        self.act_show_floor: QtWidgets.QAction
        self.act_show_orientation: QtWidgets.QAction
        self.act_save_perspective: QtWidgets.QAction
        self.act_align_pcd: QtWidgets.QAction
        self.act_change_settings: QtWidgets.QAction
        self.act_show_shortcuts: QtWidgets.QAction

        # Settings > Language
        self.menuLanguage: QtWidgets.QMenu
        self.act_language_system: QtWidgets.QAction
        self.act_language_en: QtWidgets.QAction
        self.act_language_zh_cn: QtWidgets.QAction
        self.actiongroup_language = QActionGroup(self.menuLanguage)
        for _action in (
            self.act_language_system,
            self.act_language_en,
            self.act_language_zh_cn,
        ):
            _action.setActionGroup(self.actiongroup_language)
        self.language_actions = {
            SYSTEM: self.act_language_system,
            ENGLISH: self.act_language_en,
            CHINESE: self.act_language_zh_cn,
        }
        self.update_language_menu()

        # STATUS BAR
        self.status_bar: QtWidgets.QStatusBar
        self.status_manager = StatusManager(self.status_bar)
        self.status_manager.on_change = lambda: self.update_session_panel()

        # CENTRAL WIDGET
        self.gl_widget: GLWidget

        # LEFT PANEL
        # point cloud management
        self.label_current_pcd: QtWidgets.QLabel
        self.button_prev_pcd: QtWidgets.QPushButton
        self.button_next_pcd: QtWidgets.QPushButton
        self.button_set_pcd: QtWidgets.QPushButton
        self.progressbar_pcds: QtWidgets.QProgressBar
        self.accumulate_label: QtWidgets.QLabel
        self.spin_accumulate_frames: QtWidgets.QSpinBox

        # bbox control section
        self.combo_step_parameter: QtWidgets.QComboBox
        self.button_step_decrease: QtWidgets.QPushButton
        self.button_step_increase: QtWidgets.QPushButton
        self.button_bbox_up: QtWidgets.QPushButton
        self.button_bbox_down: QtWidgets.QPushButton
        self.button_bbox_left: QtWidgets.QPushButton
        self.button_bbox_right: QtWidgets.QPushButton
        self.button_bbox_forward: QtWidgets.QPushButton
        self.button_bbox_backward: QtWidgets.QPushButton
        self.dial_bbox_z_rotation: QtWidgets.QDial
        self.button_bbox_decrease_dimension: QtWidgets.QPushButton
        self.button_bbox_increase_dimension: QtWidgets.QPushButton

        # 2d image viewer
        self.button_show_image: QtWidgets.QPushButton
        self.button_show_image.setVisible(
            config.getboolean("USER_INTERFACE", "show_2d_image")
        )

        # label mode selection
        self.button_pointer: QtWidgets.QPushButton
        self.button_pick_bbox: QtWidgets.QPushButton
        self.button_span_bbox: QtWidgets.QPushButton
        self.button_fit_bbox: QtWidgets.QPushButton
        self.button_save_label: QtWidgets.QPushButton

        # RIGHT PANEL
        self.label_list: QtWidgets.QListWidget
        self.current_class_dropdown: QtWidgets.QComboBox
        self.next_class_title: QtWidgets.QLabel
        self.combo_next_class: QtWidgets.QComboBox

        # right panel: frame / saving / activity card
        self.frame_session: QtWidgets.QFrame
        self.session_title: QtWidgets.QLabel
        self.session_frame_label: QtWidgets.QLabel
        self.session_save_label: QtWidgets.QLabel
        self.session_recent_label: QtWidgets.QLabel
        self.session_predict_label: QtWidgets.QLabel
        self.button_show_activity_log: QtWidgets.QPushButton
        self.button_prediction_settings: QtWidgets.QPushButton
        self.button_refit_settings: QtWidgets.QPushButton
        self.button_deselect_label: QtWidgets.QPushButton
        self.button_delete_label: QtWidgets.QPushButton
        self.button_assign_label: QtWidgets.QPushButton

        # label list actions
        # self.act_rename_class = QtWidgets.QAction("Rename class") #TODO: Implement!
        self.act_change_class_color = QtWidgets.QAction("Change class color")
        self.act_delete_class = QtWidgets.QAction("Delete label")
        self.act_crop_pointcloud_inside = QtWidgets.QAction("Save points inside as")
        self.label_list.addActions(
            [
                self.act_change_class_color,
                self.act_delete_class,
                self.act_crop_pointcloud_inside,
            ]
        )
        self.label_list.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        # BOUNDING BOX PARAMETER EDITS
        self.edit_pos_x: QtWidgets.QLineEdit
        self.edit_pos_y: QtWidgets.QLineEdit
        self.edit_pos_z: QtWidgets.QLineEdit

        self.edit_length: QtWidgets.QLineEdit
        self.edit_width: QtWidgets.QLineEdit
        self.edit_height: QtWidgets.QLineEdit

        self.edit_rot_x: QtWidgets.QLineEdit
        self.edit_rot_y: QtWidgets.QLineEdit
        self.edit_rot_z: QtWidgets.QLineEdit

        self.all_line_edits = [
            self.edit_pos_x,
            self.edit_pos_y,
            self.edit_pos_z,
            self.edit_length,
            self.edit_width,
            self.edit_height,
            self.edit_rot_x,
            self.edit_rot_y,
            self.edit_rot_z,
        ]

        self.label_volume: QtWidgets.QLabel

        self.controller = control

        # Connect all events to functions
        self.connect_events()
        self.set_checkbox_states()  # tick in menu

        # Run startup dialog (skippable for a fixed dataset / class setup, which
        # is the normal case once the classes are settled)
        if config.getboolean("FILE", "skip_startup_dialog", fallback=False):
            logging.info("Startup dialog skipped (FILE/skip_startup_dialog).")
        else:
            self.startup_dialog = StartupDialog()
            if not self.startup_dialog.exec():
                sys.exit()
        # Segmentation only functionalities
        if LabelConfig().type == LabelingMode.OBJECT_DETECTION:
            self.button_assign_label.setVisible(False)
            self.act_color_with_label.setVisible(False)

        # Connect with controller
        self.controller.startup(self)
        self.populate_next_class_dropdown()
        self.connect_persistence_signals()
        self.update_session_panel()

        # Start event cycle
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(20)  # period, in milliseconds
        self.timer.timeout.connect(self.controller.loop_gui)
        self.timer.start()

        # Periodic autosave so a crash cannot cost the current frame's work
        self.autosave_timer = QtCore.QTimer(self)
        interval_seconds = config.getint("LABEL", "autosave_interval_seconds", fallback=0)
        if interval_seconds > 0:
            self.autosave_timer.setInterval(interval_seconds * 1000)
            self.autosave_timer.timeout.connect(self.controller.autosave)
            self.autosave_timer.start()
            logging.info("Autosave every %s s.", interval_seconds)

    # Event connectors
    def connect_events(self) -> None:
        # POINTCLOUD CONTROL
        self.button_next_pcd.clicked.connect(
            lambda: self.controller.next_pcd(save=True)
        )
        self.button_prev_pcd.clicked.connect(self.controller.prev_pcd)

        # BBOX CONTROL
        self.button_bbox_up.pressed.connect(
            lambda: self.controller.bbox_controller.translate_along_z()
        )
        self.button_bbox_down.pressed.connect(
            lambda: self.controller.bbox_controller.translate_along_z(down=True)
        )
        self.button_bbox_left.pressed.connect(
            lambda: self.controller.bbox_controller.translate_along_x(left=True)
        )
        self.button_bbox_right.pressed.connect(
            self.controller.bbox_controller.translate_along_x
        )
        self.button_bbox_forward.pressed.connect(
            lambda: self.controller.bbox_controller.translate_along_y(forward=True)
        )
        self.button_set_pcd.pressed.connect(lambda: self.ask_custom_index())
        self.button_bbox_backward.pressed.connect(
            lambda: self.controller.bbox_controller.translate_along_y()
        )

        self.dial_bbox_z_rotation.valueChanged.connect(
            lambda x: self.controller.bbox_controller.rotate_around_z(x, absolute=True)
        )
        self.button_bbox_decrease_dimension.clicked.connect(
            lambda: self.controller.bbox_controller.scale(decrease=True)
        )

        # parameter stepper (±): no keyboard needed to fine-tune a value
        for _value, _label in self.controller.STEP_PARAMETERS:
            self.combo_step_parameter.addItem(self.tr(_label), _value)
        self.button_step_decrease.pressed.connect(
            lambda: self.step_selected_parameter(-1)
        )
        self.button_step_increase.pressed.connect(
            lambda: self.step_selected_parameter(1)
        )
        self.button_bbox_increase_dimension.clicked.connect(
            lambda: self.controller.bbox_controller.scale()
        )

        # LABELING CONTROL
        self.current_class_dropdown.currentTextChanged.connect(
            self.controller.bbox_controller.set_classname
        )
        self.combo_next_class.currentIndexChanged.connect(self.change_next_class)
        self.button_show_activity_log.clicked.connect(
            lambda: self.controller.cmd_show_save_log()
        )
        self.button_prediction_settings.clicked.connect(self.show_prediction_settings)
        self.button_refit_settings.clicked.connect(self.show_refit_settings)
        self.button_deselect_label.clicked.connect(
            self.controller.bbox_controller.deselect_bbox
        )
        self.button_delete_label.clicked.connect(
            self.controller.bbox_controller.delete_current_bbox
        )
        self.label_list.currentRowChanged.connect(
            self.controller.bbox_controller.set_active_bbox
        )
        self.button_assign_label.clicked.connect(
            self.controller.bbox_controller.assign_point_label_in_active_box
        )
        # context menu
        self.act_delete_class.triggered.connect(
            self.controller.bbox_controller.delete_current_bbox
        )
        self.act_crop_pointcloud_inside.triggered.connect(
            self.controller.crop_pointcloud_inside_active_bbox
        )
        self.act_change_class_color.triggered.connect(self.change_label_color)

        # open_2D_img
        self.button_show_image.pressed.connect(lambda: self.show_2d_image())

        # LABEL CONTROL
        self.spin_accumulate_frames.setValue(
            config.getint("POINTCLOUD", "accumulate_frames", fallback=0)
        )
        self.spin_accumulate_frames.valueChanged.connect(
            self.controller.set_accumulate_frames
        )
        self.button_pointer.clicked.connect(self.activate_pointer_mode)
        self.button_pick_bbox.clicked.connect(
            lambda: self.start_drawing_mode(PickingStrategy(self))
        )
        self.button_span_bbox.clicked.connect(
            lambda: self.start_drawing_mode(SpanningStrategy(self))
        )
        self.button_fit_bbox.clicked.connect(
            lambda: self.start_drawing_mode(FittingStrategy(self))
        )
        self.button_save_label.clicked.connect(self.controller.save)

        # BOUNDING BOX PARAMETER
        self.edit_pos_x.editingFinished.connect(
            lambda: self.update_bbox_parameter("pos_x")
        )
        self.edit_pos_y.editingFinished.connect(
            lambda: self.update_bbox_parameter("pos_y")
        )
        self.edit_pos_z.editingFinished.connect(
            lambda: self.update_bbox_parameter("pos_z")
        )

        self.edit_length.editingFinished.connect(
            lambda: self.update_bbox_parameter("length")
        )
        self.edit_width.editingFinished.connect(
            lambda: self.update_bbox_parameter("width")
        )
        self.edit_height.editingFinished.connect(
            lambda: self.update_bbox_parameter("height")
        )

        self.edit_rot_x.editingFinished.connect(
            lambda: self.update_bbox_parameter("rot_x")
        )
        self.edit_rot_y.editingFinished.connect(
            lambda: self.update_bbox_parameter("rot_y")
        )
        self.edit_rot_z.editingFinished.connect(
            lambda: self.update_bbox_parameter("rot_z")
        )

        # MENU BAR
        self.act_set_pcd_folder.triggered.connect(self.change_pointcloud_folder)
        self.act_set_label_folder.triggered.connect(self.change_label_folder)
        self.actiongroup_default_class.triggered.connect(
            self.change_default_object_class
        )
        self.act_delete_all_labels.triggered.connect(
            self.controller.bbox_controller.reset
        )
        # NOTE: the toggled handlers for these two are connected in
        # `connect_persistence_signals()` *after* the controller has a view —
        # restoring the saved checkbox state here must not write config.ini or
        # touch the status bar.
        self.act_z_rotation_only.toggled.connect(set_zrotation_only)
        self.act_color_with_label.toggled.connect(set_color_with_label)
        self.act_show_floor.toggled.connect(set_floor_visibility)
        self.act_show_orientation.toggled.connect(set_orientation_visibility)
        self.act_save_perspective.toggled.connect(set_keep_perspective)
        self.act_align_pcd.toggled.connect(self.controller.align_mode.change_activation)
        self.act_change_settings.triggered.connect(self.show_settings_dialog)
        self.act_show_shortcuts.triggered.connect(
            lambda: self.controller.cmd_show_shortcuts()
        )
        self.act_show_save_log.triggered.connect(
            lambda: self.controller.cmd_show_save_log()
        )
        # clicking the save indicator in the status bar opens the same log
        self.status_manager.save_label.mousePressEvent = (
            lambda _event: self.controller.cmd_show_save_log()
        )
        self.status_manager.load_label.mousePressEvent = (
            lambda _event: self.controller.cmd_show_save_log()
        )

        # ASSIST
        self.act_preannotate_frame.triggered.connect(
            lambda: self.controller.cmd_preannotate_frame()
        )
        self.act_accept_candidate.triggered.connect(
            lambda: self.controller.cmd_accept_candidate()
        )
        self.act_reject_candidates.triggered.connect(
            lambda: self.controller.cmd_reject_candidates()
        )
        self.act_fit_box.triggered.connect(
            lambda: self.controller.cmd_fit_box_at_cursor()
        )
        self.act_refit_box.triggered.connect(lambda: self.controller.cmd_refit_box())
        self.act_snap_box.triggered.connect(lambda: self.controller.cmd_snap_box())
        self.act_propagate_to_end.triggered.connect(
            lambda: self.controller.cmd_propagate_to_end()
        )
        self.act_flip_180.triggered.connect(lambda: self.controller.cmd_flip_180())
        self.act_show_statistics.triggered.connect(
            lambda: self.controller.cmd_show_statistics()
        )

        # LANGUAGE
        for setting, action in self.language_actions.items():
            action.triggered.connect(
                lambda _checked=False, s=setting: self.change_language(s)
            )

    # DRAWING MODES

    def activate_pointer_mode(self) -> None:
        """Leave every drawing mode: the mouse navigates again.

        Without this there was no way back from the sticky fit mode other than
        knowing that Esc also cancels drawing, and every further click kept
        producing boxes.
        """
        self.controller.drawing_mode.reset()
        self.controller.align_mode.reset()
        self.button_pointer.setChecked(True)
        self.button_pick_bbox.setChecked(False)
        self.button_span_bbox.setChecked(False)
        self.button_fit_bbox.setChecked(False)
        logging.info("Pointer mode: no drawing mode active.")

    def start_drawing_mode(self, strategy) -> None:
        """Arm a drawing mode (clicking its button again disarms it)."""
        self.button_pointer.setChecked(False)
        self.controller.drawing_mode.set_drawing_strategy(strategy)
        if not self.controller.drawing_mode.is_active():
            self.activate_pointer_mode()

    # NEXT-FRAME CLASS

    def populate_next_class_dropdown(self) -> None:
        """Fill the "new boxes in next frames" combo from the class list."""
        self.combo_next_class.blockSignals(True)
        current = self.controller.next_box_class
        self.combo_next_class.clear()
        self.combo_next_class.addItem(
            self.tr("Follow the active / default class"), None
        )
        for name in LabelConfig().get_classes():
            self.combo_next_class.addItem(name, name)
        index = self.combo_next_class.findData(current)
        self.combo_next_class.setCurrentIndex(index if index >= 0 else 0)
        self.combo_next_class.blockSignals(False)

    def change_next_class(self) -> None:
        value = self.combo_next_class.currentData()
        self.controller.set_next_box_class(value)

    def step_selected_parameter(self, direction: int) -> None:
        """Step the parameter chosen in the ± combo box."""
        parameter = self.combo_step_parameter.currentData()
        if parameter:
            self.controller.step_parameter(parameter, direction)

    # SESSION PANEL (frame / save state / recent activity / prediction)

    def update_session_panel(self) -> None:
        """Refresh the card in the right panel. Cheap: called often."""
        controller = self.controller
        pcd_path = getattr(controller.pcd_manager, "pcd_path", None)
        if pcd_path is None:
            self.session_frame_label.setText(self.tr("— no point cloud loaded"))
        else:
            total = len(getattr(controller.pcd_manager, "pcds", []) or [])
            index = getattr(controller.pcd_manager, "current_id", 0) + 1
            short = shorten_filename(pcd_path, keep=13)
            self.session_frame_label.setText(
                self.tr("Frame %s/%s · <b>%s</b>") % (index, total, short)
            )
            self.session_frame_label.setToolTip(str(pcd_path))

        state = self.status_manager.current_save_state()
        style = {
            "saved": "color: #1a7f37;",
            "dirty": "color: #c07000;",
            "failed": "color: #c0392b;",
            "unchanged": "color: #888;",
        }.get(state, "color: #888;")
        self.session_save_label.setStyleSheet(style)
        # the panel already lists the times in "recent", so keep this line short
        save_text = self.status_manager.save_label.text()
        saved_state = self.status_manager.current_save_state()
        if saved_state == "saved":
            save_text = self.tr("✓ saved · %s") % shorten_filename(
                getattr(controller, "_last_saved_path", ""), keep=13
            )
        self.session_save_label.setText(save_text)
        self.session_save_label.setToolTip(self.status_manager.save_label.toolTip())

        entries = list(getattr(controller, "activity_log", []))[-2:]
        lines = []
        for timestamp, kind, path, ok, _message in reversed(entries):
            import datetime

            when = datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M")
            name = shorten_filename(path, keep=13)
            verb = self.tr("loaded") if kind == "load" else self.tr("saved")
            lines.append(f"{when} {verb} {name}")
        self.session_recent_label.setText(
            self.tr("Recent:") + ("<br/>" + "<br/>".join(lines) if lines else " —")
        )
        if lines:
            self.session_recent_label.setToolTip("\n".join(str(e[2]) for e in entries))

        self.session_predict_label.setText(controller.prediction_summary())

    def show_refit_settings(self) -> None:
        from .refit_dialog import RefitSettingsDialog

        RefitSettingsDialog(self, self.controller).exec_()

    def show_prediction_settings(self) -> None:
        from .prediction_dialog import PredictionSettingsDialog

        PredictionSettingsDialog(self, self.controller).exec_()

    def connect_persistence_signals(self) -> None:
        """Connect the option checkboxes once the controller is functional."""
        self.act_propagate_labels.toggled.connect(self.change_propagate_labels)
        self.act_predict_next_frame.toggled.connect(self.change_predict_next_frame)

    def change_propagate_labels(self, state: bool) -> None:
        """Persist the "copy the previous frame's boxes" option."""
        config.set("LABEL", "propagate_labels", str(state))
        from ..control.config_manager import config_manager

        config_manager.write_into_file()
        logging.info("Propagate labels: %s.", state)

    def change_predict_next_frame(self, state: bool) -> None:
        self.controller.toggle_predict_next_frame(state)

    def set_checkbox_states(self) -> None:
        self.act_propagate_labels.setChecked(
            config.getboolean("LABEL", "propagate_labels")
        )
        self.act_predict_next_frame.setChecked(
            config.getboolean("LABEL", "predict_next_frame", fallback=False)
        )
        self.act_show_floor.setChecked(
            config.getboolean("USER_INTERFACE", "show_floor")
        )
        self.act_show_orientation.setChecked(
            config.getboolean("USER_INTERFACE", "show_orientation")
        )
        self.act_z_rotation_only.setChecked(
            config.getboolean("USER_INTERFACE", "z_rotation_only")
        )
        self.act_color_with_label.setChecked(
            config.getboolean("POINTCLOUD", "color_with_label")
        )

    # LANGUAGE

    def change_language(self, setting: str) -> None:
        """Switch the interface language immediately (no restart)."""
        language = set_language(setting, QtWidgets.QApplication.instance())
        logging.info("Interface language switched to %s (%s).", setting, language)
        self.update_language_menu()

    def update_language_menu(self) -> None:
        """Tick the menu entry matching the configured language."""
        setting = current_setting()
        for value, action in self.language_actions.items():
            action.setChecked(value == setting)

    def changeEvent(self, event) -> None:
        """Re-translate the window when Qt tells us the language changed."""
        if event.type() == QEvent.LanguageChange:
            self.retranslateUi(self)
            self.retranslate_custom_texts()
            self.update_language_menu()
        super().changeEvent(event)

    def retranslate_custom_texts(self) -> None:
        """Texts that are not part of the generated form.

        Window titles we set ourselves, and the transient status message, which
        would otherwise stay in the previous language until the next action.
        """
        self.setWindowTitle(self.tr("labelCloud"))
        self.status_manager.retranslate()
        pcd_path = getattr(self.controller.pcd_manager, "pcd_path", None)
        if pcd_path is not None:
            self.set_pcd_label(pcd_path.name)

    # Collect, filter and forward events to viewer
    def eventFilter(self, event_object, event) -> bool:
        # Keyboard Events
        if (event.type() == QEvent.KeyPress) and event_object in [
            self,
            self.label_list,  # otherwise steals focus for keyboard shortcuts
        ]:
            self.controller.key_press_event(event)
            self.update_bbox_stats(self.controller.bbox_controller.get_active_bbox())
            return True  # TODO: Recheck pyqt behaviour
        elif event.type() == QEvent.KeyRelease:
            self.controller.key_release_event(event)

        # Mouse Events
        elif (event.type() == QEvent.MouseMove) and (event_object == self.gl_widget):
            self.controller.mouse_move_event(event)
            self.update_bbox_stats(self.controller.bbox_controller.get_active_bbox())
        elif (event.type() == QEvent.Wheel) and (event_object == self.gl_widget):
            self.controller.mouse_scroll_event(event)
            self.update_bbox_stats(self.controller.bbox_controller.get_active_bbox())
        elif event.type() == QEvent.MouseButtonDblClick and (
            event_object == self.gl_widget
        ):
            self.controller.mouse_double_clicked(event)
            return True
        elif (event.type() == QEvent.MouseButtonPress) and (
            event_object == self.gl_widget
        ):
            self.controller.mouse_clicked(event)
            self.update_bbox_stats(self.controller.bbox_controller.get_active_bbox())
        elif (event.type() == QEvent.MouseButtonRelease) and (
            event_object == self.gl_widget
        ):
            self.controller.mouse_released(event)
        elif (event.type() == QEvent.MouseButtonPress) and (
            event_object != self.current_class_dropdown
        ):
            self.current_class_dropdown.clearFocus()
            self.update_bbox_stats(self.controller.bbox_controller.get_active_bbox())
        return False

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        logging.info("Closing window after saving ...")
        self.controller.save()
        self.autosave_timer.stop()
        self.timer.stop()
        a0.accept()

    def show_settings_dialog(self) -> None:
        dialog = SettingsDialog(self)
        dialog.exec()

    def show_2d_image(self):
        """Searches for a 2D image with the point cloud name and displays it in a new window."""
        image_folder = config.getpath("FILE", "image_folder")

        # Look for image files with the name of the point cloud
        pcd_name = self.controller.pcd_manager.pcd_path.stem
        image_file_pattern = re.compile(
            f"{pcd_name}+(\\.(?i:(jpe?g|png|gif|bmp|tiff)))"
        )

        try:
            image_name = next(
                filter(image_file_pattern.search, os.listdir(image_folder))
            )
        except StopIteration:
            QMessageBox.information(
                self,
                self.tr("No 2D Image File"),
                (
                    self.tr(
                        "Could not find a related image in the image folder (%s).\n"
                        "Check your path to the folder or if an image for this point cloud exists."
                    )
                    % image_folder
                ),
                QMessageBox.Ok,
            )
        else:
            image_path = image_folder.joinpath(image_name)
            image = QtGui.QImage(QtGui.QImageReader(str(image_path)).read())
            self.imageLabel = QLabel()
            self.imageLabel.setWindowTitle(self.tr("2D Image (%s)") % image_name)
            self.imageLabel.setPixmap(QPixmap.fromImage(image))
            self.imageLabel.show()

    def show_no_pointcloud_dialog(
        self, pcd_folder: Path, pcd_extensions: Set[str]
    ) -> None:
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setText(
            self.tr(
                "<b>labelCloud could not find any valid point cloud files inside the "
                "specified folder.</b>"
            )
        )
        msg.setInformativeText(
            self.tr(
                "Please copy all your point clouds into <code>%s</code> or update "
                "the point cloud folder location. labelCloud supports the following point "
                "cloud file formats:\n %s."
            )
            % (pcd_folder.resolve(), ", ".join(pcd_extensions))
        )
        msg.setWindowTitle(self.tr("No Point Clouds Found"))
        msg.exec_()

    # VISUALIZATION METHODS

    def set_pcd_label(self, pcd_name: str) -> None:
        self.label_current_pcd.setText(self.tr("Current: <em>%s</em>") % pcd_name)

    def init_progress(self, min_value, max_value):
        self.progressbar_pcds.setMinimum(min_value)
        self.progressbar_pcds.setMaximum(max_value)

    def update_progress(self, value) -> None:
        self.progressbar_pcds.setValue(value)

    def update_current_class_dropdown(self) -> None:
        self.controller.pcd_manager.populate_class_dropdown()

    def update_bbox_stats(self, bbox) -> None:
        viewing_precision = config.getint("USER_INTERFACE", "viewing_precision")
        if bbox and not self.line_edited_activated():
            self.edit_pos_x.setText(str(round(bbox.get_center()[0], viewing_precision)))
            self.edit_pos_y.setText(str(round(bbox.get_center()[1], viewing_precision)))
            self.edit_pos_z.setText(str(round(bbox.get_center()[2], viewing_precision)))

            self.edit_length.setText(
                str(round(bbox.get_dimensions()[0], viewing_precision))
            )
            self.edit_width.setText(
                str(round(bbox.get_dimensions()[1], viewing_precision))
            )
            self.edit_height.setText(
                str(round(bbox.get_dimensions()[2], viewing_precision))
            )

            self.edit_rot_x.setText(str(round(bbox.get_x_rotation(), 1)))
            self.edit_rot_y.setText(str(round(bbox.get_y_rotation(), 1)))
            self.edit_rot_z.setText(str(round(bbox.get_z_rotation(), 1)))

            self.label_volume.setText(str(round(bbox.get_volume(), viewing_precision)))

    def update_bbox_parameter(self, parameter: str) -> None:
        str_value = None
        self.setFocus()  # Changes the focus from QLineEdit to the window

        if parameter == "pos_x":
            str_value = self.edit_pos_x.text()
        if parameter == "pos_y":
            str_value = self.edit_pos_y.text()
        if parameter == "pos_z":
            str_value = self.edit_pos_z.text()
        if str_value and string_is_float(str_value):
            self.controller.bbox_controller.update_position(parameter, float(str_value))
            return

        if parameter == "length":
            str_value = self.edit_length.text()
        if parameter == "width":
            str_value = self.edit_width.text()
        if parameter == "height":
            str_value = self.edit_height.text()
        if str_value and string_is_float(str_value, recect_negative=True):
            self.controller.bbox_controller.update_dimension(
                parameter, float(str_value)
            )
            return

        if parameter == "rot_x":
            str_value = self.edit_rot_x.text()
        if parameter == "rot_y":
            str_value = self.edit_rot_y.text()
        if parameter == "rot_z":
            str_value = self.edit_rot_z.text()
        if str_value and string_is_float(str_value):
            self.controller.bbox_controller.update_rotation(parameter, float(str_value))
            return

    # Enables, disables the draw mode
    def activate_draw_modes(self, state: bool) -> None:
        self.button_pick_bbox.setEnabled(state)
        self.button_span_bbox.setEnabled(state)
        self.button_fit_bbox.setEnabled(state)

    def line_edited_activated(self) -> bool:
        for line_edit in self.all_line_edits:
            if line_edit.hasFocus():
                return True
        return False

    def change_pointcloud_folder(self) -> None:
        path_to_folder = Path(
            QFileDialog.getExistingDirectory(
                self,
                self.tr("Change Point Cloud Folder"),
                directory=config.get("FILE", "pointcloud_folder"),
            )
        )
        if not path_to_folder.is_dir():
            logging.warning("Please specify a valid folder path.")
        else:
            self.controller.pcd_manager.pcd_folder = path_to_folder
            self.controller.pcd_manager.read_pointcloud_folder()
            self.controller.pcd_manager.get_next_pcd()
            logging.info("Changed point cloud folder to %s!" % path_to_folder)

    def change_label_folder(self) -> None:
        path_to_folder = Path(
            QFileDialog.getExistingDirectory(
                self,
                self.tr("Change Label Folder"),
                directory=config.get("FILE", "label_folder"),
            )
        )
        if not path_to_folder.is_dir():
            logging.warning("Please specify a valid folder path.")
        else:
            self.controller.pcd_manager.label_manager.label_folder = path_to_folder
            self.controller.pcd_manager.label_manager.label_strategy.update_label_folder(
                path_to_folder
            )
            logging.info("Changed label folder to %s!" % path_to_folder)

    def update_default_object_class_menu(
        self, new_classes: Optional[Set[str]] = None
    ) -> None:
        object_classes = set(LabelConfig().get_classes())

        object_classes.update(new_classes or [])
        existing_classes = {
            action.text() for action in self.actiongroup_default_class.actions()
        }
        for object_class in object_classes.difference(existing_classes):
            action = self.actiongroup_default_class.addAction(
                object_class
            )  # TODO: Add limiter for number of classes
            action.setCheckable(True)
            if object_class == LabelConfig().get_default_class_name():
                action.setChecked(True)

        self.act_set_default_class.addActions(self.actiongroup_default_class.actions())
        self.populate_next_class_dropdown()

    def change_default_object_class(self, action: QAction) -> None:
        LabelConfig().set_default_class(action.text())
        logging.info("Changed default object class to %s.", action.text())

    def ask_custom_index(self):
        input_d = QInputDialog(self)
        self.input_pcd = input_d
        input_d.setInputMode(QInputDialog.IntInput)
        input_d.setWindowTitle(self.tr("labelCloud"))
        input_d.setLabelText(self.tr("Insert Point Cloud number: ()"))
        input_d.setIntMaximum(len(self.controller.pcd_manager.pcds) - 1)
        input_d.intValueChanged.connect(lambda val: self.update_dialog_pcd(val))
        input_d.intValueSelected.connect(lambda val: self.controller.custom_pcd(val))
        input_d.open()
        self.update_dialog_pcd(0)

    def update_dialog_pcd(self, value: int) -> None:
        pcd_path = self.controller.pcd_manager.pcds[value]
        self.input_pcd.setLabelText(
            self.tr("Insert Point Cloud number: %s") % pcd_path.name
        )

    def change_label_color(self):
        bbox = self.controller.bbox_controller.get_active_bbox()
        LabelConfig().set_class_color(
            bbox.classname, Color3f.from_qcolor(QColorDialog.getColor())
        )

    @staticmethod
    def save_point_cloud_as(pointcloud: PointCloud) -> None:
        extensions = BasePointCloudHandler.get_supported_extensions()
        make_filter = " ".join(["*" + extension for extension in extensions])
        file_filter = QCoreApplication.translate(
            "labelCloud", "Point Cloud File (%s)"
        ) % make_filter
        file_name, _ = QFileDialog.getSaveFileName(
            caption=QCoreApplication.translate(
                "labelCloud", "Select a file name to save the point cloud"
            ),
            directory=str(pointcloud.path.parent),
            filter=file_filter,
            initialFilter=file_filter,
        )
        if file_name == "":
            logging.warning("No file path provided. Ignored.")
            return

        try:
            path = Path(file_name)
            handler = BasePointCloudHandler.get_handler(path.suffix)
            handler.write_point_cloud(path, pointcloud)
        except Exception as e:
            msg = QMessageBox()
            msg.setWindowTitle(
                QCoreApplication.translate("labelCloud", "Failed to save a point cloud")
            )
            msg.setText(e.__class__.__name__)
            msg.setInformativeText(traceback.format_exc())
            msg.setIcon(QMessageBox.Critical)
            msg.setStandardButtons(QMessageBox.Cancel)
            msg.exec_()
