"""Geometric assists: grow a region from a click, fit a pole/wire box, snap a box.

This is the in-app counterpart of the offline ``tools/pole_wire_autolabel``
pipeline. It deliberately shares nothing with it (no scipy, no file access) so it
can run inside the GUI thread in milliseconds on a single frame, and it follows the
conventions learned from this project's hand labels:

* **pole** — upright box, bottom sitting on the local ground, size template fixed
  (L≈2.6 m, W≈4.0 m), only the height follows the structure;
* **wire** — the long axis goes into ``dimensions.width`` (not ``length``) and the
  yaw is set so the box's local **+y** follows the wire. PCA gives that direction
  reliably; the roll around the wire axis is *not* determined by PCA (a thin tube
  has λ2≈λ3), so it is left at zero instead of letting the box spin randomly.

Everything here is numpy only and works on the point array of the loaded frame
(``pcd_manager.pointcloud.points``, absolute coordinates).
"""
from __future__ import annotations

import logging
import math
from typing import Optional, Tuple

import numpy as np
import numpy.typing as npt

from ..io.labels.config import LabelConfig
from ..model import BBox

#: Maximum distance between two points of the same region.
DEFAULT_LINK_RADIUS = 0.9
#: Vertical band around the seed that a wire may span (cables sag, but not 10 m).
WIRE_VERTICAL_BAND = 3.0
#: Never grow beyond this many points. A pole is a few thousand points; a cable
#: segment is thinner still, so a tight cap keeps a click responsive on dense
#: frames (74k points) instead of walking a leaked region for seconds.
MAX_REGION_POINTS = 20000
MAX_WIRE_REGION_POINTS = 6000
#: A cable is thin: if the region's points scatter wider than this around the
#: fitted line, the click landed on a hedge/wall/kerb and no box is produced.
MAX_WIRE_RESIDUAL = 0.9
#: A single cable spanning more than this is a leaked region, not a wire.
MAX_WIRE_LENGTH = 35.0
#: Growth cost guard: with the grid index a region of this size is still instant.
GRID_MAX_POINTS = 200000
#: Radius around the object used to estimate the local ground height.
GROUND_RADIUS = 4.0
#: Percentile of the local z values taken as the ground.
GROUND_PERCENTILE = 3.0
#: Points closer than this to the estimated ground are ignored while growing.
GROUND_MARGIN = 0.25
#: A pole is fitted inside a column of this horizontal radius around the click.
POLE_COLUMN_RADIUS = 2.0


def nearest_point_index(points: npt.NDArray[np.float32], target) -> Optional[int]:
    """Index of the point closest to ``target`` (brute force, one frame at a time)."""
    if points.size == 0:
        return None
    deltas = points[:, :3] - np.asarray(target, dtype=points.dtype)
    distances = np.einsum("ij,ij->i", deltas, deltas)
    return int(np.argmin(distances))


class _GridIndex:
    """Uniform grid over the points, for fast neighbour lookup.

    The first implementation compared every point against every visited point,
    which is fine for a pole (a few hundred points) but catastrophically slow when
    a region leaks into a hedge or the ground: the click inside would freeze the
    window for tens of seconds. A grid makes the cost proportional to the number of
    neighbours actually examined.

    Coordinates are kept as plain Python floats: the inner loop touches them
    millions of times, and numpy scalar indexing costs more than the arithmetic.
    """

    __slots__ = ("cell", "coordinates", "keys", "buckets")

    def __init__(self, points: npt.NDArray[np.float32], cell: float) -> None:
        self.cell = max(cell, 1e-3)
        self.coordinates = points[:, :3].tolist()
        self.keys = [
            (
                int(math.floor(x / self.cell)),
                int(math.floor(y / self.cell)),
                int(math.floor(z / self.cell)),
            )
            for x, y, z in self.coordinates
        ]
        buckets: dict = {}
        for index, key in enumerate(self.keys):
            bucket = buckets.get(key)
            if bucket is None:
                buckets[key] = [index]
            else:
                bucket.append(index)
        self.buckets = buckets

    def neighbours(self, index: int, radius: float):
        """Yield candidate indices within ``radius`` of the query point's cell."""
        reach = int(math.ceil(radius / self.cell))
        bx, by, bz = self.keys[index]
        buckets = self.buckets
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                for dz in range(-reach, reach + 1):
                    bucket = buckets.get((bx + dx, by + dy, bz + dz))
                    if bucket:
                        yield from bucket


def grow_region(
    points: npt.NDArray[np.float32],
    seed_index: int,
    link_radius: float = DEFAULT_LINK_RADIUS,
    vertical_band: Optional[float] = None,
    max_points: int = MAX_REGION_POINTS,
    grid: Optional[_GridIndex] = None,
) -> npt.NDArray[np.bool_]:
    """Grow a connected component around ``seed_index`` (breadth first).

    A plain radius search would leak into the tree or the ground next to a pole,
    so the caller can clamp the vertical band and the growth stops at
    ``max_points``. Neighbour lookup goes through a uniform grid (see
    :class:`_GridIndex`) so a leaked region stays fast.
    """
    count = len(points)
    visited = np.zeros(count, dtype=bool)
    if count == 0 or not (0 <= seed_index < count):
        return visited

    if grid is None:
        grid = _GridIndex(points, cell=link_radius)
    coordinates = grid.coordinates

    seed_z = coordinates[seed_index][2]
    visited[seed_index] = True
    queue = [seed_index]
    radius_sq = link_radius * link_radius
    grown = 1
    neighbours_of = grid.neighbours

    while queue and grown < max_points:
        current = queue.pop()
        x, y, z = coordinates[current]
        for candidate in neighbours_of(current, link_radius):
            if visited[candidate]:
                continue
            cx, cy, cz = coordinates[candidate]
            ddx = cx - x
            ddy = cy - y
            ddz = cz - z
            if ddx * ddx + ddy * ddy + ddz * ddz > radius_sq:
                continue
            visited[candidate] = True  # never reconsider it, band member or not
            if vertical_band is not None and abs(cz - seed_z) > vertical_band:
                continue
            queue.append(candidate)
            grown += 1
            if grown >= max_points:
                break
    return visited


def estimate_local_ground(
    points: npt.NDArray[np.float32],
    center: Tuple[float, float, float],
    radius: float = GROUND_RADIUS,
    percentile: float = GROUND_PERCENTILE,
) -> Optional[float]:
    """Low percentile of the z values around ``center``: the local ground."""
    if points.size == 0:
        return None
    deltas = points[:, :2] - np.asarray(center[:2], dtype=points.dtype)
    distances = np.einsum("ij,ij->i", deltas, deltas)
    nearby = points[distances <= radius * radius]
    if nearby.size == 0:
        return float(np.min(points[:, 2]))
    return float(np.percentile(nearby[:, 2], percentile))


def _template(classname: str) -> dict:
    template = LabelConfig().get_default_dimensions(classname) or {}
    return {key: template.get(key) for key in ("length", "width", "height")}


def fit_box(
    points: npt.NDArray[np.float32],
    seed_index: int,
    classname: str,
    link_radius: Optional[float] = None,
) -> Optional[BBox]:
    """Grow a region from ``seed_index`` and fit a box of ``classname`` around it."""
    if points.size == 0 or not (0 <= seed_index < len(points)):
        return None

    tilt_allowed = not LabelConfig().is_z_rotation_only(classname)
    if link_radius is None:
        link_radius = 1.2 if tilt_allowed else DEFAULT_LINK_RADIUS

    # The ground is a dense, fully connected plane: without removing it, growing
    # from the base of a pole swallows the whole street. Everything we label sits
    # above the ground, so mask it out first.
    ground = estimate_local_ground(points, tuple(points[seed_index, :3]))  # type: ignore[arg-type]
    mask = np.ones(len(points), dtype=bool)
    if ground is not None:
        mask = points[:, 2] > ground + GROUND_MARGIN
        mask[seed_index] = True

    indices = np.flatnonzero(mask)
    sub_points = points[indices]
    sub_seed = int(np.searchsorted(indices, seed_index))

    if tilt_allowed:
        # A click that lands on a hedge, a kerb or a fence grows into a huge
        # region and would produce an absurdly large box. Try the normal radius,
        # then a much tighter one, and refuse rather than hand back nonsense.
        for radius, band in (
            (link_radius, WIRE_VERTICAL_BAND),
            (min(link_radius, 0.5), 1.5),
        ):
            grid = _GridIndex(sub_points, cell=max(radius, 1e-3))
            region = grow_region(
                sub_points,
                sub_seed,
                link_radius=radius,
                vertical_band=band,
                max_points=MAX_WIRE_REGION_POINTS,
                grid=grid,
            )
            inside = sub_points[region]
            if len(inside) < 5:
                continue
            fitted = _fit_wire(inside, classname)
            if _wire_is_plausible(fitted, inside):
                return fitted
            logging.info(
                "Rejected an implausible wire fit (%.1f m long, %.1f m wide); "
                "retrying with a tighter region.",
                fitted.get_dimensions()[1],
                fitted.get_dimensions()[0],
            )
        logging.warning(
            "Could not find a cable-like structure at this point; no box was created."
        )
        return None

    grid = _GridIndex(sub_points, cell=max(link_radius, 1e-3))
    region = grow_region(sub_points, sub_seed, link_radius=link_radius, grid=grid)
    inside = sub_points[region]
    if len(inside) < 5:
        logging.warning("Not enough points around the click to fit a box.")
        return None
    # the ground was measured on the full cloud, before the mask removed it
    return _fit_pole(inside, classname, seed=points[seed_index], ground=ground)


def _wire_is_plausible(bbox: BBox, points: npt.NDArray[np.float32]) -> bool:
    """Reject the box shapes that come from a leaked region rather than a cable.

    A cable is a *thin chain*: long, but its points hug the fitted axis. A hedge,
    kerb or wall produces a long box whose points scatter across it, and a leaked
    ground patch produces a very long box as well.
    """
    _length, width, _height = bbox.get_dimensions()
    # for a wire the long axis is stored in `width` (see the class conventions)
    if width > MAX_WIRE_LENGTH:
        return False

    # Scatter of the region's points around the cable axis. The box's local x is
    # the direction *across* the cable, which is what must stay small; the local y
    # runs along it and is legitimately many metres long.
    yaw = math.radians(bbox.get_z_rotation())
    cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
    center = bbox.get_center()
    dx = points[:, 0] - center[0]
    dy = points[:, 1] - center[1]
    across = dx * cos_yaw + dy * sin_yaw
    return float(np.median(np.abs(across))) <= MAX_WIRE_RESIDUAL


def _fit_pole(
    points: npt.NDArray[np.float32],
    classname: str,
    seed=None,
    ground: Optional[float] = None,
) -> BBox:
    """Upright box: ground to structure top, cross-section from the template.

    The region is additionally clamped to a column around the clicked point, so a
    tree crown or a wall that happens to touch the pole cannot drag the centre
    sideways — a pole is a thin vertical structure by definition.
    """
    template = _template(classname)
    if seed is not None:
        radius = max(
            POLE_COLUMN_RADIUS, float(template.get("width") or 0.0) / 2.0
        )
        deltas = points[:, :2] - np.asarray(seed[:2], dtype=points.dtype)
        column = np.einsum("ij,ij->i", deltas, deltas) <= radius * radius
        if column.sum() >= 5:
            points = points[column]

    center_xy = np.median(points[:, :2], axis=0)
    if ground is None:
        ground = estimate_local_ground(points, (center_xy[0], center_xy[1], 0.0))
    bottom = float(ground) if ground is not None else float(np.min(points[:, 2]))

    # the structure top: a high percentile ignores a few stray points above it
    top = float(np.percentile(points[:, 2], 98.0))
    height = max(top - bottom + 0.6, 1.0)

    length = float(template.get("length") or 2.6)
    width = float(template.get("width") or 4.0)

    bbox = BBox(
        float(center_xy[0]),
        float(center_xy[1]),
        bottom + height / 2.0,
        length,
        width,
        height,
    )
    bbox.set_rotations(0.0, 0.0, 0.0)
    bbox.set_classname(classname)
    logging.info(
        "Fitted pole box: centre (%.2f, %.2f, %.2f), height %.2f m, base z %.2f.",
        bbox.center[0],
        bbox.center[1],
        bbox.center[2],
        height,
        bottom,
    )
    return bbox


def _fit_wire(points: npt.NDArray[np.float32], classname: str) -> BBox:
    """Thin box along the cable: long axis in ``width``, local +y along the wire."""
    template = _template(classname)

    # Region growing can leak into the ground or a nearby hedge. A cable is a
    # thin band in z as well, so drop vertical outliers before measuring.
    z_median = float(np.median(points[:, 2]))
    z_tolerance = max(3.0 * float(points[:, 2].std()), 0.6)
    keep_z = np.abs(points[:, 2] - z_median) <= z_tolerance
    if keep_z.sum() >= 5:
        points = points[keep_z]

    xy = points[:, :2]
    centered = xy - xy.mean(axis=0)

    # principal direction in the ground plane (2x2 covariance, closed form)
    covariance = centered.T @ centered
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    main = eigenvectors[:, -1]
    if main[0] < 0:  # stable sign, so the yaw does not flip between clicks
        main = -main
    across = np.array([-main[1], main[0]])

    along = centered @ main
    sideways = centered @ across
    # drop outliers across the wire before measuring the cross-section
    keep = np.abs(sideways) <= max(3.0 * sideways.std(), 1.0)
    if keep.sum() >= 5:
        along, sideways = along[keep], sideways[keep]
        points = points[keep]

    span_along = float(along.max() - along.min())
    span_across = float(sideways.max() - sideways.min())
    center_xy = xy.mean(axis=0)

    length = float(template.get("length") or max(span_across, 1.5))
    width = float(template.get("width") or max(span_along, 3.0))
    if template.get("width"):
        width = max(width, min(span_along, template["width"] * 3.0))
    else:
        width = max(width, span_along)

    height = float(template.get("height") or 2.0)
    z_center = float((points[:, 2].max() + points[:, 2].min()) / 2.0)

    bbox = BBox(
        float(center_xy[0]), float(center_xy[1]), z_center, length, width, height
    )
    # local +y must follow the wire: yaw = direction - 90 degrees
    yaw = math.degrees(math.atan2(main[1], main[0])) - 90.0
    bbox.set_rotations(0.0, 0.0, yaw % 360.0)
    bbox.set_classname(classname)
    logging.info(
        "Fitted wire box: span %.2f m along the cable, yaw %.1f deg.", span_along, yaw
    )
    return bbox


def refit_box(bbox: BBox, points: npt.NDArray[np.float32]) -> Optional[BBox]:
    """Refit an existing box to the points currently inside it (F-21)."""
    classname = bbox.get_classname()
    inside = bbox.is_inside(points)
    selected = points[inside]
    if len(selected) < 5:
        logging.warning("Not enough points inside the box to refit it.")
        return None

    if LabelConfig().is_z_rotation_only(classname):
        fitted = _fit_pole(
            selected,
            classname,
            seed=np.asarray(bbox.get_center()),
            ground=estimate_local_ground(points, bbox.get_center()),
        )
        # A refit moves the box onto the points; the cross-section stays exactly as
        # the user set it (the template is for *new* boxes).
        existing_length, existing_width, _existing_height = bbox.get_dimensions()
        fitted.set_dimensions(existing_length, existing_width, fitted.height)
    else:
        fitted = _fit_wire(selected, classname)
    fitted.locked = getattr(bbox, "locked", False)
    return fitted


def snap_box(bbox: BBox, points: npt.NDArray[np.float32]) -> bool:
    """Snap the active box to the ground (F-22). Returns True if it moved."""
    bottom = bbox.center[2] - bbox.height / 2.0
    ground = estimate_local_ground(points, bbox.center)
    if ground is None:
        return False
    if abs(ground - bottom) < 1e-3:
        return False
    bbox.set_z_translation(ground + bbox.height / 2.0)
    logging.info("Snapped box bottom from %.2f to %.2f.", bottom, ground)
    return True
