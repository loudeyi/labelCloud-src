#!/usr/bin/env python3
"""End-to-end smoke tests that drive the real GUI offscreen.

``tests/check_assist.py`` covers the logic in dependency-free subprocesses, but it
never builds a window: the wiring between a command, the dialog and the label files on
disk is exactly where the last few bugs lived. This script builds the real
``Controller`` + ``GUI`` with ``QT_QPA_PLATFORM=offscreen``, on a throwaway dataset, and
checks three flows end to end:

* **keyframe interpolation** — set an anchor, jump forward, interpolate, read back what
  was written;
* **quality check** — a folder with deliberate mistakes, the dialog's table, the
  jump-to-frame action, and the promise that the check writes nothing at all;
* **queued proposals** — the session card counts the unconfirmed proposals, the count
  follows confirm/reject, and queueing them writes no file;
* **Chinese session** — the menus, the object list, the parameter stepper, the quality
  window and the standard dialog buttons all come out translated.

Usage::

    python tools/smoke_gui.py            # every flow
    python tools/smoke_gui.py interp     # one flow (interp | quality | proposals | zh)

Every flow works in its own temporary directory and deletes it afterwards; nothing
outside the temporary directory is read or written.
"""
from __future__ import annotations

import configparser
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402

PCD_HEAD = """# .PCD v0.7 - Point Cloud Data file format
VERSION 0.7
FIELDS x y z
SIZE 4 4 4
TYPE F F F
COUNT 1 1 1
WIDTH {n}
HEIGHT 1
VIEWPOINT 0 0 0 1 0 0 0
POINTS {n}
DATA ascii
"""

CLASSES = {
    "classes": [
        {
            "name": "wire",
            "id": 1,
            "color": "#ff0000",
            "z_rotation_only": False,
            "default_dimensions": {"length": 0.2, "width": 20.0, "height": 0.2},
        },
        {
            "name": "pole",
            "id": 2,
            "color": "#00ff7f",
            "z_rotation_only": True,
            "default_dimensions": {"length": 2.6, "width": 4.0, "height": None},
        },
    ],
    "default": 2,
    "type": "object_detection",
    "format": "centroid_abs",
}


# --------------------------------------------------------------------------- #
#                                 tiny helpers                                 #
# --------------------------------------------------------------------------- #


def write_pcd(path: Path, points: np.ndarray) -> None:
    body = "\n".join(f"{x:.4f} {y:.4f} {z:.4f}" for x, y, z in points)
    path.write_text(PCD_HEAD.format(n=len(points)) + body + "\n")


def make_project(root: Path, language: str = "en") -> None:
    """A dataset folder the real application can open without a startup dialog."""
    (root / "pointclouds").mkdir(parents=True)
    (root / "labels").mkdir()
    (root / "labels" / "_classes.json").write_text(json.dumps(CLASSES))
    shutil.copy(REPO / "labelCloud/resources/default_config.ini", root / "config.ini")
    parser = configparser.ConfigParser()
    parser.read(root / "config.ini")
    parser["FILE"]["pointcloud_folder"] = "pointclouds"
    parser["FILE"]["label_folder"] = "labels"
    parser["FILE"]["skip_startup_dialog"] = "True"
    parser["USER_INTERFACE"]["language"] = language
    parser["LABEL"]["autosave_interval_seconds"] = "0"
    parser["LABEL"]["predict_next_frame"] = "False"
    with (root / "config.ini").open("w") as handle:
        parser.write(handle)
    os.chdir(root)


def boot(language: str = "en"):
    """Build the application the way ``labelCloud.__main__`` does."""
    from PyQt5.QtWidgets import QApplication

    from labelCloud.control.controller import Controller
    from labelCloud.i18n import install_language
    from labelCloud.view.gui import GUI

    app = QApplication.instance() or QApplication(sys.argv)
    install_language(app)
    control = Controller()
    gui = GUI(control)
    gui.show()
    app.processEvents()
    return app, control, gui


def spin(app, seconds: float) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def blob(rng, x: float, y: float, count: int = 80, spread: float = 0.6) -> np.ndarray:
    return np.column_stack(
        [
            x + rng.uniform(-spread, spread, count),
            y + rng.uniform(-spread, spread, count),
            rng.uniform(-1.5, 1.5, count),
        ]
    )


def label_document(index: int, objects: list) -> dict:
    return {
        "folder": "pointclouds",
        "filename": f"frame_{index:03d}.pcd",
        "path": f"pointclouds/frame_{index:03d}.pcd",
        "objects": objects,
    }


def box_object(name: str, x: float, y: float, z: float, yaw: float = 0.0) -> dict:
    return {
        "name": name,
        "centroid": {"x": x, "y": y, "z": z},
        "dimensions": {"length": 2.6, "width": 4.0, "height": 3.0},
        "rotations": {"x": 0.0, "y": 0.0, "z": yaw},
    }


# --------------------------------------------------------------------------- #
#                                    flows                                     #
# --------------------------------------------------------------------------- #


def flow_interpolation() -> bool:
    """Ctrl+Shift+I / Ctrl+Shift+K fill the frames between two keyframes."""
    root = Path(tempfile.mkdtemp(prefix="lc-smoke-interp-"))
    try:
        make_project(root)
        rng = np.random.default_rng(5)
        for index in range(7):
            write_pcd(
                root / "pointclouds" / f"frame_{index:03d}.pcd",
                np.vstack([blob(rng, 0.0, index), blob(rng, 27.0, 0.0, 40, 2.0)]),
            )
        (root / "labels/frame_000.json").write_text(
            json.dumps(label_document(0, [box_object("pole", 0.0, 0.0, 0.0, 350.0)]))
        )
        (root / "labels/frame_006.json").write_text(
            json.dumps(label_document(6, [box_object("pole", 0.0, 6.0, 0.0, 10.0)]))
        )

        app, control, gui = boot()
        control.bbox_controller.set_active_bbox(0)
        control.cmd_set_interpolation_anchor()
        anchor_ok = control.interpolation_anchor is not None
        for _ in range(6):
            control.next_pcd(save=False)
            app.processEvents()
        control.bbox_controller.set_active_bbox(0)
        control.cmd_interpolate_to_here()

        deadline = time.time() + 60
        while time.time() < deadline:
            app.processEvents()
            worker = control.propagate_worker
            if worker is None or not worker.isRunning():
                break
            time.sleep(0.05)
        spin(app, 0.2)

        written = {}
        for index in range(1, 6):
            path = root / "labels" / f"frame_{index:03d}.json"
            if path.exists():
                objects = json.loads(path.read_text())["objects"]
                written[index] = [round(obj["centroid"]["y"], 2) for obj in objects]

        positions = [written.get(index) for index in range(1, 6)]
        ok = (
            anchor_ok
            and all(entry and len(entry) == 1 for entry in positions)
            and positions[0][0] < positions[1][0] < positions[2][0]
            < positions[3][0] < positions[4][0]
            and abs(positions[0][0] - 1.0) < 0.4
            and abs(positions[4][0] - 5.0) < 0.4
        )
        report("keyframe interpolation fills the frames between the two keyframes", ok,
               json.dumps(written))
        return ok
    finally:
        shutil.rmtree(root, ignore_errors=True)


def flow_quality() -> bool:
    """The quality window lists the mistakes, jumps to a frame and writes nothing."""
    root = Path(tempfile.mkdtemp(prefix="lc-smoke-quality-"))
    try:
        make_project(root)
        def pole_column(x: float, y: float) -> np.ndarray:
            return np.column_stack(
                [np.full(60, x), np.full(60, y), np.linspace(0.0, 10.0, 60)]
            )

        for index in range(3):
            write_pcd(
                root / "pointclouds" / f"frame_{index:03d}.pcd",
                np.vstack([pole_column(0.0, 0.0), pole_column(20.0, 0.0)]),
            )
        (root / "labels/frame_000.json").write_text(
            json.dumps(
                label_document(
                    0, [box_object("pole", 0.0, 0.0, 5.0), box_object("pole", 20.0, 0.0, 5.0)]
                )
            )
        )
        (root / "labels/frame_001.json").write_text(
            json.dumps(
                label_document(
                    1,
                    [
                        box_object("pole", 0.0, 0.0, 5.0),
                        box_object("pole", 0.05, 0.02, 5.0),  # duplicate
                        {
                            "name": "wire",
                            "centroid": {"x": 40.0, "y": 0.0, "z": 8.0},
                            "dimensions": {"length": 20.0, "width": 0.2, "height": 0.2},
                            "rotations": {"x": 0.0, "y": 0.0, "z": 0.0},
                        },  # long axis in length
                    ],
                )
            )
        )

        app, control, gui = boot()
        from PyQt5.QtCore import Qt

        from labelCloud.view.quality_dialog import QualityDialog

        before = {
            path.name: (path.read_text(), path.stat().st_mtime_ns)
            for path in (root / "labels").glob("*")
            if path.is_file()
        }
        dialog = QualityDialog(gui, control)
        dialog.show()
        spin(app, 0.2)

        kinds = sorted(issue.kind for issue in dialog.report.issues)
        rows = dialog.table.rowCount()
        dialog.table.selectRow(0)
        app.processEvents()
        expected_frame = dialog.table.item(0, 0).data(Qt.UserRole)
        dialog.go_to_selected()
        spin(app, 0.2)
        jump_ok = (
            control.pcd_manager.current_id == expected_frame
            and not dialog.isVisible()
        )
        after = {
            path.name: (path.read_text(), path.stat().st_mtime_ns)
            for path in (root / "labels").glob("*")
            if path.is_file()
        }
        detail = dialog.table.item(0, 4).text() if rows else ""

        ok = (
            kinds == ["axis_convention", "duplicate"]
            and rows == 2
            and jump_ok
            and before == after
            and bool(detail)
        )
        report(
            "quality check finds the doubtful boxes, jumps, and writes nothing",
            ok,
            f"kinds={kinds} rows={rows} jump={jump_ok} untouched={before == after}",
        )
        return ok
    finally:
        shutil.rmtree(root, ignore_errors=True)


def flow_proposals() -> bool:
    """Queued proposals show up in the session card, and write nothing by themselves."""
    root = Path(tempfile.mkdtemp(prefix="lc-smoke-proposals-"))
    try:
        make_project(root)
        write_pcd(root / "pointclouds/frame_000.pcd", blob(np.random.default_rng(2), 0.0, 0.0, 30))
        app, control, gui = boot()
        from labelCloud.model.bbox import BBox

        def box(x: float, y: float) -> BBox:
            candidate = BBox(x, y, 3.0, 2.6, 4.0, 6.0)
            candidate.set_classname("pole")
            return candidate

        control.bbox_controller.set_active_bbox(-1)
        added = control.bbox_controller.add_candidates([box(0.0, 0.0), box(5.0, 0.0)], 0.5)
        gui.update_session_panel()
        after_add = gui.session_predict_label.text()
        control.bbox_controller.set_active_bbox(0)
        control.cmd_accept_candidate()
        after_accept = gui.session_predict_label.text()
        control.cmd_reject_candidates()
        after_reject = gui.session_predict_label.text()

        ok = (
            added == 2
            and "2" in after_add
            and "1" in after_accept
            and "0" not in after_reject
            and "proposals waiting" in after_add
            and not (root / "labels/frame_000.json").exists()
        )
        report(
            "queued proposals are counted in the session card and stay off disk",
            ok,
            f"added={added} add={after_add!r} accept={after_accept!r} reject={after_reject!r}",
        )
        return ok
    finally:
        shutil.rmtree(root, ignore_errors=True)


def flow_chinese() -> bool:
    """A Chinese session: menus, object list, stepper, quality window, buttons."""
    root = Path(tempfile.mkdtemp(prefix="lc-smoke-zh-"))
    try:
        make_project(root, language="zh_CN")
        write_pcd(root / "pointclouds/frame_000.pcd", blob(np.random.default_rng(1), 0.0, 0.0, 20))

        app, control, gui = boot(language="zh_CN")
        from labelCloud.view.quality_dialog import QualityDialog

        assist_menu = [action.text() for action in gui.menuAssist.actions() if action.text()]
        stepper = [
            gui.combo_step_parameter.itemText(index)
            for index in range(gui.combo_step_parameter.count())
        ]
        actions = [action.text() for action in gui.label_list.actions() if action.text()]
        dialog = QualityDialog(gui, control)
        columns = [
            dialog.table.horizontalHeaderItem(index).text()
            for index in range(dialog.table.columnCount())
        ]
        buttons = [
            button.text() for button in dialog.findChildren(type(dialog.rescan_button))
        ]

        def translated(texts) -> bool:
            return all(any("\u4e00" <= char <= "\u9fff" for char in text) for text in texts)

        ok = (
            translated(assist_menu)
            and translated(stepper)
            and translated(actions)
            and translated(columns)
            and translated(buttons)
            and "质检" in dialog.windowTitle()
        )
        report(
            "a Chinese session is translated everywhere (menus, stepper, dialogs)",
            ok,
            f"stepper={stepper} buttons={buttons}",
        )
        return ok
    finally:
        shutil.rmtree(root, ignore_errors=True)


RESULTS: list = []


def report(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not ok else ""))


def main() -> int:
    flows = {
        "interp": flow_interpolation,
        "quality": flow_quality,
        "proposals": flow_proposals,
        "zh": flow_chinese,
    }
    wanted = sys.argv[1:] or list(flows)
    unknown = [name for name in wanted if name not in flows]
    if unknown:
        print(f"unknown flow(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    if len(wanted) > 1 and not os.environ.get("LC_SMOKE_CHILD"):
        # ``config.ini`` is bound to the working directory when the config manager is
        # imported, so one flow per process — otherwise flow 2 reads flow 1's folder.
        failures = []
        for name in wanted:
            environment = dict(os.environ, LC_SMOKE_CHILD="1")
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), name], env=environment
            )
            if result.returncode != 0:
                failures.append(name)
        print(f"\n{len(wanted) - len(failures)}/{len(wanted)} smoke flows passed")
        return 1 if failures else 0

    for name in wanted:
        flows[name]()
    failed = [name for name, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} smoke flows passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
