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
    def __init__(self): self.save_state = "unknown"
    def set_message(self, *a, **k): pass
    def update_status(self, *a, **k): pass
    def set_mode(self, *a, **k): pass
    def set_save_state(self, state, detail="", tooltip=""):
        self.save_state = state
        self.save_detail = detail
        self.save_tooltip = tooltip
    def current_save_state(self): return self.save_state

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

# --- F-23: proposal queue lifecycle ---
control.set_bboxes([])
existing = BBox(0.0, 0.0, 0.0, 2.0, 3.0, 4.0)
existing.set_classname("pole")
control.add_bbox(existing)
proposals = []
for x, y in ((9.0, 0.0), (10.0, 0.0), (9.05, 0.0)):   # third duplicates the first
    candidate = BBox(x, y, 0.0, 2.0, 3.0, 4.0)
    candidate.set_classname("pole")
    proposals.append(candidate)
out["candidates_added"] = control.add_candidates(proposals)      # 2, dedup by 0.6 m
out["candidate_count"] = control.candidate_count()
out["active_is_candidate"] = control.get_active_bbox().candidate
control.accept_candidate()
out["count_after_accept"] = control.candidate_count()
control.select_relative_candidate(1)
out["jumped_to_candidate"] = control.get_active_bbox().candidate
out["rejected"] = control.reject_all_candidates()
out["boxes_after_reject"] = len(control.bboxes)

# --- F-11b: group selection and group operations ---
control.set_bboxes([])
group = []
for index in range(3):
    member = BBox(float(index) * 10.0, 0.0, 0.0, 2.0, 3.0, 4.0)
    member.set_classname("pole")
    control.add_bbox(member)
    group.append(member)
control.set_active_bbox(0)
control.toggle_selection(1)
control.toggle_selection(2)
out["selection_size"] = control.selection_size()
out["group_ids"] = control.group_ids()
control.apply_to_group(lambda: control.translate_along_x(1.0))
out["group_centres"] = [round(b.center[0], 1) for b in control.bboxes]
control.toggle_selection(2)
out["after_deselect"] = control.selection_size()
control.toggle_selection(2)
out["group_deleted"] = control.delete_group()
out["boxes_after_group_delete"] = len(control.bboxes)
out["selection_cleared"] = control.selection_size()
control.clear_selection()
out["single_call_still_works"] = control.apply_to_group(lambda: control.translate_along_x(1.0))

# --- F-11b/F-16b: 180 degree flip ---
flip = BBox(0.0, 0.0, 0.0, 2.0, 3.0, 4.0)
flip.set_classname("wire")
flip.set_z_rotation(30.0)
control.add_bbox(flip)
control.update_rotation("rot_z", (control.get_active_bbox().get_z_rotation() + 180.0) % 360.0)
out["flip_180"] = round(control.get_active_bbox().get_z_rotation(), 1)
control.update_rotation("rot_z", (control.get_active_bbox().get_z_rotation() + 180.0) % 360.0)
out["flip_back"] = round(control.get_active_bbox().get_z_rotation(), 1)

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
            and data["candidates_added"] == 2  # the duplicate is skipped
            and data["candidate_count"] == 2
            and data["active_is_candidate"] is True
            and data["count_after_accept"] == 1
            and data["jumped_to_candidate"] is True
            and data["rejected"] == 1
            # the pre-existing box plus the one that was just confirmed
            and data["boxes_after_reject"] == 2
            and data["selection_size"] == 3
            and data["group_ids"] == [0, 1, 2]
            and data["group_centres"] == [1.0, 11.0, 21.0]   # all three moved
            and data["after_deselect"] == 2
            # the third box is re-selected before the delete, so the group is all three
            and data["group_deleted"] == 3
            and data["boxes_after_group_delete"] == 0
            and data["selection_cleared"] == 0
            and data["single_call_still_works"] == 1
            and data["flip_180"] == 210.0
            and data["flip_back"] == 30.0
        )
        detail = json.dumps(data)
    check("F-10/11/12/13 undo, lock, template, paste, local axes", ok, detail)


SAVE_FAILURE_SNIPPET = """
import json
from pathlib import Path
from labelCloud.control.controller import Controller
from labelCloud.model.bbox import BBox

class FakeStatus:
    def __init__(self): self.save_state = "unknown"
    def set_message(self, *a, **k): pass
    def update_status(self, *a, **k): pass
    def set_mode(self, *a, **k): pass
    def set_save_state(self, state, detail="", tooltip=""):
        self.save_state = state
        self.save_detail = detail
        self.save_tooltip = tooltip
    def current_save_state(self): return self.save_state

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

class FakeStrategy:
    FILE_ENDING = ".json"

class FakeLabelManager:
    def __init__(self, folder):
        self.label_folder = folder
        self.label_strategy = FakeStrategy()

class WorkingPcdManager:
    pointcloud = None
    def __init__(self, fail, folder):
        self.fail = fail
        self.saved = 0
        self.label_manager = FakeLabelManager(folder)
        self.pcd_path = folder / "frame.pcd"
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

labels_dir = Path("labels"); labels_dir.mkdir(exist_ok=True)
control.pcd_manager = WorkingPcdManager(fail=True, folder=labels_dir)
out["failed_save_returns"] = control.save(quiet=True)
out["dirty_after_failure"] = control.bbox_controller.dirty
out["error_count"] = control.save_error_count

control.pcd_manager = WorkingPcdManager(fail=False, folder=labels_dir)
label_path = control.label_file_path()
label_path.write_text("{}")          # the frame already has a file on disk
control.bbox_controller.dirty = False   # ... and nothing was edited since loading
out["writes_before_clean_save"] = control.pcd_manager.saved
# ... an untouched frame must not be rewritten on a frame change
out["clean_save_returns"] = control.save(quiet=True)
out["writes_after_clean_save"] = control.pcd_manager.saved
# ... but an explicit save (Ctrl+S) writes it, marking it as checked
control.save(quiet=True, force=True)
out["writes_after_forced_save"] = control.pcd_manager.saved
control.bbox_controller.dirty = True
out["ok_save_returns"] = control.save(quiet=True)
out["writes_after_dirty_save"] = control.pcd_manager.saved
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
            and data["clean_save_returns"] is True
            # unchanged frame: no write at all
            and data["writes_after_clean_save"] == data["writes_before_clean_save"]
            # explicit save: one write
            and data["writes_after_forced_save"] == data["writes_before_clean_save"] + 1
            # edited frame: another write
            and data["writes_after_dirty_save"] == data["writes_before_clean_save"] + 2
            and data["ok_save_returns"] is True
            and data["dirty_after_success"] is False
            and data["writes"] == data["writes_after_dirty_save"]
            # nothing is dirty any more, so the periodic autosave writes nothing
            and data["writes_after_autosave"] == data["writes_after_dirty_save"]
        )
        detail = json.dumps(data)
    check("F-18 failed save is reported, frame stays dirty, autosave is a no-op", ok, detail)


# --------------------------------------------------------------------------- #
# F-20/F-21/F-22: click-to-fit, refit, ground snapping
# --------------------------------------------------------------------------- #
FIT_SNIPPET = """
import json
import math
import numpy as np
from labelCloud.control import assist

rng = np.random.default_rng(7)

# --- a synthetic scene: ground plane at z = -2, a pole, and a slanted cable ---
ground = np.column_stack([
    rng.uniform(-12, 12, 6000),
    rng.uniform(-12, 12, 6000),
    np.full(6000, -2.0) + rng.normal(0, 0.03, 6000),
])
angle = rng.uniform(0, 2 * math.pi, 900)
height = rng.uniform(0, 1, 900)
pole = np.column_stack([
    3.0 + 0.12 * np.cos(angle),
    4.0 + 0.12 * np.sin(angle),
    -2.0 + 10.0 * height,
])

yaw_deg = 30.0
direction = np.array([math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))])
steps = rng.uniform(0, 20, 700)
wire = np.column_stack([
    -5.0 + steps * direction[0],
    2.0 + steps * direction[1],
    3.0 + steps * 0.02 + rng.normal(0, 0.02, 700),
])

points = np.vstack([ground, pole, wire]).astype(np.float32)
out = {}

# --- F-20: pole ---
seed = assist.nearest_point_index(points, (3.0, 4.0, 3.0))
pole_box = assist.fit_box(points, seed, "pole")
bottom = pole_box.center[2] - pole_box.height / 2.0
out["pole_class"] = pole_box.get_classname()
out["pole_centre"] = [round(pole_box.center[0], 2), round(pole_box.center[1], 2)]
out["pole_bottom"] = round(bottom, 2)
out["pole_height"] = round(pole_box.height, 2)
out["pole_dims_lw"] = [round(v, 2) for v in pole_box.get_dimensions()[:2]]
out["pole_upright"] = [round(v, 3) for v in pole_box.get_rotations()]

# --- F-20: wire (long axis must land in width, yaw so local +y follows it) ---
seed = assist.nearest_point_index(points, (0.0, 4.9, 3.2))
wire_box = assist.fit_box(points, seed, "wire")
out["wire_class"] = wire_box.get_classname()
out["wire_long_axis_is_width"] = wire_box.get_dimensions()[1] > wire_box.get_dimensions()[0]
out["wire_width"] = round(wire_box.get_dimensions()[1], 1)
out["wire_length"] = round(wire_box.get_dimensions()[0], 2)
out["wire_height"] = round(wire_box.get_dimensions()[2], 2)
out["wire_yaw"] = round(wire_box.get_z_rotation(), 1)
out["wire_yaw_error"] = round(
    min(
        abs((wire_box.get_z_rotation() - (yaw_deg - 90.0)) % 360),
        360 - abs((wire_box.get_z_rotation() - (yaw_deg - 90.0)) % 360),
    ),
    1,
)

# --- F-21: refit a box that was left slightly off ---
moved = assist.fit_box(points, seed, "wire")
moved.set_x_translation(moved.center[0] + 0.8)
moved.set_z_translation(moved.center[2] + 0.5)
refitted = assist.refit_box(moved, points)
out["refit_improved_x"] = abs(refitted.center[0] - wire_box.center[0]) < abs(
    moved.center[0] - wire_box.center[0]
)
out["refit_class_kept"] = refitted.get_classname() == "wire"

# --- F-21: a pole refit keeps the cross-section the user chose ---
pole_box.set_dimensions(1.1, 1.7, pole_box.height)
pole_box.set_x_translation(pole_box.center[0] + 0.6)
refit_pole = assist.refit_box(pole_box, points)
out["pole_refit_centre_error"] = round(abs(refit_pole.center[0] - 3.0), 2)
out["pole_refit_kept_cross_section"] = [round(v, 2) for v in refit_pole.get_dimensions()[:2]]

# --- F-22: snapping moves an elevated box onto the ground ---
elevated = assist.fit_box(points, assist.nearest_point_index(points, (3.0, 4.0, 3.0)), "pole")
elevated.set_z_translation(elevated.center[2] + 1.5)
moved_flag = assist.snap_box(elevated, points)
out["snap_moved"] = moved_flag
out["snap_bottom"] = round(elevated.center[2] - elevated.height / 2.0, 2)
out["snap_is_idempotent"] = assist.snap_box(elevated, points)

print(json.dumps(out))
"""


def test_fit_refit_snap():
    """The fitting engine must reproduce the pole/wire conventions on synthetic data."""
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
            [PYTHON, "-c", textwrap.dedent(FIT_SNIPPET)],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        ok = (
            data["pole_class"] == "pole"
            and abs(data["pole_centre"][0] - 3.0) <= 0.15
            and abs(data["pole_centre"][1] - 4.0) <= 0.15
            and -2.2 <= data["pole_bottom"] <= -1.8
            and 10.0 <= data["pole_height"] <= 11.5
            and data["pole_dims_lw"] == [2.6, 4.0]
            and data["pole_upright"] == [0.0, 0.0, 0.0]
            and data["wire_class"] == "wire"
            and data["wire_long_axis_is_width"] is True
            and data["wire_width"] >= 18.0
            and data["wire_yaw_error"] <= 8.0
            and data["refit_improved_x"] is True
            and data["refit_class_kept"] is True
            and data["pole_refit_centre_error"] <= 0.15
            and data["pole_refit_kept_cross_section"] == [1.1, 1.7]
            and data["snap_moved"] is True
            and -2.2 <= data["snap_bottom"] <= -1.8
            and data["snap_is_idempotent"] is False
        )
        detail = json.dumps(data)
    check("F-20/21/22 fit pole+wire, refit, snap conventions", ok, detail)


PROPOSALS_STATS_SNIPPET = """
import json
from pathlib import Path
from labelCloud.control.assist_worker import to_bboxes
from labelCloud.view.statistics_dialog import collect_statistics

proposals = [
    {"name": "pole", "center": (1.0, 2.0, 3.0), "dims": (2.6, 4.0, 11.0), "rot": (0.0, 0.0, 0.0)},
    {"name": "wire", "center": (5.0, 6.0, 7.0), "dims": (2.5, 17.0, 2.0), "rot": (0.0, 0.0, 300.0)},
    {"name": "broken"},                       # malformed -> skipped, not fatal
]
boxes = to_bboxes(proposals)
out = {
    "converted": len(boxes),
    "classes": [b.get_classname() for b in boxes],
    "all_candidates": all(b.candidate for b in boxes),
    "wire_yaw": round(boxes[1].get_z_rotation(), 1),
    "dims_kept": [round(v, 1) for v in boxes[1].get_dimensions()],
}

# --- statistics over a tiny synthetic dataset ---
pcd_dir = Path("pointclouds"); pcd_dir.mkdir(exist_ok=True)
label_dir = Path("labels"); label_dir.mkdir(exist_ok=True)
for stem, objects in (
    ("frame_a", [{"name": "pole"}, {"name": "pole"}]),
    ("frame_b", [{"name": "wire"}]),
    ("frame_c", []),                           # confirmed empty
    ("frame_d", [{"name": "pole"}]),
):
    (pcd_dir / (stem + ".pcd")).write_text("")
    (label_dir / (stem + ".json")).write_text(json.dumps({"objects": objects}))
(pcd_dir / "frame_e.pcd").write_text("")      # never labelled
(pcd_dir / "frame_f.pcd").write_text("")      # labelled, but the file is broken
(label_dir / "frame_f.json").write_text("{ not json")

stats = collect_statistics(pcd_dir, label_dir)
out["stats"] = {k: stats[k] for k in
                ("total", "labelled", "empty", "unlabelled", "unreadable", "boxes", "per_class")}
print(json.dumps(out))
"""


def test_proposals_and_statistics():
    """Proposal conversion must be tolerant, and the statistics must classify frames."""
    proc = run_snippet("proposals-stats", PROPOSALS_STATS_SNIPPET)
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        stats = data["stats"]
        ok = (
            data["converted"] == 2
            and data["classes"] == ["pole", "wire"]
            and data["all_candidates"] is True
            and data["wire_yaw"] == 300.0
            and data["dims_kept"] == [2.5, 17.0, 2.0]
            and stats["total"] == 6
            and stats["labelled"] == 3
            and stats["empty"] == 1
            and stats["unreadable"] == 1
            and stats["unlabelled"] == 1
            and stats["boxes"] == 4
            and stats["per_class"] == {"pole": 3, "wire": 1}
        )
        detail = json.dumps(data)
    check("F-24/25/26 proposal conversion and dataset statistics", ok, detail)


def test_readme_shortcuts_match_keymap():
    """The README shortcut tables must list exactly what the keymap defines.

    They are generated from the same table, so a stale README is a bug: this check
    fails whenever a binding is added or renamed without updating the docs.
    """
    import re

    from labelCloud.control.keymap import KeyMap

    expected = []
    for group, bindings in KeyMap().groups():
        expected.append(f"### {group}")
        for binding in bindings:
            expected.append(f"| `{binding.sequence}` | {binding.label} |")

    missing = []
    for name in ("README.md",):
        text = (REPO / name).read_text()
        block = text.split("<!-- BEGIN SHORTCUTS -->")[1].split("<!-- END SHORTCUTS -->")[0]
        rows = [line.strip() for line in block.splitlines() if line.strip()]
        for line in expected:
            if line.startswith("###"):
                continue
            if line not in rows:
                missing.append(f"{name}: {line}")

    check(
        f"README lists all {len(expected)} shortcut rows from the keymap",
        not missing,
        "; ".join(missing[:4]),
    )


def test_launcher_preserves_user_config():
    """The launcher must not overwrite settings the user changed by hand.

    It regenerates config.ini only when the file is missing or the dataset
    changed; otherwise every start would reset the language, shortcuts and
    autosave interval.
    """
    launcher = REPO / "run_labelcloud.sh"
    if not launcher.is_file():
        check("launcher preserves user config", False, "run_labelcloud.sh missing")
        return
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp) / "work"
        env = {**os.environ, "LABELCLOUD_WORKDIR": str(workdir), "DRY_RUN": "1"}
        dataset = str(REPO.parent / "datasets_y40" / "2026_04131(未标)")
        first = subprocess.run(
            ["bash", str(launcher), dataset, "labels_lc"],
            capture_output=True, text=True, env=env,
        )
        config = workdir / "config.ini"
        config_written = config.is_file()
        text = config.read_text() if config_written else ""
        text = text.replace("language = system", "language = zh_CN")
        text += "\n[SHORTCUTS]\ncopy_box = Ctrl+Shift+C\n"
        config.write_text(text)

        second = subprocess.run(
            ["bash", str(launcher)], capture_output=True, text=True, env=env
        )
        after = config.read_text() if config.is_file() else ""
        ok = (
            first.returncode == 0
            and config_written
            and second.returncode == 0
            and "language = zh_CN" in after
            and "copy_box = Ctrl+Shift+C" in after
            and "skip_startup_dialog = True" in after
            and "pointcloud_folder" in after
        )
        check(
            "launcher writes config once and then preserves manual edits",
            ok,
            f"rc={first.returncode}/{second.returncode} written={config_written} "
            f"stderr={second.stderr.strip()[:120]}",
        )


MOUSE_AND_CLASS_SNIPPET = """
import json
from pathlib import Path
from PyQt5.QtCore import QPoint, Qt
from labelCloud.control.controller import Controller
from labelCloud.model.bbox import BBox
from labelCloud.labeling_strategies import BaseLabelingStrategy
from labelCloud.labeling_strategies.picking import PickingStrategy

class FakeStatus:
    def __init__(self): self.save_state = "unknown"; self.messages = []
    def set_message(self, *a, **k): self.messages.append(a[0] if a else "")
    def update_status(self, *a, **k): pass
    def set_mode(self, *a, **k): pass
    def set_save_state(self, state, detail="", tooltip=""):
        self.save_state = state
        self.save_detail = detail
        self.save_tooltip = tooltip
    def current_save_state(self): return self.save_state
    def set_cursor_position(self, *a, **k): pass
    def retranslate(self): pass

class FakeGL:
    modelview = None
    projection = None
    def get_world_coords(self, x, y, correction=False): return (1.0, 2.0, 3.0)

class FakeDropdown:
    def __init__(self): self.text = ""
    def setCurrentText(self, text): self.text = text
    def currentData(self): return None

class FakeList:
    def blockSignals(self, *a): pass
    def clear(self): pass
    def addItem(self, *a): pass
    def setCurrentRow(self, *a): pass
    def currentItem(self): return None

class FakeDial:
    def blockSignals(self, *a): pass
    def setValue(self, v): pass

class FakeView:
    def __init__(self):
        self.status_manager = FakeStatus()
        self.gl_widget = FakeGL()
        self.current_class_dropdown = FakeDropdown()
        self.label_list = FakeList()
        self.dial_bbox_z_rotation = FakeDial()
        self.controller = None
    def update_bbox_stats(self, bbox): pass

class SpyStrategy(BaseLabelingStrategy):
    POINTS_NEEDED = 1
    def __init__(self, view):
        super().__init__(view)
        self.registered = 0
    def register_point(self, point):
        self.registered += 1
    def get_bbox(self):
        raise AssertionError("no box should be completed in this test")

class FakeEvent:
    def __init__(self, x, y, buttons=Qt.LeftButton, modifiers=Qt.NoModifier):
        self._pos = QPoint(x, y)
        self._buttons = buttons
        self._modifiers = modifiers
    def pos(self): return self._pos
    def x(self): return self._pos.x()
    def y(self): return self._pos.y()
    def buttons(self): return self._buttons
    def modifiers(self): return self._modifiers

control = Controller()
view = FakeView()
control.view = view
view.controller = control
control.drawing_mode.set_view(view)
control.bbox_controller.set_view(view)


class MinimalPcd:
    # the real manager needs a view that only Controller.startup() provides
    pointcloud = None

    def populate_class_dropdown(self):
        pass


control.pcd_manager = MinimalPcd()

# The GL widget normally sets this in __init__. There is no GL context in this
# test, so ray picking (which needs the modelview/projection matrices) is stubbed
# out; the gesture state machine is what is under test here.
from labelCloud.utils import oglhelper
oglhelper.DEVICE_PIXEL_RATIO = 1.0
oglhelper.get_intersected_bboxes = lambda *a, **k: None

out = {}

# --- a drag while a drawing mode is armed must not create a box ---------------
spy = SpyStrategy(view)
control.drawing_mode.drawing_strategy = spy
control.mouse_clicked(FakeEvent(100, 100))
control.mouse_released(FakeEvent(160, 130))       # dragged 60 px
out["drag_registered"] = spy.registered

# --- a real click does register ----------------------------------------------
control.mouse_clicked(FakeEvent(100, 100))
control.mouse_released(FakeEvent(102, 101))       # 3 px
out["click_registered"] = spy.registered

# --- Ctrl+drag must stay "rotate the box", not "resize a face" ----------------
control.drawing_mode.reset()             # no drawing mode armed for this check
control.bbox_controller.set_bboxes([])
face_box = BBox(0.0, 0.0, 0.0, 2.0, 3.0, 4.0)
face_box.set_classname("pole")
control.bbox_controller.add_bbox(face_box)
control.selected_side = "right"          # as if the cursor hovers that face
control.mouse_clicked(FakeEvent(100, 100, modifiers=Qt.ControlModifier))
out["ctrl_press_drag_target"] = control.drag_target      # None -> falls through to rotation
control.mouse_released(FakeEvent(100, 100))
control.mouse_clicked(FakeEvent(100, 100))               # no modifier
out["plain_press_drag_target"] = control.drag_target      # "face"
out["face_start_extent"] = control.drag_start_extent
control.mouse_released(FakeEvent(100, 100))
control.selected_side = None

# --- pointer mode leaves the drawing mode ------------------------------------
control.mouse_clicked(FakeEvent(100, 100))
control.mouse_released(FakeEvent(100, 100))
control.drawing_mode.reset()
out["mode_cleared"] = control.drawing_mode.is_active()

# --- next-frame class ---------------------------------------------------------
# the dropdown only follows the pin while no box is selected (as after a frame load)
control.bbox_controller.deselect_bbox()
out["class_before_pin"] = control.new_box_class()
control.set_next_box_class("wire")
out["class_after_pin"] = control.new_box_class()
out["dropdown_follows_pin"] = view.current_class_dropdown.text
control.set_next_box_class(None)
out["class_after_unpin"] = control.new_box_class()

# --- a new box from the picking strategy gets the pinned class ----------------
control.set_next_box_class("wire")
picking = PickingStrategy(view)
picking.point_1 = (0.0, 0.0, 0.0)
box = picking.get_bbox()
out["picked_class"] = box.get_classname()

# --- save indicator ----------------------------------------------------------
class StubStrategy:
    FILE_ENDING = ".json"

class StubLabels:
    def __init__(self, folder):
        self.label_folder = folder
        self.label_strategy = StubStrategy()

class StubPcd:
    pointcloud = None
    def __init__(self, folder):
        self.label_manager = StubLabels(folder)
        self.pcd_path = folder / "frame.pcd"

labels_dir = Path("labels"); labels_dir.mkdir(exist_ok=True)
control.pcd_manager = StubPcd(labels_dir)

control.record_save(control.label_file_path(), True)
out["state_after_save"] = view.status_manager.current_save_state()

control.label_file_path().write_text("{}")   # the frame is on disk
control.bbox_controller.dirty = True
control.refresh_save_state()
out["state_when_dirty"] = view.status_manager.current_save_state()

control.bbox_controller.dirty = False
control.refresh_save_state()
out["state_when_clean"] = view.status_manager.current_save_state()

control.label_file_path().unlink()           # no file on disk, nothing edited
control.refresh_save_state()
out["state_when_untouched"] = view.status_manager.current_save_state()

control.label_file_path().write_text("{}")
control.refresh_save_state()
out["state_when_file_exists"] = view.status_manager.current_save_state()

control.record_save(control.label_file_path(), False, "disk full")
out["state_after_failure"] = view.status_manager.current_save_state()
out["log_len"] = len(control.activity_log)
out["log_kinds"] = [entry[1] for entry in control.activity_log]
out["log_path"] = control.activity_log[-1][2]
print(json.dumps(out))
"""


def test_mouse_modes_and_save_indicator():
    """Click-vs-drag, pointer mode, the next-frame class and the save indicator."""
    proc = run_snippet(
        "mouse-modes",
        MOUSE_AND_CLASS_SNIPPET,
        classes_json=("pole", "wire"),
        env={"QT_QPA_PLATFORM": "offscreen"},
    )
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        ok = (
            data["drag_registered"] == 0        # dragging never builds a box
            and data["click_registered"] == 1   # a real click does
            and data["ctrl_press_drag_target"] is None   # Ctrl keeps upstream rotate
            and data["plain_press_drag_target"] == "face"
            and data["face_start_extent"] == 2.0
            and data["mode_cleared"] is False   # pointer mode leaves drawing
            and data["class_before_pin"] == "pole"
            and data["class_after_pin"] == "wire"
            and data["dropdown_follows_pin"] == "wire"
            and data["class_after_unpin"] == "pole"
            and data["picked_class"] == "wire"
            and data["state_after_save"] == "saved"
            and data["state_when_dirty"] == "dirty"
            and data["state_when_clean"] == "saved"
            and data["state_when_untouched"] == "unchanged"
            and data["state_when_file_exists"] == "saved"
            and data["state_after_failure"] == "failed"
            and data["log_len"] == 2
            and data["log_kinds"] == ["save", "save"]
            and data["log_path"].endswith("frame.json")
        )
        detail = json.dumps(data)
    check("pointer mode, click-vs-drag, next-frame class, save indicator", ok, detail)


PREDICTION_SNIPPET = """
import json
from pathlib import Path
import numpy as np
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

app = QApplication([])
from labelCloud.control.controller import Controller
from labelCloud.model.bbox import BBox

class FakeStatus:
    def __init__(self): self.messages = []; self.save_state = "unknown"; self.loaded = []
    def set_message(self, *a, **k): self.messages.append(a[0] if a else "")
    def update_status(self, *a, **k): pass
    def set_mode(self, *a, **k): pass
    def set_save_state(self, state, detail="", tooltip=""): self.save_state = state
    def current_save_state(self): return self.save_state
    def set_cursor_position(self, *a, **k): pass
    def set_loaded_file(self, path, index=0, total=0): self.loaded.append(str(path))
    def retranslate(self): pass

class FakePointCloud:
    def __init__(self, points): self.points = points

class FakeLabels:
    FILE_ENDING = ".json"
    def __init__(self, folder): self.label_folder = folder; self.label_strategy = self
class FakePcd:
    pointcloud = None
    def __init__(self, folder, points):
        self.label_manager = FakeLabels(folder)
        self.pcd_path = folder / "frame.pcd"
        self.pointcloud = FakePointCloud(points)
    def populate_class_dropdown(self):
        pass
    def save_labels_into_file(self, bboxes):
        doc = {"folder": "images", "filename": "frame.pcd", "path": str(self.pcd_path),
               "objects": [{"name": b.get_classname(),
                            "centroid": dict(zip("xyz", b.get_center())),
                            "dimensions": dict(zip(("length", "width", "height"),
                                                   b.get_dimensions())),
                            "rotations": dict(zip("xyz", b.get_rotations()))}
                           for b in bboxes]}
        self.label_manager.label_folder.joinpath("frame.json").write_text(json.dumps(doc))

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
        self.controller = None
    def update_bbox_stats(self, bbox): pass

def pole_points(cx, cy, count=200, height=10.0):
    rng = np.random.default_rng(3)
    angle = rng.uniform(0, 2 * np.pi, count)
    z = rng.uniform(0, height, count)
    return np.column_stack([cx + 0.12 * np.cos(angle), cy + 0.12 * np.sin(angle), z])

control = Controller()
view = FakeView(); control.view = view
view.controller = control
control.bbox_controller.set_view(view)

out = {}

# --- a pole that stays in view is predicted; one that leaves is dropped -------
alive = BBox(10.0, 2.0, 5.0, 2.6, 4.0, 10.0); alive.set_classname("pole")
gone = BBox(40.0, -8.0, 5.0, 2.6, 4.0, 10.0); gone.set_classname("pole")
labels = Path("labels"); labels.mkdir(exist_ok=True)

control.pcd_manager = FakePcd(labels, pole_points(10.0, 2.0))
control.bbox_controller.set_bboxes([alive, gone])
control.bbox_controller.dirty = True
from labelCloud.control.config_manager import config as _cfg
out["setting_before"] = _cfg.getboolean("LABEL", "predict_next_frame", fallback=False)
out["toggle_on"] = control.toggle_predict_next_frame(True)
out["written_to_file"] = "predict_next_frame = True" in Path("config.ini").read_text()
sources = control.capture_prediction_sources()
out["source_count"] = len(sources)
out["source_points"] = [c > 100 for _s, c, _h in sources]

# next frame: the first pole is still there, the second is gone
control.pcd_manager = FakePcd(labels, pole_points(10.0, 2.0))
control.bbox_controller.set_bboxes([])
predicted, dropped = control.predict_from(sources)
out["predicted"] = len(predicted)
out["dropped"] = dropped
out["predicted_class"] = predicted[0].get_classname() if predicted else None
out["predicted_candidate"] = bool(predicted[0].candidate) if predicted else None
out["size_kept"] = [round(v, 2) for v in predicted[0].get_dimensions()] if predicted else None

# the same prediction, but the object only left a couple of points behind
control.pcd_manager = FakePcd(labels, pole_points(10.0, 2.0, count=6))
control.bbox_controller.set_bboxes([])
few, few_dropped = control.predict_from(sources)
out["predicted_when_scarce"] = len(few)
out["dropped_when_scarce"] = few_dropped

# --- predictions count as new content and are written ------------------------
control.pcd_manager = FakePcd(labels, pole_points(10.0, 2.0))
control.bbox_controller.set_bboxes([])
added = control.predict_into_current_frame(sources, [])
out["added_to_frame"] = added
out["dirty_after_prediction"] = control.bbox_controller.dirty
# confirming one turns it into content that must be written
control.bbox_controller.set_active_bbox(0)
out["confirm_candidate"] = control.bbox_controller.accept_candidate()
out["dirty_after_confirm"] = control.bbox_controller.dirty
out["save_result"] = control.save(quiet=True)
out["label_file_written"] = (labels / "frame.json").is_file()
doc = json.loads((labels / "frame.json").read_text())
out["written_objects"] = [o["name"] for o in doc["objects"]]

# --- the drop rule: halving, and the adaptive variant ------------------------
from labelCloud.control.prediction import PointHistory, decide

steady = PointHistory()
steady.observe(100)
steady.observe(100)
out["half_dropped"] = decide(49, steady, 0.5, 5, 1.5, False)[0]   # halved -> gone
out["sixty_kept"] = decide(60, steady, 0.5, 5, 1.5, False)[0]

occluded = PointHistory()
for value in (100, 90, 80, 70):        # progressively hidden behind a tree
    occluded.observe(value)
out["adaptive_keeps_slow_decline"] = decide(60, occluded, 0.5, 5, 1.5, True)[0]
out["adaptive_drops_collapse"] = decide(5, occluded, 0.5, 5, 1.5, True)[0]

# --- switching it off stops the collection ----------------------------------
from labelCloud.control.config_manager import config
out["setting_after"] = config.getboolean("LABEL", "predict_next_frame", fallback=False)
out["sources_when_enabled"] = len(control.capture_prediction_sources())
out["toggle_off"] = control.toggle_predict_next_frame(False)
out["sources_when_disabled"] = len(control.capture_prediction_sources())
print(json.dumps(out))
"""


def test_next_frame_prediction():
    """Prediction carries boxes over, guards on point count, and gets saved."""
    proc = run_snippet(
        "prediction",
        PREDICTION_SNIPPET,
        env={"QT_QPA_PLATFORM": "offscreen"},
    )
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        ok = (
            data["source_count"] == 2
            and data["source_points"] == [True, False]   # the missing pole has no points
            and data["predicted"] == 1                   # only the one still in view
            and data["dropped"] == 1
            and data["predicted_class"] == "pole"
            and data["predicted_candidate"] is True
            # cross-section carried over exactly, height follows the points
            and data["size_kept"][:2] == [2.6, 4.0]
            and abs(data["size_kept"][2] - 10.0) <= 0.5
            and data["predicted_when_scarce"] == 0       # too few points left
            and data["dropped_when_scarce"] == 2
            and data["added_to_frame"] == 1
            # unconfirmed proposals are NOT written ...
            and data["dirty_after_prediction"] is False
            # ... but confirming one makes it content
            and data["confirm_candidate"] is True
            and data["dirty_after_confirm"] is True
            and data["save_result"] is True
            and data["label_file_written"] is True
            and data["written_objects"] == ["pole"]
            and data["setting_before"] is False
            and data["toggle_on"] is True
            and data["written_to_file"] is True
            and data["setting_after"] is True
            and data["sources_when_enabled"] == 1
            and data["toggle_off"] is False
            and data["sources_when_disabled"] == 0
            and data["half_dropped"] is False       # 100 -> 49 points: gone
            and data["sixty_kept"] is True          # 100 -> 60 points: still there
            and data["adaptive_keeps_slow_decline"] is True
            and data["adaptive_drops_collapse"] is False
        )
        detail = json.dumps(data)
    check("next-frame prediction: carry over, guard, persist", ok, detail)


REFIT_TUNING_SNIPPET = """
import json
import math
import numpy as np
from labelCloud.control import assist
from labelCloud.control.assist import RefitParams
from labelCloud.model.bbox import BBox

rng = np.random.default_rng(11)
out = {}

def pole_points(cx, cy, z0, z1, n=1200, radius=0.12):
    a = rng.uniform(0, 2 * np.pi, n)
    z = rng.uniform(z0, z1, n)
    return np.column_stack([cx + radius * np.cos(a), cy + radius * np.sin(a), z])

def ground():
    return np.column_stack([
        rng.uniform(-15, 20, 4000), rng.uniform(-10, 10, 4000), rng.normal(0, 0.03, 4000)
    ])

# --- the "missing points" case: a box that is far too short ---------------
points = np.vstack([ground(), pole_points(5.0, 2.0, 0.0, 10.0)]).astype(np.float32)
small = BBox(5.0, 2.0, 4.0, 2.6, 4.0, 3.0)       # covers only z = 2.5 .. 5.5
small.set_classname("pole")
out["small_height_before"] = round(small.get_dimensions()[2], 2)
refitted = assist.refit_box(small, points)
out["grown_height"] = round(refitted.get_dimensions()[2], 2)
out["grown_bottom"] = round(refitted.get_center()[2] - refitted.get_dimensions()[2] / 2, 2)

# --- the "empty stretch" case: stray points far above the pole ------------
with_stray = np.vstack([points, pole_points(5.0, 2.0, 18.0, 19.0, n=40)]).astype(np.float32)
box = BBox(5.0, 2.0, 5.0, 2.6, 4.0, 10.0)
box.set_classname("pole")
trimmed = assist.refit_box(box, with_stray)
out["trimmed_height"] = round(trimmed.get_dimensions()[2], 2)   # stays ~10, not ~19

# max_link_distance decides what still counts as "the same object": tightened to
# 5 mm the pole falls apart into tiny clusters, so the refit stays with the box
# interior instead of growing (this is the "unless the point is too far" knob).
tight = assist.refit_box(small, points, RefitParams(max_link_distance=0.005))
out["tight_link_height"] = round(tight.get_dimensions()[2], 2)

# --- a wire whose tail is a detached cluster: trim it ---------------------
yaw = math.radians(25)
direction = np.array([math.cos(yaw), math.sin(yaw)])
t_main = rng.uniform(0, 12, 800)
main = np.column_stack([t_main * direction[0], t_main * direction[1], 4.0 + 0.01 * t_main])
t_tail = rng.uniform(20, 24, 200)                 # 8 m gap, then more cable
tail = np.column_stack([t_tail * direction[0], t_tail * direction[1], 4.0 + 0.01 * t_tail])
wire_points = np.vstack([ground(), main, tail]).astype(np.float32)
wire_box = BBox(6.0 * direction[0], 6.0 * direction[1], 4.0, 2.5, 24.0, 2.0)
wire_box.set_classname("wire")
wire_box.set_z_rotation(math.degrees(yaw) - 90.0)
refit_wire = assist.refit_box(wire_box, wire_points)
out["wire_width_trimmed"] = round(refit_wire.get_dimensions()[1], 1)   # ~12, not ~24

print(json.dumps(out))
"""


def test_refit_tuning():
    """Refit must not miss the object, and must not cover empty stretches."""
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
            [PYTHON, "-c", textwrap.dedent(REFIT_TUNING_SNIPPET)],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        ok = (
            data["small_height_before"] == 3.0
            # a too-short box grows onto the whole pole ...
            and 9.5 <= data["grown_height"] <= 11.5
            and -0.6 <= data["grown_bottom"] <= 0.3
            # ... but stray points far above are trimmed, not covered
            and 9.5 <= data["trimmed_height"] <= 11.5
            # a tiny link distance keeps the refit near the box it started from
            # instead of growing onto the whole object
            and data["tight_link_height"] <= 6.0
            # a detached tail of a cable is cut off
            and 9.0 <= data["wire_width_trimmed"] <= 14.0
        )
        detail = json.dumps(data)
    check("Ctrl+R refit: grows onto the object, trims empty stretches", ok, detail)


PROPAGATE_SNIPPET = """
import json
import math
from pathlib import Path
import numpy as np
from labelCloud.control.prediction import PointHistory
from labelCloud.control.propagate import propagate_box
from labelCloud.model.bbox import BBox

rng = np.random.default_rng(23)
out = {}

def pole_points(cx, cy, z0=0.0, z1=10.0, n=400, radius=0.12):
    a = rng.uniform(0, 2 * np.pi, n)
    z = rng.uniform(z0, z1, n)
    return np.column_stack([cx + radius * np.cos(a), cy + radius * np.sin(a), z])

# the vehicle drives past a pole: it moves 0.5 m per frame in -y, and disappears
# after frame 4 (sensor range), while a second, static pole stays.
frames = [Path(f"f{i}.pcd") for i in range(6)]
clouds = {}
for i in range(6):
    x = 12.0 - 0.3 * i          # slight closing motion in x as well
    y = 3.0 - 0.5 * i           # moving sideways out of view
    if i < 5:
        clouds[frames[i]] = np.vstack([pole_points(x, y), pole_points(30.0, 0.0)])
    else:
        clouds[frames[i]] = pole_points(30.0, 0.0)     # the object is gone

boxes = {frame: [] for frame in frames}
box = BBox(12.0, 3.0, 5.0, 2.6, 4.0, 10.0)
box.set_classname("pole")
history = PointHistory()
history.observe(int(box.is_inside(clouds[frames[0]]).sum()), box)

outcome = propagate_box(
    box, history, frames[1:],
    read_points=lambda path: clouds[path],
    read_boxes=lambda path: boxes[path],
    write_boxes=lambda path, value: boxes.__setitem__(path, value),
)
out["written"] = outcome.frames_written
out["skipped"] = outcome.frames_skipped
out["reason_has_left"] = "left the view" in outcome.reason
out["written_centres"] = [
    [round(v, 2) for v in boxes[frame][0].get_center()] for frame in frames[1:5]
]
out["followed_the_motion"] = all(
    boxes[frames[i]][0].get_center()[1] < boxes[frames[i - 1]][0].get_center()[1]
    for i in range(2, 5)
)
out["size_from_history"] = [round(v, 2) for v in boxes[frames[1]][0].get_dimensions()]

# a frame that already holds the object is left alone instead of duplicated
boxes[frames[3]] = [BBox(11.1, 1.5, 5.0, 2.6, 4.0, 10.0)]
boxes[frames[3]][0].set_classname("pole")
history2 = PointHistory()
history2.observe(int(box.is_inside(clouds[frames[0]]).sum()), box)
outcome2 = propagate_box(
    box, history2, frames[1:],
    read_points=lambda path: clouds[path],
    read_boxes=lambda path: boxes[path],
    write_boxes=lambda path, value: boxes.__setitem__(path, value),
)
out["skipped_existing"] = outcome2.frames_skipped
out["no_duplicate_at_frame3"] = len(boxes[frames[3]]) == 1

print(json.dumps(out))
"""


def test_propagate_to_end():
    """Carrying a box forward follows the motion and stops when the object is gone."""
    classes = {
        "classes": [
            {
                "name": "pole",
                "id": 1,
                "color": "#00ff7f",
                "z_rotation_only": True,
                "default_dimensions": {"length": 2.6, "width": 4.0, "height": None},
            }
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
            [PYTHON, "-c", textwrap.dedent(PROPAGATE_SNIPPET)],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()[-1] if not ok else ""
    if ok:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        ok = (
            data["written"] == 4                 # frames 1..4, then the object is gone
            and data["reason_has_left"] is True
            and data["followed_the_motion"] is True
            and abs(data["written_centres"][1][1] - 2.0) <= 0.6   # tracked the -0.5 m/frame
            and data["size_from_history"][:2] == [2.6, 4.0]
            and data["skipped_existing"] == 4    # every frame already had the object
            and data["no_duplicate_at_frame3"] is True
        )
        detail = json.dumps(data)
    check("carry box forward: follows motion, stops when gone, no duplicates", ok, detail)


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
    test_fit_refit_snap()
    test_proposals_and_statistics()
    test_readme_shortcuts_match_keymap()
    test_launcher_preserves_user_config()
    test_mouse_modes_and_save_indicator()
    test_next_frame_prediction()
    test_refit_tuning()
    test_propagate_to_end()

    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("failed:")
        for name in failed:
            print(f"  - {name}")
        sys.exit(1)
