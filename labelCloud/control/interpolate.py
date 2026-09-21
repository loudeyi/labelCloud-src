"""Fill the frames between two hand-labelled keyframes.

This is the workflow the project's tool survey recommended: label one object where it
is clearly visible, label it again some frames later, and let the frames in between be
computed. Position is interpolated with the fraction of the gap, the heading with the
shortest arc, and the size with the two keyframes' sizes — the object is rigid, so its
size should barely change.

Each generated box is checked against the points of its own frame: if the object is
not there (a gap in the data, an occlusion, a wrong keyframe) the box is not written
and the frame is counted as skipped, so a bad interpolation cannot quietly fill the
dataset with empty boxes. Existing objects in a frame are kept; a frame that already
holds this object is left alone.

Like :mod:`labelCloud.control.propagate` this is a plain function with injected
readers and writers, so it is testable without a GUI or a thread.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np

from ..model.bbox import BBox


@dataclass
class InterpolationOutcome:
    """What the pass between the two keyframes did."""

    frames_filled: int = 0
    frames_without_points: int = 0
    frames_already_labelled: int = 0
    reason: str = ""
    written: List[Path] = field(default_factory=list)


def lerp_box(anchor: BBox, target: BBox, fraction: float) -> BBox:
    """A box ``fraction`` of the way from ``anchor`` to ``target``.

    Position and size interpolate linearly; the heading uses the shortest arc, so a
    box does not spin 350° the wrong way when the two keyframes straddle north.
    """
    fraction = min(max(fraction, 0.0), 1.0)
    anchor_centre = np.asarray(anchor.get_center())
    target_centre = np.asarray(target.get_center())
    centre = anchor_centre + (target_centre - anchor_centre) * fraction

    anchor_dims = np.asarray(anchor.get_dimensions())
    target_dims = np.asarray(target.get_dimensions())
    dims = anchor_dims + (target_dims - anchor_dims) * fraction

    yaw_delta = (target.get_z_rotation() - anchor.get_z_rotation() + 180.0) % 360.0 - 180.0
    yaw = anchor.get_z_rotation() + yaw_delta * fraction

    box = BBox(float(centre[0]), float(centre[1]), float(centre[2]), *[float(v) for v in dims])
    box.set_rotations(
        anchor.get_x_rotation()
        + (target.get_x_rotation() - anchor.get_x_rotation()) * fraction,
        anchor.get_y_rotation()
        + (target.get_y_rotation() - anchor.get_y_rotation()) * fraction,
        yaw % 360.0,
    )
    box.set_classname(target.get_classname() or anchor.get_classname())
    box.locked = getattr(anchor, "locked", False)
    return box


def interpolate_between(
    anchor: BBox,
    target: BBox,
    frames: List[Path],
    read_points: Callable[[Path], Optional[np.ndarray]],
    read_boxes: Callable[[Path], List[BBox]],
    write_boxes: Callable[[Path, List[BBox]], None],
    refit: bool = True,
    min_points: int = 5,
    progress: Optional[Callable[[int, int, int], None]] = None,
) -> InterpolationOutcome:
    """Fill the frames between two keyframes (``frames`` excludes both keyframes)."""
    from . import assist
    from .propagate import already_there

    outcome = InterpolationOutcome()
    span = len(frames) + 1
    if span < 2:
        outcome.reason = "the two keyframes are adjacent (nothing to fill)"
        return outcome

    for index, frame in enumerate(frames):
        fraction = (index + 1) / span
        if progress is not None:
            progress(index, len(frames), outcome.frames_filled)

        box = lerp_box(anchor, target, fraction)
        points = read_points(frame)
        if points is None or len(points) < 5:
            outcome.frames_without_points += 1
            continue

        try:
            count = int(box.is_inside(points).sum())
        except Exception:  # noqa: BLE001 - a broken frame must not kill the pass
            count = 0
        if count < min_points:
            # nothing inside the interpolated box: do not write a guess
            outcome.frames_without_points += 1
            continue

        final = box
        if refit:
            refitted = assist.refit_box(box, points)
            if refitted is not None:
                final = refitted

        existing = read_boxes(frame)
        if already_there(existing, final):
            outcome.frames_already_labelled += 1
            continue
        write_boxes(frame, existing + [final])
        outcome.frames_filled += 1
        outcome.written.append(frame)

    outcome.reason = (
        f"filled {outcome.frames_filled} of {len(frames)} frames "
        f"({outcome.frames_without_points} without points, "
        f"{outcome.frames_already_labelled} already labelled)"
    )
    logging.info("Interpolation finished: %s", outcome.reason)
    return outcome
