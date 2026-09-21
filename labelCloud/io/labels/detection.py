"""Detect the encoding of an existing label file.

labelCloud picks its reader from the single global ``format`` setting, but label
folders in this project are **not** homogeneous: some datasets were written as
``centroid`` boxes (absolute degrees) and others as 8-corner ``vertices`` files.
Reading a ``vertices`` file with the centroid reader raises ``KeyError``, which the
label manager swallows — the frame then looks empty, and because every frame change
auto-saves, the original annotation gets overwritten with ``{"objects": []}``.

This module makes that visible *before* anything is written:

* :func:`describe_label_file` reports which encoding a file uses,
* :func:`detect_rotation_unit` reports whether the angles can only be degrees,
* :class:`FormatGuard` remembers what was read and blocks a write that would
  change a file's encoding, keeping a ``.bak`` copy of everything it does rewrite.
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Dict, Optional, Set

CENTROID = "centroid"
VERTICES = "vertices"
KITTI = "kitti"
UNKNOWN = "unknown"

#: Angles above this can only be degrees (radians never leave (-pi, pi]).
DEGREES_MIN_ABS = 6.30  # 2*pi + margin


def detect_encoding(data: dict) -> str:
    """Return the encoding name used by a parsed label document."""
    if not isinstance(data, dict):
        return UNKNOWN
    objects = data.get("objects")
    if not isinstance(objects, list):
        return UNKNOWN
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        if "vertices" in obj:
            return VERTICES
        if "centroid" in obj:
            return CENTROID
    return UNKNOWN


def detect_rotation_unit(data: dict) -> str:
    """Return ``degrees``, ``radians`` or ``unknown`` for a centroid document.

    Only the unambiguous direction is reported: values outside (-pi, pi] can only
    be degrees. A file whose yaw values all happen to be small is *not* guessed —
    for example every wire in ``2026_04131(未标)`` has |rz| <= 2.82 in degrees,
    which looks exactly like a radians file if you only look at the range.
    """
    if detect_encoding(data) != CENTROID:
        return UNKNOWN
    angles = []
    for obj in data["objects"]:
        if not isinstance(obj, dict):
            # a hand-edited file can contain a ``null`` entry; it must not take the
            # frame-change slot down with an AttributeError
            continue
        rotations = obj.get("rotations")
        if isinstance(rotations, dict):
            angles.extend(
                abs(float(v)) for v in rotations.values() if isinstance(v, (int, float))
            )
    if not angles:
        return UNKNOWN
    if max(angles) > DEGREES_MIN_ABS:
        return "degrees"
    return "unknown"


def describe_label_file(path: Path) -> Dict[str, object]:
    """Inspect one label file. Missing/unreadable files report ``exists: False``.

    KITTI labels are ``.txt`` (one object per line, no JSON): they are recognised by
    their ending here, because everything else in this module works on parsed JSON.
    Without it a KITTI session sees every one of its own files as "unknown encoding"
    and refuses to load a single frame.
    """
    info: Dict[str, object] = {
        "path": path,
        "exists": path.is_file(),
        "encoding": UNKNOWN,
        "rotation_unit": UNKNOWN,
        "objects": 0,
        "readable": False,
    }
    if not info["exists"]:
        return info
    try:
        with path.open("r") as stream:
            text = stream.read()
    except OSError as error:
        logging.warning("Could not read label file %s: %s", path, error)
        return info
    info["readable"] = True
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if data is None:
        if path.suffix.lower() == ".txt":
            # KITTI labels are plain text, one object per line. The ending decides,
            # but only after JSON parsing failed, so a stray JSON document that was
            # renamed to ``.txt`` is still recognised as what it holds.
            info["encoding"] = KITTI
            info["objects"] = sum(1 for line in text.splitlines() if line.strip())
            return info
        logging.warning("Could not parse label file %s: not valid JSON", path)
        return info
    info["encoding"] = detect_encoding(data)
    info["rotation_unit"] = detect_rotation_unit(data)
    objects = data.get("objects") if isinstance(data, dict) else None
    info["objects"] = len(objects) if isinstance(objects, list) else 0
    return info


class FormatGuard:
    """Remember what was read and refuse writes that would change the encoding."""

    def __init__(self, label_folder: Path, file_ending: str = ".json") -> None:
        self.label_folder = label_folder
        self.file_ending = file_ending
        self.backup_folder = label_folder.joinpath(".bak")
        self.read_encodings: Dict[str, str] = {}
        #: frames that could only be read with a different encoding (see below)
        self.mismatches: Set[str] = set()
        #: frames whose *read* was refused, so the caller knows an empty frame is
        #: really "another format on disk" and not "no objects"
        self.refusals: Set[str] = set()
        self._backed_up: Set[str] = set()

    # -- read side ---------------------------------------------------------- #
    def note_read(self, label_path: Path, encoding: str) -> None:
        self.read_encodings[label_path.stem] = encoding

    def expected_encoding(self, pcd_stem: str, written_encoding: str) -> Optional[str]:
        """Return the encoding stored on disk if it differs from ``written_encoding``.

        Returns ``None`` when writing is fine (no file yet, same encoding, or the
        file could not be classified).
        """
        stored = self.read_encodings.get(pcd_stem)
        if stored is None:
            info = describe_label_file(
                self.label_folder.joinpath(pcd_stem + self.file_ending)
            )
            stored = str(info["encoding"])
            self.read_encodings[pcd_stem] = stored
        if stored in (UNKNOWN, written_encoding):
            return None
        return stored

    # -- write side --------------------------------------------------------- #
    def backup(self, label_path: Path) -> Optional[Path]:
        """Copy an existing label file into ``<label_folder>/.bak`` once per run."""
        if not label_path.is_file() or label_path.stem in self._backed_up:
            return None
        try:
            self.backup_folder.mkdir(parents=True, exist_ok=True)
            target = self.backup_folder.joinpath(label_path.name)
            shutil.copy2(label_path, target)
            self._backed_up.add(label_path.stem)
            return target
        except OSError as error:  # pragma: no cover - depends on the filesystem
            logging.warning("Could not back up %s: %s", label_path, error)
            return None
