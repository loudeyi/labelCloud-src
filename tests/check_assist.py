#!/usr/bin/env python3
"""Regression checks for the pole/wire assist work.

Dependency-free on purpose: the labelCloud venv has no pytest, and every check here
needs its own working directory (``ConfigManager`` binds ``config.ini`` to the
current directory at import time), so each check runs in a fresh subprocess.

Usage::

    /home/tyy/DSH-WS/labelcloud-hzh/bin/python tests/check_assist.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

PYTHON = sys.executable
REPO = Path(__file__).resolve().parent.parent

BASE_CONFIG = """\
[FILE]
pointcloud_folder = {cwd}/pointclouds
label_folder = {cwd}/labels
class_definitions = {classes}
image_folder = {cwd}/pointclouds
"""

READ_CONFIG_SNIPPET = """
import json
from labelCloud.io.labels.config import LabelConfig
from labelCloud.control.config_manager import config
lc = LabelConfig()
print(json.dumps({
    "classes": [c.name for c in lc.classes],
    "ids": [c.id for c in lc.classes],
    "default": lc.default,
    "type": lc.type.value,
    "format": lc.format,
    "propagate_labels": config.getboolean("LABEL", "propagate_labels"),
    "propagate_labels_raw": config.get("LABEL", "propagate_labels"),
}))
"""

RESULTS = []


def run_case(name, classes_json, config_body=None, snippet=READ_CONFIG_SNIPPET):
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        classes_path = cwd / "_classes.json"
        if classes_json is not None:
            classes_path.write_text(json.dumps(classes_json))
        config_text = (config_body or BASE_CONFIG).format(cwd=cwd, classes=classes_path)
        (cwd / "config.ini").write_text(config_text)
        proc = subprocess.run(
            [PYTHON, "-c", textwrap.dedent(snippet)],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        return proc


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {name}" + (f"  -- {detail}" if detail and not condition else ""))


# --------------------------------------------------------------------------- #
# F-02: class definition compatibility
# --------------------------------------------------------------------------- #
def test_bare_list_is_accepted():
    """A bare-list _classes.json (written by the pole/wire auto-labeler) must load."""
    proc = run_case("bare-list", ["pole", "wire"])
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        ok = data["classes"] == ["pole", "wire"] and data["format"] == "centroid_abs"
        detail = json.dumps(data)
    check("F-02 bare-list _classes.json loads as pole/wire + centroid_abs", ok, detail)


def test_dict_is_accepted():
    """labelCloud's own dict shape must keep working."""
    proc = run_case(
        "dict",
        {
            "classes": [
                {"name": "pole", "id": 1, "color": "#00ff7f"},
                {"name": "wire", "id": 2, "color": "#00aaff"},
            ],
            "default": 1,
            "type": "object_detection",
            "format": "centroid_abs",
        },
    )
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        ok = data["classes"] == ["pole", "wire"] and data["default"] == 1
        detail = json.dumps(data)
    check("F-02 dict _classes.json still loads unchanged", ok, detail)


def test_dict_without_id_or_color():
    """Hand-written class files with only names must not raise KeyError."""
    proc = run_case(
        "dict-minimal",
        {"classes": [{"name": "pole"}, {"name": "wire"}], "format": "centroid_abs"},
    )
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        ok = data["ids"] == [0, 1]
        detail = json.dumps(data)
    check("F-02 dict without id/color falls back instead of raising", ok, detail)


def test_missing_class_file_warns_but_starts():
    """Missing class file must not crash, and must not silently mean radians."""
    proc = run_case("missing", None)
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        ok = data["classes"] == ["cart"] and data["format"] == "centroid_abs"
        detail = json.dumps(data)
    check("F-02 missing class file falls back to centroid_abs (not radians)", ok, detail)


def test_unknown_class_is_added_from_label_file():
    """A class only present in the label folder must be merged into the config."""
    snippet = """
        import json
        from pathlib import Path
        from labelCloud.io.labels.config import LabelConfig
        labels = Path("labels"); labels.mkdir(exist_ok=True)
        (labels / "frame.json").write_text(json.dumps({"objects": [
            {"name": "pole", "centroid": {"x": 1, "y": 2, "z": 3},
             "dimensions": {"length": 1, "width": 1, "height": 1},
             "rotations": {"x": 0, "y": 0, "z": 0}},
            {"name": "insulator", "centroid": {"x": 1, "y": 2, "z": 3},
             "dimensions": {"length": 1, "width": 1, "height": 1},
             "rotations": {"x": 0, "y": 0, "z": 0}}]}))
        boxes = LabelConfig().classes
        from labelCloud.io.labels.centroid import CentroidFormat
        from labelCloud.control.config_manager import config
        fmt = CentroidFormat(Path("labels"), 8, relative_rotation=False)
        imported = fmt.import_labels(Path("frame.pcd"))
        after = [c.name for c in LabelConfig().classes]
        saved = json.loads(Path(config.get("FILE", "class_definitions")).read_text())
        print(json.dumps({"imported": len(imported), "after": after,
                          "saved": [c["name"] for c in saved["classes"]]}))
    """
    proc = run_case("unknown-class", ["pole"], snippet=snippet)
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        ok = data["imported"] == 2 and data["after"] == ["pole", "insulator"]
        ok = ok and data["saved"] == ["pole", "insulator"]
        detail = json.dumps(data, ensure_ascii=False)
    check("F-02 unknown class in label file is auto-added and persisted", ok, detail)


# --------------------------------------------------------------------------- #
# F-03: config defaults
# --------------------------------------------------------------------------- #
def test_new_options_fall_back_to_default():
    """An old config.ini missing new keys must not raise KeyError."""
    minimal = "[FILE]\nclass_definitions = {classes}\n"
    proc = run_case("minimal-config", ["pole"], config_body=minimal)
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        # present in default_config.ini, absent from the minimal user config
        ok = data["propagate_labels_raw"] == "False"
        detail = json.dumps(data)
    check("F-03 options missing from config.ini come from the default", ok, detail)


def test_user_value_overrides_default():
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        classes_path = cwd / "_classes.json"
        classes_path.write_text(json.dumps(["pole"]))
        (cwd / "config.ini").write_text(
            "[FILE]\nclass_definitions = {c}\n[LABEL]\npropagate_labels = True\n".format(
                c=classes_path
            )
        )
        proc = subprocess.run(
            [PYTHON, "-c", textwrap.dedent(READ_CONFIG_SNIPPET)],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        ok = proc.returncode == 0
        detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
        if ok:
            data = json.loads(proc.stdout.strip().splitlines()[-1])
            ok = data["propagate_labels"] is True
            detail = json.dumps(data)
        check("F-03 user config still overrides the default", ok, detail)


# --------------------------------------------------------------------------- #
# F-05: format detection and overwrite protection
# --------------------------------------------------------------------------- #
VERTICES_GUARD_SNIPPET = """
import json
from pathlib import Path
from labelCloud.control.label_manager import LabelManager

labels = Path("labels"); labels.mkdir(exist_ok=True)
pcd_dir = Path("pointclouds"); pcd_dir.mkdir(exist_ok=True)
frame = pcd_dir / "frame.pcd"; frame.write_text("")
label_file = labels / "frame.json"
label_file.write_text(json.dumps({
    "folder": "pointclouds", "filename": "frame.pcd", "path": str(frame),
    "objects": [{"name": "pole", "vertices": [
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 2], [1, 0, 2], [1, 1, 2], [0, 1, 2]]}]}))
before = label_file.read_text()

manager = LabelManager(strategy="centroid_abs", path_to_label_folder=labels)
boxes = manager.import_labels(frame)
manager.export_labels(frame, [])            # simulates the auto-save on frame change
after = label_file.read_text()
backup_dir = labels / ".bak"
print(json.dumps({
    "imported": len(boxes),
    "unchanged": before == after,
    "backups": len(list(backup_dir.glob("*"))) if backup_dir.is_dir() else 0,
}))
"""

BACKUP_SNIPPET = """
import json
from pathlib import Path
from labelCloud.control.label_manager import LabelManager

labels = Path("labels"); labels.mkdir(exist_ok=True)
pcd_dir = Path("pointclouds"); pcd_dir.mkdir(exist_ok=True)
frame = pcd_dir / "frame.pcd"; frame.write_text("")
label_file = labels / "frame.json"
label_file.write_text(json.dumps({
    "folder": "pointclouds", "filename": "frame.pcd", "path": str(frame),
    "objects": [{"name": "wire",
                 "centroid": {"x": 1, "y": 2, "z": 3},
                 "dimensions": {"length": 2, "width": 17, "height": 2},
                 "rotations": {"x": 0, "y": 0, "z": 179.0}}]}))
before = label_file.read_text()

manager = LabelManager(strategy="centroid_abs", path_to_label_folder=labels)
boxes = manager.import_labels(frame)
manager.export_labels(frame, [])            # user deleted the box and switched frame
backup = labels / ".bak" / "frame.json"
print(json.dumps({
    "imported": len(boxes),
    "rewritten": label_file.read_text() != before,
    "backup_kept_original": backup.is_file() and backup.read_text() == before,
}))
"""

UNIT_SNIPPET = """
import json
from labelCloud.io.labels.detection import detect_rotation_unit, detect_encoding, describe_label_file

def unit(rz):
    return detect_rotation_unit({"objects": [
        {"name": "pole", "centroid": {"x": 0, "y": 0, "z": 0},
         "dimensions": {"length": 1, "width": 1, "height": 1},
         "rotations": {"x": 0, "y": 0, "z": rz}}]})

vertices = {"objects": [{"name": "pole", "vertices": [[0, 0, 0]]}]}
print(json.dumps({
    "big": unit(353.0),
    "small": unit(2.8),
    "negative": unit(-181.0),
    "encoding_vertices": detect_encoding(vertices),
}))
"""


def run_snippet(name, snippet, classes_json=("pole", "wire")):
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        classes_path = cwd / "_classes.json"
        classes_path.write_text(json.dumps(list(classes_json)))
        (cwd / "config.ini").write_text(
            BASE_CONFIG.format(cwd=cwd, classes=classes_path)
        )
        return subprocess.run(
            [PYTHON, "-c", textwrap.dedent(snippet)],
            cwd=cwd,
            capture_output=True,
            text=True,
        )


def test_vertices_file_is_never_overwritten():
    """Reading a vertices frame with the centroid strategy must not blank it."""
    proc = run_snippet("vertices-guard", VERTICES_GUARD_SNIPPET)
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        ok = (
            data["imported"] == 0
            and data["unchanged"] is True
            and data["backups"] == 0
        )
        detail = json.dumps(data)
    check("F-05 vertices file is not overwritten by a centroid session", ok, detail)


def test_centroid_file_is_backed_up_before_rewrite():
    proc = run_snippet("backup", BACKUP_SNIPPET)
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        ok = (
            data["imported"] == 1
            and data["rewritten"] is True
            and data["backup_kept_original"] is True
        )
        detail = json.dumps(data)
    check("F-05 first rewrite of a label file keeps a .bak copy", ok, detail)


def test_rotation_unit_detection():
    proc = run_snippet("unit", UNIT_SNIPPET)
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        # 353 deg can only be degrees; 2.8 is genuinely ambiguous (verify, not guess)
        ok = (
            data["big"] == "degrees"
            and data["negative"] == "degrees"
            and data["small"] == "unknown"
            and data["encoding_vertices"] == "vertices"
        )
        detail = json.dumps(data)
    check("F-05 rotation-unit detection only claims what it can prove", ok, detail)


def run_snippet(name, snippet, classes_json=("pole", "wire"), extra_config="", env=None):
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        classes_path = cwd / "_classes.json"
        classes_path.write_text(json.dumps(list(classes_json)))
        (cwd / "config.ini").write_text(
            BASE_CONFIG.format(cwd=cwd, classes=classes_path) + extra_config
        )
        environment = {**os.environ, **(env or {})}
        return subprocess.run(
            [PYTHON, "-c", textwrap.dedent(snippet)],
            cwd=cwd,
            capture_output=True,
            text=True,
            env=environment,
        )


# --------------------------------------------------------------------------- #
# F-04: interface language switching
# --------------------------------------------------------------------------- #
def test_every_extracted_string_is_translated():
    """No extracted string may be left empty in the compiled translation."""
    ts_file = REPO / "labelCloud" / "i18n" / "labelCloud_zh_CN.ts"
    qm_file = REPO / "labelCloud" / "i18n" / "labelCloud_zh_CN.qm"
    import xml.etree.ElementTree as ET

    tree = ET.parse(ts_file)
    unfinished = []
    total = 0
    for context in tree.getroot().findall("context"):
        for message in context.findall("message"):
            total += 1
            translation = message.find("translation")
            if translation is None or not (translation.text or "").strip():
                unfinished.append(message.find("source").text)
    ok = total >= 150 and not unfinished and qm_file.is_file()
    check(
        f"F-04 all {total} extracted strings translated and .qm built",
        ok,
        f"unfinished={unfinished[:5]} qm={qm_file.is_file()}",
    )


LANGUAGE_SWITCH_SNIPPET = """
import json
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QCoreApplication

app = QApplication([])
from labelCloud.i18n import install_language, set_language, current_language

def t(ctx, text):
    return QCoreApplication.translate(ctx, text)

# the fixture config sets language = zh_CN
install_language(app)
zh = t("StatusManager", "Navigation Mode")
set_language("en", app)
en = t("StatusManager", "Navigation Mode")
set_language("zh_CN", app)
zh_again = t("StatusManager", "Navigation Mode")
print(json.dumps({"zh": zh, "en": en, "zh_again": zh_again,
                  "current": current_language()}))
"""

LANGUAGE_PERSIST_SNIPPET = """
import json
from pathlib import Path
from PyQt5.QtWidgets import QApplication

app = QApplication([])
from labelCloud.i18n import set_language, current_setting

set_language("en", app)
after_en = current_setting()
text = Path("config.ini").read_text()
set_language("zh_CN", app)
print(json.dumps({
    "after_en": after_en,
    "written_en": "language = en" in text,
    "after_zh": current_setting(),
}))
"""


def test_language_switches_at_runtime():
    """Switching the language must take effect without restarting."""
    proc = run_snippet(
        "language-switch",
        LANGUAGE_SWITCH_SNIPPET,
        extra_config="[USER_INTERFACE]\nlanguage = zh_CN\n",
        env={"QT_QPA_PLATFORM": "offscreen"},
    )
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        ok = (
            data["zh"] == "导航模式"
            and data["en"] == "Navigation Mode"
            and data["zh_again"] == "导航模式"
            and data["current"] == "zh_CN"
        )
        detail = json.dumps(data, ensure_ascii=False)
    check("F-04 language switches at runtime (zh -> en -> zh)", ok, detail)


def test_language_selection_is_persisted():
    proc = run_snippet(
        "language-persist",
        LANGUAGE_PERSIST_SNIPPET,
        extra_config="[USER_INTERFACE]\nlanguage = system\n",
        env={"QT_QPA_PLATFORM": "offscreen"},
    )
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        ok = (
            data["after_en"] == "en"
            and data["written_en"] is True
            and data["after_zh"] == "zh_CN"
        )
        detail = json.dumps(data)
    check("F-04 language choice is written to config.ini", ok, detail)


# --------------------------------------------------------------------------- #
# F-07: per-class rotation freedom
# --------------------------------------------------------------------------- #
TILT_SNIPPET = """
import json
from pathlib import Path
from labelCloud.io.labels.config import LabelConfig
from labelCloud.control.config_manager import config
from labelCloud.control.bbox_controller import only_zrotation_decorator

class Stub:
    def __init__(self, classname):
        self.classname = classname
        self.calls = 0
    def has_active_bbox(self):
        return self.classname is not None
    def get_classname(self):
        return self.classname

@only_zrotation_decorator
def rotate(self):
    self.calls += 1

label_config = LabelConfig()
results = {}
for name in ("pole", "wire", "other", None):
    stub = Stub(name)
    rotate(stub)
    results[str(name)] = stub.calls

results["pole_perm"] = label_config.is_z_rotation_only("pole")
results["wire_perm"] = label_config.is_z_rotation_only("wire")
results["global_perm"] = label_config.is_z_rotation_only()
label_config.set_z_rotation_only("wire", True)
results["wire_after_toggle"] = label_config.is_z_rotation_only("wire")
saved = json.loads(config.getpath("FILE", "class_definitions").read_text())["classes"]
results["persisted"] = [c.get("z_rotation_only") for c in saved]
print(json.dumps(results))
"""


def test_per_class_tilt_permission():
    """Poles stay upright-only, wires may tilt, unknown classes follow the global."""
    classes = [
        {"name": "pole", "id": 1, "color": "#00ff7f", "z_rotation_only": True},
        {"name": "wire", "id": 2, "color": "#00aaff", "z_rotation_only": False},
        {"name": "other", "id": 3, "color": "#ff0000"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        classes_path = cwd / "_classes.json"
        classes_path.write_text(
            json.dumps(
                {
                    "classes": classes,
                    "default": 1,
                    "type": "object_detection",
                    "format": "centroid_abs",
                }
            )
        )
        (cwd / "config.ini").write_text(BASE_CONFIG.format(cwd=cwd, classes=classes_path))
        proc = subprocess.run(
            [PYTHON, "-c", textwrap.dedent(TILT_SNIPPET)],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        ok = (
            data["pole"] == 0  # blocked by the per-class flag
            and data["wire"] == 1  # allowed
            and data["other"] == 0  # falls back to the global (True)
            and data["None"] == 0
            and data["pole_perm"] is True
            and data["wire_perm"] is False
            and data["global_perm"] is True
            and data["wire_after_toggle"] is True
            and data["persisted"] == [True, True, None]
        )
        detail = json.dumps(data)
    check("F-07 tilt allowed for wire, blocked for pole, persisted", ok, detail)


# --------------------------------------------------------------------------- #
# Phase 1: keymap, undo, copy/paste, lock, template, local-axis movement
# --------------------------------------------------------------------------- #
KEYMAP_SNIPPET = """
import json
from PyQt5.QtCore import Qt
from labelCloud.control.keymap import KeyMap

km = KeyMap()

def resolve(mods, key):
    binding, factor = km.resolve(mods, key)
    return [binding.command if binding else None, factor]

result = {
    "ctrl_v": resolve(Qt.ControlModifier, Qt.Key_V),
    "ctrl_c": resolve(Qt.ControlModifier, Qt.Key_C),
    "ctrl_z": resolve(Qt.ControlModifier, Qt.Key_Z),
    "ctrl_shift_z": resolve(Qt.ControlModifier | Qt.ShiftModifier, Qt.Key_Z),
    "plain_v": resolve(Qt.NoModifier, Qt.Key_V),
    "shift_w": resolve(Qt.ShiftModifier, Qt.Key_W),
    "alt_i": resolve(Qt.AltModifier, Qt.Key_I),
    "plain_semicolon": resolve(Qt.NoModifier, Qt.Key_Semicolon),
    "f1": resolve(Qt.NoModifier, Qt.Key_F1),
    "conflicts": len(km.bindings) - len(km.by_sequence),
}
print(json.dumps(result))
"""

KEYMAP_OVERRIDE_SNIPPET = """
import json
from PyQt5.QtCore import Qt
from labelCloud.control.keymap import KeyMap

km = KeyMap()
binding, factor = km.resolve(Qt.ControlModifier | Qt.ShiftModifier, Qt.Key_C)
overridden = binding.command if binding else None
binding, factor = km.resolve(Qt.ControlModifier, Qt.Key_C)
still_default = binding.command if binding else None
print(json.dumps({"overridden": overridden, "default_still_free": still_default}))
"""

CONTROLLER_SNIPPET = """
import json
import math
from labelCloud.control.bbox_controller import BoundingBoxController
from labelCloud.model.bbox import BBox

class FakeStatus:
    def set_message(self, *a, **k): pass
    def update_status(self, *a, **k): pass
    def set_mode(self, *a, **k): pass

class FakeWidget:
    def __init__(self): self.value = 0
    def blockSignals(self, *a): pass
    def setValue(self, v): self.value = v

class FakeDropdown:
    def setCurrentText(self, *a): pass

class FakeList:
    def blockSignals(self, *a): pass
    def clear(self): pass
    def addItem(self, *a): pass
    def setCurrentRow(self, *a): pass
    def currentItem(self): return None

class FakePcdManager:
    def get_perspective(self): return (1.0, 0.0, 1.0)   # cosz, sinz, bu
    def populate_class_dropdown(self): pass

class FakeView:
    def __init__(self):
        self.status_manager = FakeStatus()
        self.current_class_dropdown = FakeDropdown()
        self.label_list = FakeList()
        self.dial_bbox_z_rotation = FakeWidget()
        self.controller = type("C", (), {"pcd_manager": FakePcdManager()})()
    def update_bbox_stats(self, bbox): pass

control = BoundingBoxController()
control.set_view(FakeView())
control.pcd_manager = FakePcdManager()

out = {}

# --- undo / redo, with coalescing of a key burst ---
box = BBox(0.0, 0.0, 0.0, 2.0, 3.0, 4.0)
box.set_classname("pole")
control.add_bbox(box)
control.translate_along_x(1.0)
control.translate_along_x(1.0)
out["center_after_two_moves"] = control.get_active_bbox().center[0]

control.undo()
out["center_after_undo"] = control.get_active_bbox().center[0]     # burst merged: back to 0
out["boxes_after_undo"] = len(control.bboxes)
control.undo()
out["boxes_after_second_undo"] = len(control.bboxes)               # add undone
control.redo()
out["boxes_after_redo"] = len(control.bboxes)
control.redo()
out["center_after_redo"] = control.get_active_bbox().center[0]
out["can_undo_at_end"] = control.history.can_undo

# --- locked dimensions refuse scaling, and leave no undo entry ---
control.bboxes[0].locked = True
before_dims = control.get_active_bbox().get_dimensions()
control.scale_along_length(1.0)
out["dims_unchanged_when_locked"] = control.get_active_bbox().get_dimensions() == before_dims
control.bboxes[0].locked = False
control.scale_along_length(1.0)
out["dims_changed_when_unlocked"] = control.get_active_bbox().get_dimensions()[0] == before_dims[0] + 1.0

# --- class template: fixes the cross-section, keeps height, straightens a pole ---
pole = control.get_active_bbox()
pole.set_rotations(5.0, -3.0, 30.0)
control.apply_template()
out["template_dims"] = [round(v, 3) for v in pole.get_dimensions()]
out["template_rotations"] = [round(v, 3) for v in pole.get_rotations()]

# --- copy / paste ---
control.copy_current_bbox()
out["paste_ok"] = control.paste_bbox()
out["boxes_after_paste"] = len(control.bboxes)
out["pasted_matches"] = (
    control.bboxes[1].get_dimensions() == control.bboxes[0].get_dimensions()
    and control.bboxes[1].get_classname() == "pole"
)

# --- clipboard survives a frame change, history does not ---
control.set_bboxes([])
out["history_cleared_on_frame_change"] = not control.history.can_undo
out["clipboard_survives"] = control.clipboard is not None
out["paste_into_next_frame"] = control.paste_bbox()
out["boxes_in_next_frame"] = len(control.bboxes)

# --- a drag gesture collapses into a single undo entry ---
control.begin_drag("Move bounding box")
for step in range(5):
    control.set_center(float(step), 0.0, 0.0)
control.end_drag()
out["center_after_drag"] = control.get_active_bbox().center[0]
control.undo()
out["center_after_drag_undo"] = control.get_active_bbox().center[0]
out["boxes_still_one"] = len(control.bboxes) == 1

# --- face dragging (and the wheel) respects the dimension lock ---
locked_box = control.get_active_bbox()
locked_box.locked = True
dims_before = locked_box.get_dimensions()
control.resize_side("right", 1.0)
out["resize_blocked_when_locked"] = control.get_active_bbox().get_dimensions() == dims_before
control.get_active_bbox().locked = False
control.resize_side("right", 1.0)
out["resize_works_when_unlocked"] = (
    round(control.get_active_bbox().get_dimensions()[0], 3) == round(dims_before[0] + 1.0, 3)
)

# --- the ± stepper obeys the tilt permission and edits single parameters ---
control.set_bboxes([])
stepped = BBox(0.0, 0.0, 0.0, 1.0, 1.0, 1.0)
stepped.set_classname("pole")
control.add_bbox(stepped)
control.nudge_rotation("rot_x", 5.0)               # pole: tilt not allowed
out["nudge_rx_blocked_for_pole"] = control.get_active_bbox().get_x_rotation()
control.nudge_position("pos_z", 2.0)
out["nudge_pos_z"] = control.get_active_bbox().center[2]
control.nudge_dimension("length", 0.5)
out["nudge_length"] = round(control.get_active_bbox().get_dimensions()[0], 3)
wire_box = BBox(0.0, 0.0, 0.0, 2.5, 12.0, 2.0)
wire_box.set_classname("wire")
control.add_bbox(wire_box)
control.nudge_rotation("rot_x", 5.0)               # wire: tilt allowed
out["nudge_rx_allowed_for_wire"] = control.get_active_bbox().get_x_rotation()
control.undo()
out["nudge_undo_removes_tilt"] = control.get_active_bbox().get_x_rotation()

# --- local-axis movement follows the box, not the camera ---
tilted = control.get_active_bbox()
tilted.set_z_rotation(90.0)
tilted.center = (0.0, 0.0, 0.0)
control.translate_local("y", distance=1.0)
out["local_y_at_90deg"] = [round(v, 3) for v in tilted.center]     # local +y -> world (-1, 0)

print(json.dumps(out))
"""


def test_keymap_bindings():
    """Ctrl combinations must not fall through to the plain-key commands."""
    proc = run_snippet("keymap", KEYMAP_SNIPPET)
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        ok = (
            data["ctrl_v"] == ["paste_box", 1.0]
            and data["ctrl_c"] == ["copy_box", 1.0]
            and data["ctrl_z"] == ["undo", 1.0]
            and data["ctrl_shift_z"] == ["redo", 1.0]
            and data["plain_v"] == ["rotate_y_cw", 1.0]
            and data["shift_w"] == ["translate_backward", 10.0]
            and data["alt_i"] == ["scale_length_up", 0.1]
            and data["plain_semicolon"] == ["translate_local_y_neg", 1.0]
            and data["f1"] == ["show_shortcuts", 1.0]
            and data["conflicts"] == 0
        )
        detail = json.dumps(data)
    check("F-15 keymap: Ctrl+V pastes, Shift x10, Alt x0.1, no conflicts", ok, detail)


def test_keymap_config_override():
    proc = run_snippet(
        "keymap-override",
        KEYMAP_OVERRIDE_SNIPPET,
        extra_config="[SHORTCUTS]\ncopy_box = Ctrl+Shift+C\n",
    )
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        ok = data["overridden"] == "copy_box" and data["default_still_free"] is None
        detail = json.dumps(data)
    check("F-15 shortcut can be rebound from config.ini", ok, detail)


def test_editing_commands():
    """Undo/redo coalescing, lock, template, copy/paste and local-axis movement."""
    classes = {
        "classes": [
            {
                "name": "pole",
                "id": 1,
                "color": "#00ff7f",
                "z_rotation_only": True,
                "default_dimensions": {"length": 2.6, "width": 4.0, "height": None},
            },
            {
                "name": "wire",
                "id": 2,
                "color": "#00aaff",
                "z_rotation_only": False,
                "default_dimensions": {"length": 2.5, "width": None, "height": 2.0},
            },
        ],
        "default": 1,
        "type": "object_detection",
        "format": "centroid_abs",
    }
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        classes_path = cwd / "_classes.json"
        classes_path.write_text(json.dumps(classes))
        (cwd / "config.ini").write_text(BASE_CONFIG.format(cwd=cwd, classes=classes_path))
        proc = subprocess.run(
            [PYTHON, "-c", textwrap.dedent(CONTROLLER_SNIPPET)],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        ok = (
            data["center_after_two_moves"] == 2.0
            and data["center_after_undo"] == 0.0  # the burst coalesced
            and data["boxes_after_undo"] == 1
            and data["boxes_after_second_undo"] == 0
            and data["boxes_after_redo"] == 1
            and data["center_after_redo"] == 2.0
            and data["can_undo_at_end"] is True
            and data["dims_unchanged_when_locked"] is True
            and data["dims_changed_when_unlocked"] is True
            and data["template_dims"] == [2.6, 4.0, 4.0]
            and data["template_rotations"] == [0.0, 0.0, 30.0]
            and data["paste_ok"] is True
            and data["boxes_after_paste"] == 2
            and data["pasted_matches"] is True
            and data["history_cleared_on_frame_change"] is True
            and data["clipboard_survives"] is True
            and data["paste_into_next_frame"] is True
            and data["boxes_in_next_frame"] == 1
            and data["local_y_at_90deg"] == [-1.0, 0.0, 0.0]
            and data["center_after_drag"] == 4.0
            # the whole gesture is one step: undo returns to the pre-drag centre
            and data["center_after_drag_undo"] == 2.0
            and data["boxes_still_one"] is True
            and data["resize_blocked_when_locked"] is True
            and data["resize_works_when_unlocked"] is True
            and data["nudge_rx_blocked_for_pole"] == 0.0
            and data["nudge_pos_z"] == 2.0
            and data["nudge_length"] == 1.5
            and data["nudge_rx_allowed_for_wire"] == 5.0
            and data["nudge_undo_removes_tilt"] == 0.0
        )
        detail = json.dumps(data)
    check("F-10/11/12/13 undo, lock, template, paste, local axes", ok, detail)


SAVE_FAILURE_SNIPPET = """
import json
from pathlib import Path
from labelCloud.control.controller import Controller
from labelCloud.model.bbox import BBox

class FakeStatus:
    def set_message(self, *a, **k): pass
    def update_status(self, *a, **k): pass
    def set_mode(self, *a, **k): pass

class FakeWidget:
    def blockSignals(self, *a): pass
    def setValue(self, v): pass

class FakeDropdown:
    def setCurrentText(self, *a): pass

class FakeList:
    def blockSignals(self, *a): pass
    def clear(self): pass
    def addItem(self, *a): pass
    def setCurrentRow(self, *a): pass
    def currentItem(self): return None

class FakeView:
    def __init__(self):
        self.status_manager = FakeStatus()
        self.current_class_dropdown = FakeDropdown()
        self.label_list = FakeList()
        self.dial_bbox_z_rotation = FakeWidget()
    def update_bbox_stats(self, bbox): pass

class WorkingPcdManager:
    pcd_path = Path("frame.pcd")
    pointcloud = None
    def __init__(self, fail):
        self.fail = fail
        self.saved = 0
    def save_labels_into_file(self, bboxes):
        if self.fail:
            raise OSError("read-only file system")
        self.saved += 1

control = Controller()
view = FakeView()
control.view = view
control.bbox_controller.set_view(view)

box = BBox(0.0, 0.0, 0.0, 1.0, 1.0, 1.0)
control.bbox_controller.add_bbox(box)
out = {"dirty_after_edit": control.bbox_controller.dirty}

control.pcd_manager = WorkingPcdManager(fail=True)
out["failed_save_returns"] = control.save(quiet=True)
out["dirty_after_failure"] = control.bbox_controller.dirty
out["error_count"] = control.save_error_count

control.pcd_manager = WorkingPcdManager(fail=False)
out["ok_save_returns"] = control.save(quiet=True)
out["dirty_after_success"] = control.bbox_controller.dirty
out["writes"] = control.pcd_manager.saved
out["autosave_without_changes"] = control.autosave()   # must not write again
out["writes_after_autosave"] = control.pcd_manager.saved
print(json.dumps(out))
"""


def test_save_safety():
    """A failing save must not raise, must keep the frame dirty and must report."""
    proc = run_snippet(
        "save-failure",
        SAVE_FAILURE_SNIPPET,
        env={"QT_QPA_PLATFORM": "offscreen"},
    )
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        ok = (
            data["dirty_after_edit"] is True
            and data["failed_save_returns"] is False
            and data["dirty_after_failure"] is True
            and data["error_count"] == 1
            and data["ok_save_returns"] is True
            and data["dirty_after_success"] is False
            and data["writes"] == 1
            and data["writes_after_autosave"] == 1
        )
        detail = json.dumps(data)
    check("F-18 failed save is reported, frame stays dirty, autosave is a no-op", ok, detail)


if __name__ == "__main__":
    print(f"python: {PYTHON}")
    print(f"repo:   {REPO}\n")
    test_bare_list_is_accepted()
    test_dict_is_accepted()
    test_dict_without_id_or_color()
    test_missing_class_file_warns_but_starts()
    test_unknown_class_is_added_from_label_file()
    test_new_options_fall_back_to_default()
    test_user_value_overrides_default()
    test_vertices_file_is_never_overwritten()
    test_centroid_file_is_backed_up_before_rewrite()
    test_rotation_unit_detection()
    test_every_extracted_string_is_translated()
    test_language_switches_at_runtime()
    test_language_selection_is_persisted()
    test_per_class_tilt_permission()
    test_keymap_bindings()
    test_keymap_config_override()
    test_editing_commands()
    test_save_safety()

    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("failed:")
        for name in failed:
            print(f"  - {name}")
        sys.exit(1)
