"""Quality check: find the boxes that are probably wrong, before they ship.

A large part of a dataset is labelled in a few long sittings, and the mistakes that
survive are the boring ones: a box that was copied into the wrong place, a pole whose
height is ten times the usual one, a wire whose long axis ended up in ``length``
instead of ``width``, two boxes on the same object, a box around two stray points.
None of them is visible while labelling — they only show up when the dataset is used.

This module is the check that runs over a whole folder in one pass. It reads **only the
label files** (no point clouds), so scanning several hundred frames takes a moment, and
it compares each box against

* the class configuration — known class, upright classes, wire's long axis in ``width``;
* the **median size of its own class** in this dataset — the person labelling a pole 200
  times is the best available definition of how big a pole is here;
* the other boxes of the same frame — duplicates and near-total overlaps;
* the points of the current frame, when they are already loaded — a box that covers
  fewer than a handful of points is a leftover.

Everything is a plain function over injected readers, so the rules can be tested without
a GUI, a thread or a dataset on disk.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from ..model.bbox import BBox

#: A dimension this far from the class median (in either direction) is reported.
DEFAULT_SIZE_RATIO = 1.6
#: Two boxes of one class overlapping this much (2D, oriented) are called duplicates.
DEFAULT_DUPLICATE_IOU = 0.55
#: ... or standing this close together, which catches thin boxes inside each other.
DEFAULT_DUPLICATE_DISTANCE = 0.35
#: Boxes smaller/larger than this in any dimension are broken by construction.
MIN_DIMENSION = 0.05
MAX_DIMENSION = 60.0
#: A box with fewer points than this in its own frame is a leftover.
DEFAULT_MIN_POINTS = 5
#: How many label files to read at most (a guard against a folder picked by mistake).
DEFAULT_LIMIT = 20000

KIND_ORDER = (
    "unknown_class",
    "degenerate",
    "not_upright",
    "axis_convention",
    "size_outlier",
    "duplicate",
    "few_points",
    "unreadable",
)


@dataclass
class QualityIssue:
    """One suspicious box (or one unreadable label file)."""

    kind: str
    frame: int
    path: Path
    classname: str
    detail: str
    box_index: int = -1

    @property
    def filename(self) -> str:
        return self.path.stem


@dataclass
class QualityReport:
    """What the pass over the folder found."""

    issues: List[QualityIssue] = field(default_factory=list)
    frames: int = 0
    frames_labelled: int = 0
    boxes: int = 0
    class_counts: Dict[str, int] = field(default_factory=dict)
    medians: Dict[str, Tuple[float, float, float]] = field(default_factory=dict)
    unreadable: List[Path] = field(default_factory=list)

    def counts_by_kind(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for issue in self.issues:
            counts[issue.kind] = counts.get(issue.kind, 0) + 1
        return counts

    def frames_with_issues(self) -> int:
        return len({issue.frame for issue in self.issues if issue.frame >= 0})


# --------------------------------------------------------------------------- #
#                               Geometry helpers                               #
# --------------------------------------------------------------------------- #


def _footprint(box: BBox) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Centre, half axes (2D unit vectors) and half extents of the box footprint."""
    centre = np.asarray(box.get_center(), dtype=float)
    length, width, _height = (float(value) for value in box.get_dimensions())
    yaw = math.radians(float(box.get_z_rotation()))
    ux = np.array([math.cos(yaw), math.sin(yaw)])   # local +x, the ``length`` axis
    uy = np.array([-math.sin(yaw), math.cos(yaw)])  # local +y, the ``width`` axis
    return centre[:2], np.vstack([ux, uy]), np.array([length / 2.0, width / 2.0])


def overlap_2d(first: BBox, second: BBox) -> float:
    """Intersection over union of the two footprints (0.0 when they only touch).

    Uses the separating-axis test on the four candidate axes of two oriented
    rectangles; both boxes are convex, so the test is exact.
    """
    centre_a, axes_a, extents_a = _footprint(first)
    centre_b, axes_b, extents_b = _footprint(second)
    delta = centre_b - centre_a

    # A cheap separating-axis test first: most pairs are nowhere near each other.
    for axis in np.vstack([axes_a, axes_b]):
        distance = abs(float(np.dot(delta, axis)))
        radius_a = float(np.sum(extents_a * np.abs(axes_a @ axis)))
        radius_b = float(np.sum(extents_b * np.abs(axes_b @ axis)))
        if distance >= radius_a + radius_b:
            return 0.0

    area_a = float(4.0 * extents_a[0] * extents_a[1])
    area_b = float(4.0 * extents_b[0] * extents_b[1])
    if area_a <= 0.0 or area_b <= 0.0:
        return 0.0
    intersection = _intersection_area(first, second)
    union = area_a + area_b - intersection
    return float(intersection / union) if union > 0.0 else 0.0


def _corners(box: BBox) -> np.ndarray:
    centre, axes, extents = _footprint(box)
    signs = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]], dtype=float)
    return centre + signs @ (axes * extents)


def _intersection_area(first: BBox, second: BBox) -> float:
    """Area of the intersection of two convex polygons (Sutherland–Hodgman)."""
    subject = _corners(first).tolist()
    clip = _corners(second)
    # clip in counter-clockwise order with an inward normal per edge
    centre_b = np.asarray(second.get_center(), dtype=float)[:2]
    order = clip - centre_b
    clip = clip[np.argsort(np.arctan2(order[:, 1], order[:, 0]))]

    output = subject
    for index in range(len(clip)):
        start = clip[index]
        end = clip[(index + 1) % len(clip)]
        edge = end - start
        if len(output) == 0:
            return 0.0
        input_list = output
        output = []
        inside = lambda point: (  # noqa: E731 - a one-line predicate reads better here
            edge[0] * (point[1] - start[1]) - edge[1] * (point[0] - start[0])
        ) >= 0.0
        for position in range(len(input_list)):
            current = np.asarray(input_list[position], dtype=float)
            previous = np.asarray(input_list[position - 1], dtype=float)
            current_in = inside(current)
            previous_in = inside(previous)
            if current_in != previous_in:
                segment = current - previous
                denominator = edge[0] * segment[1] - edge[1] * segment[0]
                if abs(denominator) > 1e-12:
                    # cross(t) = A + t * denominator with A = edge x (previous - start),
                    # so the crossing sits at t = -A / denominator.
                    t = (
                        edge[0] * (start[1] - previous[1])
                        - edge[1] * (start[0] - previous[0])
                    ) / denominator
                    if 0.0 <= t <= 1.0:
                        output.append(previous + t * segment)
            if current_in:
                output.append(current)
    if len(output) < 3:
        return 0.0
    points = np.asarray(output, dtype=float)
    x = points[:, 0]
    y = points[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)


def centre_distance(first: BBox, second: BBox) -> float:
    """Distance between the two centres (3D)."""
    delta = np.asarray(first.get_center(), dtype=float) - np.asarray(
        second.get_center(), dtype=float
    )
    return float(np.linalg.norm(delta))


# --------------------------------------------------------------------------- #
#                                  The rules                                   #
# --------------------------------------------------------------------------- #


def class_medians(
    per_class: Dict[str, List[Sequence[float]]]
) -> Dict[str, Tuple[float, float, float]]:
    """Median (length, width, height) of every class; classes without boxes are absent."""
    medians: Dict[str, Tuple[float, float, float]] = {}
    for name, dimensions in per_class.items():
        if not dimensions:
            continue
        array = np.asarray(dimensions, dtype=float)
        medians[name] = tuple(float(value) for value in np.median(array, axis=0))  # type: ignore[assignment]
    return medians


def check_frame_boxes(
    boxes: Sequence[BBox],
    frame: int,
    path: Path,
    medians: Optional[Dict[str, Tuple[float, float, float]]] = None,
    known_classes: Optional[Iterable[str]] = None,
    upright_classes: Iterable[str] = (),
    width_axis_classes: Iterable[str] = (),
    size_ratio: float = DEFAULT_SIZE_RATIO,
    duplicate_iou: float = DEFAULT_DUPLICATE_IOU,
    duplicate_distance: float = DEFAULT_DUPLICATE_DISTANCE,
) -> List[QualityIssue]:
    """Every rule that only needs the boxes of one frame."""
    issues: List[QualityIssue] = []
    known = set(known_classes) if known_classes is not None else None
    upright = set(upright_classes)
    width_axis = set(width_axis_classes)
    medians = medians or {}

    for index, box in enumerate(boxes):
        name = box.get_classname()
        length, width, height = (float(value) for value in box.get_dimensions())

        if known is not None and name not in known:
            issues.append(
                QualityIssue(
                    "unknown_class",
                    frame,
                    path,
                    name,
                    "not one of the configured classes",
                    index,
                )
            )

        smallest = min(length, width, height)
        largest = max(length, width, height)
        if smallest < MIN_DIMENSION or largest > MAX_DIMENSION:
            issues.append(
                QualityIssue(
                    "degenerate",
                    frame,
                    path,
                    name,
                    "size %.2f x %.2f x %.2f m is not a real object"
                    % (length, width, height),
                    index,
                )
            )
            continue  # the other rules cannot say anything useful about a broken box

        if name in upright:
            tilt = max(abs(float(box.get_x_rotation())), abs(float(box.get_y_rotation())))
            if tilt > 1.0:
                issues.append(
                    QualityIssue(
                        "not_upright",
                        frame,
                        path,
                        name,
                        "tilted by %.1f deg, but this class is always upright" % tilt,
                        index,
                    )
                )

        if name in width_axis and length > width:
            issues.append(
                QualityIssue(
                    "axis_convention",
                    frame,
                    path,
                    name,
                    "long axis is in length (%.2f m) instead of width (%.2f m)"
                    % (length, width),
                    index,
                )
            )

        median = medians.get(name)
        if median is not None:
            values = (length, width, height)
            for axis, value, expected in zip(("length", "width", "height"), values, median):
                if expected <= 0.0:
                    continue
                ratio = value / expected
                if ratio > size_ratio or ratio < 1.0 / size_ratio:
                    issues.append(
                        QualityIssue(
                            "size_outlier",
                            frame,
                            path,
                            name,
                            "%s %.2f m is %.1fx the usual %.2f m"
                            % (axis, value, ratio, expected),
                            index,
                        )
                    )
                    break

        for other_index in range(index + 1, len(boxes)):
            other = boxes[other_index]
            if other.get_classname() != name:
                continue
            if centre_distance(box, other) <= duplicate_distance:
                issues.append(
                    QualityIssue(
                        "duplicate",
                        frame,
                        path,
                        name,
                        "two %s boxes %.2f m apart" % (name, centre_distance(box, other)),
                        index,
                    )
                )
                break
            iou = overlap_2d(box, other)
            if iou >= duplicate_iou:
                issues.append(
                    QualityIssue(
                        "duplicate",
                        frame,
                        path,
                        name,
                        "overlaps the next %s box by %.0f %%" % (name, iou * 100.0),
                        index,
                    )
                )
                break

    return issues


def check_frame_points(
    boxes: Sequence[BBox],
    points: Optional[np.ndarray],
    frame: int,
    path: Path,
    min_points: int = DEFAULT_MIN_POINTS,
) -> List[QualityIssue]:
    """Boxes of one frame that cover (almost) no points."""
    if points is None or len(points) == 0:
        return []
    issues: List[QualityIssue] = []
    for index, box in enumerate(boxes):
        try:
            count = int(box.is_inside(points).sum())
        except Exception:  # noqa: BLE001 - a broken box must not stop the check
            continue
        if count < min_points:
            issues.append(
                QualityIssue(
                    "few_points",
                    frame,
                    path,
                    box.get_classname(),
                    "only %s point%s inside" % (count, "" if count == 1 else "s"),
                    index,
                )
            )
    return issues


def read_label_file(path: Path) -> List[BBox]:
    """Boxes of one label file; raises on unreadable files."""
    with path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    boxes: List[BBox] = []
    for entry in data.get("objects", []) or []:
        centroid = entry.get("centroid", {})
        dimensions = entry.get("dimensions", {})
        rotations = entry.get("rotations", {})
        box = BBox(
            float(centroid.get("x", 0.0)),
            float(centroid.get("y", 0.0)),
            float(centroid.get("z", 0.0)),
            float(dimensions.get("length", 0.0)),
            float(dimensions.get("width", 0.0)),
            float(dimensions.get("height", 0.0)),
        )
        box.set_rotations(
            float(rotations.get("x", 0.0)),
            float(rotations.get("y", 0.0)),
            float(rotations.get("z", 0.0)),
        )
        box.set_classname(str(entry.get("name", "?")))
        boxes.append(box)
    return boxes


def check_dataset(
    frames: Sequence[Path],
    read_boxes: Callable[[Path], List[BBox]],
    known_classes: Optional[Iterable[str]] = None,
    upright_classes: Iterable[str] = (),
    width_axis_classes: Iterable[str] = (),
    size_ratio: float = DEFAULT_SIZE_RATIO,
    duplicate_iou: float = DEFAULT_DUPLICATE_IOU,
    duplicate_distance: float = DEFAULT_DUPLICATE_DISTANCE,
    min_points: int = DEFAULT_MIN_POINTS,
    current_frame: Optional[int] = None,
    current_points: Optional[np.ndarray] = None,
    progress: Optional[Callable[[int, int], None]] = None,
) -> QualityReport:
    """Check every frame; ``frames`` are point cloud paths in folder order.

    ``current_frame``/``current_points`` add the one rule that needs points: the points
    of the frame that is on screen right now, which are loaded anyway.
    """
    report = QualityReport(frames=len(frames))
    per_class: Dict[str, List[Sequence[float]]] = {}
    frame_boxes: List[Tuple[int, Path, List[BBox]]] = []

    for index, path in enumerate(frames):
        if progress is not None:
            progress(index, len(frames))
        try:
            boxes = list(read_boxes(path))
        except Exception as error:  # noqa: BLE001 - report, do not abort the scan
            logging.warning("Quality check could not read %s: %s", path, error)
            report.unreadable.append(path)
            report.issues.append(
                QualityIssue("unreadable", index, path, "?", "cannot be read: %s" % error)
            )
            continue
        if not boxes:
            continue
        report.frames_labelled += 1
        report.boxes += len(boxes)
        for box in boxes:
            name = box.get_classname()
            report.class_counts[name] = report.class_counts.get(name, 0) + 1
            per_class.setdefault(name, []).append(box.get_dimensions())
        frame_boxes.append((index, path, boxes))

    report.medians = class_medians(per_class)

    for index, path, boxes in frame_boxes:
        report.issues.extend(
            check_frame_boxes(
                boxes,
                index,
                path,
                medians=report.medians,
                known_classes=known_classes,
                upright_classes=upright_classes,
                width_axis_classes=width_axis_classes,
                size_ratio=size_ratio,
                duplicate_iou=duplicate_iou,
                duplicate_distance=duplicate_distance,
            )
        )
        if current_frame is not None and index == current_frame and current_points is not None:
            report.issues.extend(
                check_frame_points(boxes, current_points, index, path, min_points=min_points)
            )

    def sort_key(issue: QualityIssue) -> Tuple[int, int]:
        rank = KIND_ORDER.index(issue.kind) if issue.kind in KIND_ORDER else len(KIND_ORDER)
        return (issue.frame, rank)

    report.issues.sort(key=sort_key)
    logging.info(
        "Quality check: %s issues in %s frames (%s boxes)",
        len(report.issues),
        report.frames,
        report.boxes,
    )
    return report
