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
from dataclasses import dataclass
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

# --- refit tuning (see RefitParams and the "Refit" settings dialog) ---------- #
#: How far outside the box to look for points that belong to the object.
DEFAULT_GROW_MARGIN = 0.6
#: A point further than this from the rest of the object is not part of it.
DEFAULT_MAX_LINK_DISTANCE = 1.2
#: An empty stretch longer than this is trimmed off the box: a box must not cover
#: a section that holds no points.
DEFAULT_MAX_EMPTY_GAP = 1.5
#: A trailing cluster smaller than this is treated as noise and cut off.
DEFAULT_MIN_CLUSTER_POINTS = 3
#: Growth/fit passes of the refit: a too-small box needs more than one to reach the
#: whole object, and it stops as soon as the result stops changing.
REFIT_MAX_PASSES = 4


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
    params: Optional[RefitParams] = None,
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

    # The structure top. A plain percentile would follow stray points (a wire
    # crossing above the pole, a bird, noise) and leave the box covering an empty
    # stretch, so the extent is taken from the longest *contiguous* run of points;
    # a gap larger than `max_empty_gap` ends the object.
    max_gap = params.max_empty_gap if params else DEFAULT_MAX_EMPTY_GAP
    z_values = points[:, 2]
    run = _largest_contiguous_run(
        z_values, max_gap, params.min_cluster_points if params else DEFAULT_MIN_CLUSTER_POINTS
    )
    if run is not None:
        start, end, order = run
        run_z = np.sort(z_values)[start:end] if len(order) == len(z_values) else None
        if run_z is None:
            ordered = z_values[order]
            run_z = ordered[start:end]
        top = float(run_z.max())
        run_bottom = float(run_z.min())
        # only keep the ground as the bottom when the object really starts there;
        # otherwise the box would cover the empty gap above the first point
        if run_bottom - bottom > max_gap:
            logging.info(
                "Pole points start %.2f m above the ground; trimming the empty part.",
                run_bottom - bottom,
            )
            bottom = run_bottom
    else:
        top = float(np.percentile(z_values, 98.0))
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


def _fit_wire(
    points: npt.NDArray[np.float32],
    classname: str,
    params: Optional[RefitParams] = None,
) -> BBox:
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

    # A cable is a *contiguous* chain: a gap larger than `max_empty_gap` means the
    # box would cover a section with no points, so the extent stops there. This is
    # what keeps a refit from stretching over the empty part of a sparse wire.
    max_gap = params.max_empty_gap if params else DEFAULT_MAX_EMPTY_GAP
    min_points = params.min_cluster_points if params else DEFAULT_MIN_CLUSTER_POINTS
    run = _largest_contiguous_run(along, max_gap, min_points)
    if run is not None:
        start, end, order = run
        ordered = along[order]
        along_start, along_end = float(ordered[start]), float(ordered[end - 1])
        if along_end - along_start >= 1.0:
            inside_run = (along >= along_start) & (along <= along_end)
            along, sideways = along[inside_run], sideways[inside_run]
            points = points[inside_run]

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


@dataclass
class RefitParams:
    """Tuning of the Ctrl+R refit.

    Two complaints shaped these defaults: the refit used to *miss* points that sat
    just outside the box (so the box stayed too small), and it used to *cover empty
    stretches* when a few stray points pulled the extent outwards. Hence both a
    margin to look beyond the box and a gap limit that trims empty runs.
    """

    grow_margin: float = DEFAULT_GROW_MARGIN
    max_link_distance: float = DEFAULT_MAX_LINK_DISTANCE
    max_empty_gap: float = DEFAULT_MAX_EMPTY_GAP
    min_cluster_points: int = DEFAULT_MIN_CLUSTER_POINTS
    #: False keeps the length/width the user set and only moves the box.
    refit_cross_section: bool = False
    #: False keeps the object's own size for wires instead of the class template.
    use_template_for_wire: bool = False


def _largest_contiguous_run(
    values: npt.NDArray[np.float32], max_gap: float, min_points: int
) -> Optional[tuple]:
    """Largest run of sorted ``values`` whose consecutive gaps stay ≤ ``max_gap``.

    Returns ``(start_index, end_index)`` into the *sorted* order, or ``None`` when
    no run is long enough. This is what stops a box from spanning a section that
    holds no points: the run ends where the object ends.
    """
    if values.size == 0:
        return None
    order = np.argsort(values)
    ordered = values[order]
    best_start = best_end = current_start = 0
    best_length = 1
    for index in range(1, len(ordered)):
        if ordered[index] - ordered[index - 1] > max_gap:
            if index - current_start > best_length:
                best_length = index - current_start
                best_start, best_end = current_start, index
            current_start = index
    if len(ordered) - current_start > best_length:
        best_start, best_end = current_start, len(ordered)
    if best_end - best_start < min_points:
        # fall back to the whole extent rather than returning something tiny
        best_start, best_end = 0, len(ordered)
    return int(best_start), int(best_end), order


def _grow_around_box(
    bbox: BBox,
    points: npt.NDArray[np.float32],
    params: RefitParams,
    ground: Optional[float] = None,
) -> npt.NDArray[np.float32]:
    """Points of the object, including the parts outside the box.

    Looking only *inside* an inflated box is not enough: when the box is too short,
    the rest of the pole is outside even the inflated version, which is why a refit
    used to leave points out. So the growth starts from the box and walks along the
    object with ``max_link_distance``, inside a neighbourhood around the box and
    (for upright objects) above the ground — the ground plane is a connected sheet
    and would otherwise swallow the search.
    """
    centre = np.asarray(bbox.get_center())
    length, width, height = bbox.get_dimensions()
    radius = max(
        0.75 * float(np.linalg.norm((length, width, height))) + params.grow_margin,
        3.0,
    )
    near_centre = np.linalg.norm(points[:, :3] - centre, axis=1) <= radius
    if ground is not None:
        near_centre &= points[:, 2] > ground + GROUND_MARGIN
    neighbourhood = points[near_centre]
    if len(neighbourhood) < 5:
        return points[bbox.is_inside(points)]

    distances = np.linalg.norm(neighbourhood[:, :3] - centre, axis=1)
    seed = int(np.argmin(distances))
    grid = _GridIndex(neighbourhood, cell=max(params.max_link_distance, 1e-3))
    component = grow_region(
        neighbourhood,
        seed,
        link_radius=params.max_link_distance,
        grid=grid,
    )
    if component.sum() < 5:
        return points[bbox.is_inside(points)]
    return neighbourhood[component]


def refit_box(
    bbox: BBox,
    points: npt.NDArray[np.float32],
    params: Optional[RefitParams] = None,
) -> Optional[BBox]:
    """Refit an existing box onto its object (F-21).

    A single "fit what is inside the box" cannot fix a box that is clearly too
    small: the rest of the pole is outside the box, so it never enters the fit.
    This therefore iterates — grow onto the object, fit, grow again with the larger
    box — until the result stops changing (at most `REFIT_MAX_PASSES` times), while
    trimming stretches without points (``max_empty_gap``) and keeping only what is
    connected to the object (``max_link_distance``).
    """
    params = params or refit_params()
    classname = bbox.get_classname()
    upright = LabelConfig().is_z_rotation_only(classname)
    ground = estimate_local_ground(points, bbox.get_center()) if upright else None

    current = bbox
    result: Optional[BBox] = None
    for _pass in range(REFIT_MAX_PASSES):
        selected = _grow_around_box(current, points, params, ground=ground)
        if len(selected) < 5:
            selected = points[current.is_inside(points)]
        if len(selected) < 5:
            logging.warning("Not enough points inside the box to refit it.")
            return None

        fitted = _fit_selection(selected, classname, current, params, ground)
        result = fitted
        if _converged(current, fitted):
            break
        current = fitted
    return result


def _fit_selection(
    selected: npt.NDArray[np.float32],
    classname: str,
    bbox: BBox,
    params: RefitParams,
    ground: Optional[float],
) -> BBox:
    """Fit ``selected`` and restore what a refit must not change."""
    if not LabelConfig().is_z_rotation_only(classname):
        fitted = _fit_wire(selected, classname, params=params)
        if not params.refit_cross_section:
            # keep the cross-section and thickness the user set
            fitted.set_dimensions(
                bbox.get_dimensions()[0],
                fitted.get_dimensions()[1],
                bbox.get_dimensions()[2],
            )
    else:
        fitted = _fit_pole(
            selected,
            classname,
            seed=np.asarray(bbox.get_center()),
            ground=ground,
            params=params,
        )
        if not params.refit_cross_section:
            existing_length, existing_width, _existing_height = bbox.get_dimensions()
            fitted.set_dimensions(existing_length, existing_width, fitted.height)
    fitted.locked = getattr(bbox, "locked", False)
    return fitted


def _converged(before: BBox, after: BBox, tolerance: float = 0.1) -> bool:
    """True when another growth pass would not move the box any more."""
    before_height = before.get_dimensions()[2]
    after_height = after.get_dimensions()[2]
    before_centre = np.asarray(before.get_center())
    after_centre = np.asarray(after.get_center())
    return bool(
        abs(before_height - after_height) <= tolerance
        and float(np.linalg.norm(before_centre - after_centre)) <= tolerance
        and abs(before.get_dimensions()[1] - after.get_dimensions()[1]) <= tolerance
    )


def refit_params() -> RefitParams:
    """Read the refit tuning from config.ini (defaults match RefitParams)."""
    from ..control.config_manager import config

    return RefitParams(
        grow_margin=config.getfloat("REFIT", "grow_margin", fallback=DEFAULT_GROW_MARGIN),
        max_link_distance=config.getfloat(
            "REFIT", "max_link_distance", fallback=DEFAULT_MAX_LINK_DISTANCE
        ),
        max_empty_gap=config.getfloat(
            "REFIT", "max_empty_gap", fallback=DEFAULT_MAX_EMPTY_GAP
        ),
        min_cluster_points=config.getint(
            "REFIT", "min_cluster_points", fallback=DEFAULT_MIN_CLUSTER_POINTS
        ),
        refit_cross_section=config.getboolean(
            "REFIT", "refit_cross_section", fallback=False
        ),
    )


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
