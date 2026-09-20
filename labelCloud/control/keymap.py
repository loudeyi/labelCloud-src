"""Declarative keyboard shortcut table.

labelCloud 1.1.1 dispatches keys with one long ``if/elif`` chain in
``Controller.key_press_event``. That has two problems we hit immediately:

* modifier combinations fall through to the plain-key branch — pressing
  ``Ctrl+V`` (paste, in every other editor) actually rotated the box around y,
  and ``Ctrl+Z`` rotated it around z;
* the bindings exist only in the code, so the interface can neither show them nor
  let the user rebind them.

This module replaces the chain with a table. Bindings are keyed by a
``QKeySequence`` string ("W", "Ctrl+Z", "Shift+W", "Del", "1"), so modifiers are
matched exactly, resolved in this order:

1. an exact match on the pressed sequence (with all modifiers),
2. otherwise the plain key, with ``Shift``/``Alt`` used as *step multipliers*
   (``Shift`` = ×10, ``Alt`` = ×0.1) for the movement, rotation and scaling
   commands — that is how coarse and fine nudging works,
3. otherwise nothing.

Every binding can be overridden from the ``[SHORTCUTS]`` section of ``config.ini``
by command name, e.g. ``copy_box = Ctrl+C``. Unknown or conflicting entries are
logged and the default is kept.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PyQt5.QtGui import QKeySequence

from .config_manager import config

CONFIG_SECTION = "SHORTCUTS"

#: Step multipliers applied to the plain-key branch.
SHIFT_FACTOR = 10.0
ALT_FACTOR = 0.1


@dataclass(frozen=True)
class Binding:
    """One keyboard shortcut."""

    command: str
    sequence: str
    label: str
    group: str
    #: True when the command takes a step size (movement/rotation/scaling), so
    #: Shift/Alt can act as coarse/fine modifiers.
    steppable: bool = False


#: The full default table. ``label`` and ``group`` are shown in the F1 dialog and
#: are translated there, so keep them as plain English source strings.
#:
#: Keys already used by labelCloud 1.1.1 keep their meaning (W/A/S/D/Q/E move,
#: Z/X/C/V/B/N rotate, I/O/K/L/,/. scale, T/G select, Y/H class, digits pick a
#: box). New commands take the keys that were free: U/J/M/; for translation along
#: the box's own axes, and Ctrl combinations for editing.
BINDINGS: Tuple[Binding, ...] = (
    # -- point cloud ------------------------------------------------------- #
    Binding("prev_pcd", "R", "Load previous point cloud", "Point Cloud"),
    Binding("prev_pcd", "Left", "Load previous point cloud", "Point Cloud"),
    Binding("next_pcd", "F", "Load next point cloud", "Point Cloud"),
    Binding("next_pcd", "Right", "Load next point cloud", "Point Cloud"),
    Binding("reset_view", "P", "Reset the point cloud view", "Point Cloud"),
    Binding("reset_view", "Home", "Reset the point cloud view", "Point Cloud"),
    Binding("save", "Ctrl+S", "Save labels", "Point Cloud"),
    # -- bounding box movement (view axes) ---------------------------------- #
    Binding("translate_backward", "W", "Move bounding box backward", "Bounding Box", True),
    Binding("translate_forward", "S", "Move bounding box forward", "Bounding Box", True),
    Binding("translate_left", "A", "Move bounding box left", "Bounding Box", True),
    Binding("translate_right", "D", "Move bounding box right", "Bounding Box", True),
    Binding("translate_up", "Q", "Move bounding box up", "Bounding Box", True),
    Binding("translate_down", "E", "Move bounding box down", "Bounding Box", True),
    # -- bounding box movement (the box's own axes) ------------------------- #
    Binding("translate_local_x", "U", "Move along the box's own x-axis", "Bounding Box", True),
    Binding("translate_local_x_neg", "J", "Move against the box's own x-axis", "Bounding Box", True),
    Binding("translate_local_y", "M", "Move along the box's own y-axis", "Bounding Box", True),
    Binding("translate_local_y_neg", ";", "Move against the box's own y-axis", "Bounding Box", True),
    # -- bounding box rotation --------------------------------------------- #
    Binding("rotate_z_ccw", "Z", "Rotate around z-axis counterclockwise", "Bounding Box", True),
    Binding("rotate_z_cw", "X", "Rotate around z-axis clockwise", "Bounding Box", True),
    Binding("rotate_y_ccw", "C", "Rotate around y-axis counterclockwise", "Bounding Box", True),
    Binding("rotate_y_cw", "V", "Rotate around y-axis clockwise", "Bounding Box", True),
    Binding("rotate_x_ccw", "B", "Rotate around x-axis counterclockwise", "Bounding Box", True),
    Binding("rotate_x_cw", "N", "Rotate around x-axis clockwise", "Bounding Box", True),
    # -- bounding box scaling ---------------------------------------------- #
    Binding("scale_length_up", "I", "Increase length", "Bounding Box", True),
    Binding("scale_length_down", "O", "Decrease length", "Bounding Box", True),
    Binding("scale_width_up", "K", "Increase width", "Bounding Box", True),
    Binding("scale_width_down", "L", "Decrease width", "Bounding Box", True),
    Binding("scale_height_up", ",", "Increase height", "Bounding Box", True),
    Binding("scale_height_down", ".", "Decrease height", "Bounding Box", True),
    # -- selection, classes, editing --------------------------------------- #
    Binding("select_prev_bbox", "T", "Select previous bounding box", "Labels", False),
    Binding("select_prev_bbox", "Up", "Select previous bounding box", "Labels", False),
    Binding("select_next_bbox", "G", "Select next bounding box", "Labels", False),
    Binding("select_next_bbox", "Down", "Select next bounding box", "Labels", False),
    Binding("class_prev", "Y", "Assign previous class", "Labels", False),
    Binding("class_next", "H", "Assign next class", "Labels", False),
    Binding("delete_bbox", "Del", "Delete the active bounding box", "Labels", False),
    Binding("escape", "Esc", "Cancel drawing / deselect", "Labels", False),
    Binding("undo", "Ctrl+Z", "Undo", "Labels", False),
    Binding("redo", "Ctrl+Shift+Z", "Redo", "Labels", False),
    Binding("redo", "Ctrl+Y", "Redo", "Labels", False),
    Binding("copy_box", "Ctrl+C", "Copy the active bounding box", "Labels", False),
    Binding("paste_box", "Ctrl+V", "Paste the copied bounding box", "Labels", False),
    Binding("duplicate_box", "Ctrl+D", "Duplicate the active bounding box in place", "Labels", False),
    Binding("toggle_dimension_lock", "Ctrl+L", "Lock/unlock the box dimensions", "Labels", False),
    Binding("apply_template", "Ctrl+T", "Apply the class template (dimensions + upright)", "Labels", False),
    Binding("fit_box_at_cursor", "Ctrl+G", "Fit a box around the object under the cursor", "Assist", False),
    Binding("refit_box", "Ctrl+R", "Refit the active box to the points inside it", "Assist", False),
    Binding("preannotate_frame", "Ctrl+Shift+G", "Pre-annotate this frame and queue the proposals", "Assist", False),
    Binding("accept_candidate", "Return", "Confirm the proposal under review", "Assist", False),
    Binding("accept_candidate", "Enter", "Confirm the proposal under review", "Assist", False),
    Binding("next_candidate", "Ctrl+Right", "Next unconfirmed proposal", "Assist", False),
    Binding("prev_candidate", "Ctrl+Left", "Previous unconfirmed proposal", "Assist", False),
    Binding("reject_candidates", "Ctrl+Shift+Del", "Reject all proposals in this frame", "Assist", False),
    Binding("flip_180", "Ctrl+U", "Flip the box by 180 degrees", "Assist", False),
    Binding("show_statistics", "Ctrl+I", "Show dataset statistics", "Help", False),
    Binding("snap_box", "Ctrl+E", "Snap the active box onto the ground", "Assist", False),
    Binding("toggle_focus", "Ctrl+F", "Show only the points inside the active box", "View", False),
    Binding("show_shortcuts", "F1", "Show this shortcut list", "Help", False),
)

#: Selecting one of the first nine boxes stays a special case: the bindings are
#: dynamic ("1".."9"), so the controller handles them before consulting the table.
BOX_SELECTION_KEYS = tuple("123456789")

#: Commands reachable from the menu/help but bound to a modifier-held pseudo key.
MODIFIER_NOTE = "Ctrl"
MULTIPLIER_NOTE = "Shift (x10) / Alt (x0.1)"


def event_sequence(modifiers, key) -> str:
    """Normalise a Qt key event into the string used by the table."""
    return QKeySequence(modifiers | key).toString()


def plain_sequence(key) -> str:
    return QKeySequence(key).toString()


def step_factor(modifiers) -> float:
    """Coarse/fine multiplier for the plain-key branch."""
    from PyQt5.QtCore import Qt

    factor = 1.0
    if modifiers & Qt.ShiftModifier:
        factor *= SHIFT_FACTOR
    if modifiers & Qt.AltModifier:
        factor *= ALT_FACTOR
    return factor


class KeyMap:
    """Resolves key events to command names, honouring config overrides."""

    def __init__(self, bindings: Tuple[Binding, ...] = BINDINGS) -> None:
        self.bindings: List[Binding] = list(bindings)
        self.by_sequence: Dict[str, Binding] = {}
        self.steppable_commands = {
            binding.command for binding in self.bindings if binding.steppable
        }
        self._rebuild()
        self._apply_config_overrides()

    # -- construction ------------------------------------------------------- #
    def _rebuild(self) -> None:
        self.by_sequence = {}
        for binding in self.bindings:
            existing = self.by_sequence.get(binding.sequence)
            if existing is not None:
                if existing.command != binding.command:
                    logging.warning(
                        "Shortcut '%s' is bound to both '%s' and '%s'; keeping '%s'.",
                        binding.sequence,
                        existing.command,
                        binding.command,
                        existing.command,
                    )
                continue
            self.by_sequence[binding.sequence] = binding

    def _apply_config_overrides(self) -> None:
        if not config.has_section(CONFIG_SECTION):
            return
        for command, value in config.items(CONFIG_SECTION):
            value = (value or "").strip()
            if not value:
                continue
            known = [b for b in self.bindings if b.command == command]
            if not known:
                logging.warning(
                    "Ignoring shortcut override for unknown command '%s'.", command
                )
                continue
            sequence = QKeySequence(value).toString()
            if not sequence:
                logging.warning(
                    "Ignoring invalid key sequence '%s' for command '%s'.", value, command
                )
                continue
            # drop the existing defaults of this command, then add the override
            self.bindings = [
                b for b in self.bindings if b.command != command and b.sequence != sequence
            ]
            self.bindings.append(
                Binding(command, sequence, known[0].label, known[0].group, known[0].steppable)
            )
            logging.info("Shortcut for '%s' overridden to '%s'.", command, sequence)
        self._rebuild()

    # -- lookup ------------------------------------------------------------- #
    def resolve(self, modifiers, key) -> Tuple[Optional[Binding], float]:
        """Return the binding to run (if any) and the step multiplier to use.

        ``Ctrl`` never falls back to a plain-key binding: otherwise rebinding (or
        removing) ``Ctrl+C`` would silently rotate the box, which is exactly the
        bug this table was written to remove. ``Shift``/``Alt`` do fall back,
        because they act as step multipliers.
        """
        from PyQt5.QtCore import Qt

        exact = self.by_sequence.get(event_sequence(modifiers, key))
        if exact is not None:
            return exact, 1.0

        reserved = modifiers & (Qt.ControlModifier | Qt.MetaModifier)
        if reserved:
            return None, 1.0

        plain = self.by_sequence.get(plain_sequence(key))
        if plain is not None:
            factor = step_factor(modifiers) if plain.steppable else 1.0
            return plain, factor
        return None, 1.0

    # -- reporting ---------------------------------------------------------- #
    def groups(self) -> List[Tuple[str, List[Binding]]]:
        """Bindings grouped for the F1 dialog, duplicate commands collapsed."""
        order: List[str] = []
        grouped: Dict[str, List[Binding]] = {}
        seen: set = set()
        for binding in self.bindings:
            if binding.group not in grouped:
                grouped[binding.group] = []
                order.append(binding.group)
            if binding.command in seen:
                # merge the alternative key into the first entry of that command
                for existing in grouped[binding.group]:
                    if existing.command == binding.command:
                        grouped[binding.group][
                            grouped[binding.group].index(existing)
                        ] = Binding(
                            binding.command,
                            f"{existing.sequence} / {binding.sequence}",
                            existing.label,
                            existing.group,
                            existing.steppable,
                        )
                        break
                continue
            seen.add(binding.command)
            grouped[binding.group].append(binding)
        return [(group, grouped[group]) for group in order]
