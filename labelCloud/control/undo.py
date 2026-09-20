"""Snapshot based undo/redo for the bounding boxes of one frame.

labelCloud 1.1.1 has no undo at all: a wrong drag, a wrong key press or a deleted
box can only be redone by hand. Bounding boxes are tiny objects (a handful per
frame), so the simplest correct implementation is to snapshot the whole list
before every mutation instead of building a command object per operation.

Two details matter for usability:

* **no empty entries** — the decorator in ``bbox_controller`` compares the state
  before and after the call, so an operation that was refused (locked axis,
  blocked tilt, no active box) leaves no trace on the stack;
* **coalescing** — holding a key down produces dozens of tiny moves. Entries that
  share a ``coalesce`` key and arrive within :data:`COALESCE_WINDOW_MS` collapse
  into one, so a single undo returns to before the whole burst.

Frame changes drop the history: undoing across a frame boundary would be
surprising while ``Ctrl+S`` has already written the previous frame to disk.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from ..model.bbox import BBox

#: Entries of the same kind arriving within this window merge into one.
COALESCE_WINDOW_MS = 700

#: Upper bound on remembered steps per frame.
DEFAULT_LIMIT = 200


@dataclass(frozen=True)
class BBoxState:
    """Everything about a box that can be edited."""

    center: Tuple[float, float, float]
    dimensions: Tuple[float, float, float]
    rotations: Tuple[float, float, float]
    classname: str
    locked: bool
    #: Unconfirmed proposal flag. Part of the snapshot because confirming a
    #: proposal is an edit: without it the frame stayed "unchanged" and the
    #: confirmed box was never written to disk.
    candidate: bool = False

    @classmethod
    def from_bbox(cls, bbox: BBox) -> "BBoxState":
        return cls(
            center=tuple(bbox.get_center()),  # type: ignore[arg-type]
            dimensions=tuple(bbox.get_dimensions()),  # type: ignore[arg-type]
            rotations=tuple(bbox.get_rotations()),  # type: ignore[arg-type]
            classname=bbox.get_classname(),
            locked=bool(getattr(bbox, "locked", False)),
            candidate=bool(getattr(bbox, "candidate", False)),
        )

    def to_bbox(self) -> BBox:
        bbox = BBox(*self.center, *self.dimensions)
        bbox.set_rotations(*self.rotations)
        bbox.set_classname(self.classname)
        bbox.locked = self.locked
        bbox.candidate = self.candidate
        return bbox


@dataclass(frozen=True)
class FrameState:
    """A restorable snapshot of one frame's labels."""

    bboxes: Tuple[BBoxState, ...]
    active_id: int
    description: str = ""

    @classmethod
    def capture(
        cls, bboxes: Sequence[BBox], active_id: int, description: str = ""
    ) -> "FrameState":
        return cls(
            bboxes=tuple(BBoxState.from_bbox(bbox) for bbox in bboxes),
            active_id=active_id,
            description=description,
        )

    @property
    def size(self) -> int:
        return len(self.bboxes)

    def same_as(self, other: "FrameState") -> bool:
        return self.bboxes == other.bboxes and self.active_id == other.active_id


class UndoStack:
    """Bounded history of :class:`FrameState` snapshots."""

    def __init__(self, limit: int = DEFAULT_LIMIT) -> None:
        self.limit = limit
        self._past: List[Tuple[FrameState, Optional[str], float]] = []
        self._future: List[FrameState] = []

    # -- state -------------------------------------------------------------- #
    @property
    def can_undo(self) -> bool:
        return bool(self._past)

    @property
    def can_redo(self) -> bool:
        return bool(self._future)

    def clear(self) -> None:
        self._past.clear()
        self._future.clear()

    def peek_undo_description(self) -> Optional[str]:
        return self._past[-1][0].description if self._past else None

    def peek_redo_description(self) -> Optional[str]:
        return self._future[-1].description if self._future else None

    # -- recording ---------------------------------------------------------- #
    def record(
        self,
        before: FrameState,
        description: str,
        coalesce: Optional[str] = None,
        now: Optional[float] = None,
    ) -> None:
        """Remember the state as it was *before* an edit."""
        before = FrameState(before.bboxes, before.active_id, description)
        now = time.monotonic() * 1000.0 if now is None else now
        self._future.clear()

        if coalesce and self._past:
            previous, previous_key, previous_time = self._past[-1]
            if previous_key == coalesce and (now - previous_time) <= COALESCE_WINDOW_MS:
                # keep the older snapshot, just extend the burst
                self._past[-1] = (previous, coalesce, now)
                return

        self._past.append((before, coalesce, now))
        if len(self._past) > self.limit:
            del self._past[0 : len(self._past) - self.limit]

    # -- navigation --------------------------------------------------------- #
    def undo(self, current: FrameState) -> Optional[FrameState]:
        if not self._past:
            return None
        target, _key, _time = self._past.pop()
        self._future.append(FrameState(current.bboxes, current.active_id, target.description))
        logging.info("Undo: %s.", target.description or "edit")
        return target

    def redo(self, current: FrameState) -> Optional[FrameState]:
        if not self._future:
            return None
        target = self._future.pop()
        self._past.append((FrameState(current.bboxes, current.active_id, target.description), None, 0.0))
        logging.info("Redo: %s.", target.description or "edit")
        return target
