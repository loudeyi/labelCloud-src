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

    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("failed:")
        for name in failed:
            print(f"  - {name}")
        sys.exit(1)
