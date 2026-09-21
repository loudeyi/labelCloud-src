"""Carry one box forward through the following frames until the object ends.

This is the "label this pole once" action: instead of confirming a prediction in
every frame, the box is followed forward automatically —

1. its next pose is extrapolated from the last frames (position, heading) and its
   size taken from their median;
2. the points inside the predicted box decide whether the object is still there
   (the same rule the interactive prediction uses);
3. on request the box is re-fitted to those points;
4. the box is appended to that frame's label file, keeping whatever that frame
   already had.

The loop stops at the first frame where the object is gone, at the end of the data,
or at the frame cap. It answers "how far did this object stay in view", which is
also useful information in itself.

The logic is a plain function with injected readers/writers so it can be tested
without a point cloud, a GUI or a thread; :mod:`labelCloud.control.propagate_worker`
wraps it in a QThread.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np

from ..model.bbox import BBox
from .prediction import PointHistory, decide

#: How many frames one "carry forward" press writes. Deliberately short: if the
#: extrapolation is wrong, a long run would pile up dozens of misplaced boxes, and
#: five frames is a couple of seconds of manual work to check. The pass still stops
#: earlier when the object leaves the view.
DEFAULT_MAX_FRAMES = 5
#: A frame that already holds a box this close to the propagated one is left alone.
DUPLICATE_DISTANCE = 0.75


@dataclass
class PropagateOutcome:
    """What the forward pass did."""

    frames_written: int = 0
    frames_skipped: int = 0
    last_frame: Optional[Path] = None
    reason: str = ""
    written: List[Path] = field(default_factory=list)


def propagate_box(
    box: BBox,
    history: PointHistory,
    frames: List[Path],
    read_points: Callable[[Path], Optional[np.ndarray]],
    read_boxes: Callable[[Path], List[BBox]],
    write_boxes: Callable[[Path, List[BBox]], None],
    ratio: float = 0.5,
    min_points: int = 5,
    sensitivity: float = 1.5,
    adaptive: bool = True,
    use_motion: bool = True,
    refit: bool = True,
    max_frames: int = DEFAULT_MAX_FRAMES,
    progress: Optional[Callable[[int, int, int], None]] = None,
) -> PropagateOutcome:
    """Follow ``box`` through ``frames``, writing it where the object still exists.

    ``progress(index, total, written)`` is called before each frame so a caller can
    show something moving.
    """
    from . import assist

    outcome = PropagateOutcome()
    current = box
    total = min(len(frames), max_frames)

    for index, frame in enumerate(frames[:total]):
        if progress is not None:
            progress(index, total, outcome.frames_written)

        points = read_points(frame)
        if points is None or len(points) < 5:
            outcome.reason = f"could not read {frame.name}"
            break

        # --- where should the box be in this frame? ---------------------------
        predicted = _copy_box(current)
        if use_motion:
            velocity = history.velocity()
            if velocity is not None:
                centre = predicted.get_center()
                predicted.set_x_translation(centre[0] + velocity[0])
                predicted.set_y_translation(centre[1] + velocity[1])
                predicted.set_z_translation(centre[2] + velocity[2])
            yaw_velocity = history.yaw_velocity()
            if yaw_velocity:
                predicted.set_z_rotation(predicted.get_z_rotation() + yaw_velocity)
            stable = history.stable_dimensions()
            if stable and not getattr(predicted, "locked", False):
                predicted.set_dimensions(*stable)

        # --- is the object still there? ---------------------------------------
        try:
            count = int(predicted.is_inside(points).sum())
        except Exception:  # noqa: BLE001 - a broken frame must not kill the pass
            count = 0
        keep, mode = decide(count, history, ratio, min_points, sensitivity, adaptive)
        if not keep:
            outcome.reason = (
                f"object left the view at {frame.name} "
                f"({count} points, {mode} rule)"
            )
            outcome.last_frame = frame
            break

        # --- refine and write ------------------------------------------------
        final = predicted
        if refit:
            refitted = assist.refit_box(predicted, points)
            if refitted is not None:
                final = refitted
        history.observe(count, final)

        existing = read_boxes(frame)
        if already_there(existing, final):
            outcome.frames_skipped += 1
        else:
            write_boxes(frame, existing + [final])
            outcome.frames_written += 1
            outcome.written.append(frame)
        outcome.last_frame = frame
        current = final

    else:
        outcome.reason = (
            f"stopped after {total} frames (cap reached)"
            if total < len(frames)
            else "reached the end of the data"
        )
    return outcome


def _copy_box(box: BBox) -> BBox:
    clone = BBox(*box.get_center(), *box.get_dimensions())
    clone.set_rotations(*box.get_rotations())
    clone.set_classname(box.get_classname())
    clone.locked = getattr(box, "locked", False)
    clone.candidate = getattr(box, "candidate", False)
    return clone


def already_there(existing: List[BBox], candidate: BBox) -> bool:
    """True when the frame already has this object (same class, near the centre)."""
    centre = np.asarray(candidate.get_center())
    for other in existing:
        if other.get_classname() != candidate.get_classname():
            continue
        if float(np.linalg.norm(np.asarray(other.get_center()) - centre)) <= DUPLICATE_DISTANCE:
            return True
    return False
