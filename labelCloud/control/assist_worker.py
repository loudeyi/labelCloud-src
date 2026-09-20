"""Run the offline pole/wire pre-annotation for a single frame, off the UI thread.

The offline tool (``tools/pole_wire_autolabel``) does the heavy geometric work:
a multi-metre ground model, tree-canopy rejection for poles and a neighbourhood
PCA for wires. Measured cost on this dataset is 18 ms for a sparse frame up to
~1.1 s for a dense one, with wires dominating — far too slow to run inside the
20 ms repaint timer, so it runs in a :class:`QThread` and reports back through
signals.

Everything about the tool's location and parameters comes from the ``[ASSIST]``
section of ``config.ini`` so this fork stays usable without that tool present.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from .config_manager import config

ASSIST_SECTION = "ASSIST"


def polewire_path() -> str:
    return config.get(
        ASSIST_SECTION, "polewire_path", fallback="/home/tyy/DSH-WS/tools/pole_wire_autolabel"
    )


def assist_classes() -> str:
    return config.get(ASSIST_SECTION, "classes", fallback="pole,wire")


def assist_profile() -> str:
    """``recall`` (default) or ``strict``; selects the pole parameters."""
    return config.get(ASSIST_SECTION, "pole_profile", fallback="recall")


class PreAnnotateWorker(QThread):
    """Compute pre-annotation proposals for one point cloud file."""

    #: list of box dicts (``name``/``center``/``dims``/``rot``) + a status line
    proposals_ready = pyqtSignal(list, str)
    failed = pyqtSignal(str)

    def __init__(self, pcd_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.pcd_path = Path(pcd_path)
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:  # noqa: D102 - QThread entry point
        try:
            tool_path = polewire_path()
            if tool_path and tool_path not in sys.path:
                sys.path.insert(0, tool_path)

            from polewire.pipeline import Config, process_frame  # type: ignore
            from polewire.poles import PoleParams  # type: ignore
            from polewire.wires import WireParams  # type: ignore

            classes = tuple(
                name.strip() for name in assist_classes().split(",") if name.strip()
            )
            pole_params = PoleParams()
            if assist_profile() == "strict":
                # the tuned "fewer boxes, less noise" profile from REPORT.md
                for attribute, value in (
                    ("canopy", 0.2),
                    ("min_points", 16),
                    ("max_radius", 1.5),
                    ("min_height", 4.0),
                ):
                    if hasattr(pole_params, attribute):
                        setattr(pole_params, attribute, value)

            cfg = Config(classes=classes, pole=pole_params, wire=WireParams())
            boxes, _debug = process_frame(self.pcd_path, cfg)
            if self._cancelled:
                return
            self.proposals_ready.emit(list(boxes), f"{len(boxes)} proposals")
        except Exception as error:  # noqa: BLE001 - reported to the UI, never raised
            logging.error("Pre-annotation failed: %s", error, exc_info=True)
            self.failed.emit(str(error))


def to_bboxes(proposals: List[dict]) -> list:
    """Convert ``polewire`` box dicts into labelCloud :class:`BBox` objects."""
    from ..model import BBox

    boxes = []
    for proposal in proposals:
        try:
            center = proposal["center"]
            dims = proposal["dims"]
            rot = proposal.get("rot", (0.0, 0.0, 0.0))
            bbox = BBox(
                float(center[0]),
                float(center[1]),
                float(center[2]),
                float(dims[0]),
                float(dims[1]),
                float(dims[2]),
            )
            bbox.set_rotations(float(rot[0]), float(rot[1]), float(rot[2]))
            bbox.set_classname(str(proposal.get("name", "")))
            bbox.candidate = True
            boxes.append(bbox)
        except (KeyError, IndexError, TypeError, ValueError) as error:
            logging.warning("Skipping malformed proposal %s: %s", proposal, error)
    return boxes


def worker_for(pcd_path: Optional[Path], parent=None) -> Optional[PreAnnotateWorker]:
    if pcd_path is None:
        return None
    return PreAnnotateWorker(pcd_path, parent)
