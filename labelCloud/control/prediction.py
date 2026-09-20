"""Deciding which boxes of the previous frame survive into the next one.

Poles and wires are static, so their boxes stay valid — but only while the object
is still in view. The signal for "it is gone" is the number of points inside the
box, and this module turns that signal into a decision:

* every box carries a short **point-count history** (an exponential moving average
  plus the last observation) while it is carried from frame to frame;
* **adaptive mode** (default) compares the new count with that history:
  ``expected - sensitivity * deviation``. A pole that is progressively hidden behind
  a tree keeps being tracked because its history follows the occlusion, while one
  that leaves the field of view collapses and is dropped;
* **fixed-ratio mode** compares with the previous frame's count directly, which is
  what "drop it once the points halve" means (``predict_min_point_ratio``, 0.5 by
  default);
* an absolute floor (``predict_min_points``) always applies.

The numbers are stored on the box as plain attributes rather than in the label
file: the export format has to stay compatible with upstream labelCloud.
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from typing import List, Optional, Tuple

DEFAULT_RATIO = 0.5
DEFAULT_MIN_POINTS = 5
DEFAULT_SENSITIVITY = 1.5
#: How many previous frames the motion model looks at.
DEFAULT_HISTORY_FRAMES = 4
#: Weight of the newest step in the velocity estimate (0.5 = the MaFilter decay
#: SUSTechPOINTS uses for the same purpose).
VELOCITY_DECAY = 0.5
#: How many observations of an object's point count are remembered.
HISTORY_LENGTH = 6
#: Weight of the newest observation in the exponential moving average.
EMA_ALPHA = 0.4


@dataclass
class TrackSample:
    """What one object looked like in one frame."""

    center: Tuple[float, float, float]
    yaw: float
    dimensions: Tuple[float, float, float]
    count: int


class PointHistory:
    """What one object looked like over the frames it has been followed through.

    Besides the point counts (used to decide whether the object is still there) this
    carries the last few *poses* and *sizes*. That is what lets the prediction follow
    the object's motion instead of copying the previous frame's box: a pole that
    moves left at 0.8 m per frame keeps moving left, and its size is taken from the
    last few frames rather than from a single noisy one.
    """

    __slots__ = ("counts", "ema", "deviation", "samples")

    def __init__(self) -> None:
        self.counts: List[int] = []
        self.ema: Optional[float] = None
        self.deviation: Optional[float] = None
        self.samples: List[TrackSample] = []

    @classmethod
    def from_bbox(cls, bbox) -> "PointHistory":
        history = cls()
        history.counts = list(getattr(bbox, "point_history", []) or [])
        ema = getattr(bbox, "point_count_ema", None)
        deviation = getattr(bbox, "point_count_deviation", None)
        history.ema = None if ema is None else float(ema)
        history.deviation = None if deviation is None else float(deviation)
        history.samples = list(getattr(bbox, "track_samples", []) or [])
        return history

    def observe(self, count: int, bbox=None) -> None:
        self.counts.append(int(count))
        del self.counts[:-HISTORY_LENGTH]
        if self.ema is None:
            self.ema = float(count)
        else:
            self.ema = EMA_ALPHA * count + (1.0 - EMA_ALPHA) * self.ema
        if len(self.counts) >= 2:
            self.deviation = statistics.pstdev(self.counts)
        else:
            self.deviation = None
        if bbox is not None:
            self.samples.append(
                TrackSample(
                    center=tuple(float(v) for v in bbox.get_center()),
                    yaw=float(bbox.get_z_rotation()),
                    dimensions=tuple(float(v) for v in bbox.get_dimensions()),
                    count=int(count),
                )
            )
            del self.samples[:-max(DEFAULT_HISTORY_FRAMES, 2)]

    def attach_to(self, bbox) -> None:
        bbox.point_history = list(self.counts)
        bbox.point_count_ema = self.ema
        bbox.point_count_deviation = self.deviation
        bbox.track_samples = list(self.samples)

    # -- motion ------------------------------------------------------------- #
    def velocity(self) -> Optional[Tuple[float, float, float]]:
        """Per-frame displacement, estimated from the last few samples.

        An exponential moving average of the frame-to-frame steps, so one jump does
        not define the motion. ``None`` until there are two samples.
        """
        if len(self.samples) < 2:
            return None
        velocity = [0.0, 0.0, 0.0]
        for previous, current in zip(self.samples, self.samples[1:]):
            step = [c - p for c, p in zip(current.center, previous.center)]
            velocity = [
                VELOCITY_DECAY * step[i] + (1.0 - VELOCITY_DECAY) * velocity[i]
                for i in range(3)
            ]
        return tuple(velocity)  # type: ignore[return-value]

    def yaw_velocity(self) -> float:
        """Per-frame change of the heading, wrapped to ±180°."""
        if len(self.samples) < 2:
            return 0.0
        velocity = 0.0
        for previous, current in zip(self.samples, self.samples[1:]):
            step = (current.yaw - previous.yaw + 180.0) % 360.0 - 180.0
            velocity = VELOCITY_DECAY * step + (1.0 - VELOCITY_DECAY) * velocity
        return velocity

    def stable_dimensions(self) -> Optional[Tuple[float, float, float]]:
        """Median size over the samples: sizes are rigid, so this is the best guess."""
        if not self.samples:
            return None
        return tuple(
            float(statistics.median(sample.dimensions[i] for sample in self.samples))
            for i in range(3)
        )  # type: ignore[return-value]

    # -- decisions ---------------------------------------------------------- #
    def threshold(self, ratio: float, min_points: int, sensitivity: float, adaptive: bool):
        """Return ``(threshold, reason)``: the count below which the box is dropped."""
        if adaptive and self.ema is not None and len(self.counts) >= 2:
            deviation = self.deviation or 0.0
            adaptive_threshold = self.ema - sensitivity * deviation
            # never demand more than the fixed ratio would: the adaptive rule only
            # makes the decision *later* for objects whose count naturally varies
            threshold = max(min_points, min(adaptive_threshold, self.ema * ratio))
            return threshold, "adaptive"
        reference = self.counts[-1] if self.counts else 0
        return max(min_points, ratio * reference), "ratio"


def decide(
    count: int,
    history: PointHistory,
    ratio: float,
    min_points: int,
    sensitivity: float,
    adaptive: bool,
) -> Tuple[bool, str]:
    """Return ``(keep, reason)`` for one object in the new frame."""
    threshold, mode = history.threshold(ratio, min_points, sensitivity, adaptive)
    if count < threshold:
        logging.info(
            "Dropping a prediction: %s points, threshold %.1f (%s, history %s).",
            count,
            threshold,
            mode,
            history.counts[-HISTORY_LENGTH:],
        )
        return False, mode
    return True, mode
