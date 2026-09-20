# Changelog

Notable changes in this fork, relative to upstream **labelCloud 1.1.1**
([ch-sa/labelCloud](https://github.com/ch-sa/labelCloud), GPL-3.0).

The label file format is unchanged: `folder` / `filename` / `path` /
`objects[{name, centroid, dimensions, rotations}]`, rotations in degrees
(`centroid_abs`).

## [Unreleased]

### Assist — semi-automatic annotation

* **Click-to-fit** (`Ctrl+G`, *Assist → Fit Box at Cursor*): grows a region around
  the clicked point and fits an oriented box of the current class. Poles are fitted
  upright with the bottom on the locally estimated ground and the cross-section from
  the class template; wires get the long axis in `dimensions.width` with the yaw set
  so the box's local **+y** follows the cable.
* **Refit** (`Ctrl+R`): re-fits the active box to the points inside it, keeping the
  cross-section the user chose.
* **Snap to ground** (`Ctrl+E`).
* **Pre-annotate this frame** (`Ctrl+Shift+G`): runs the offline pole/wire detector
  for the current frame in a background thread and queues its output as proposals.
* **Proposal review queue**: proposals are ordinary boxes flagged as candidates,
  drawn **dashed in orange**; `Enter` confirms the active one and jumps to the next,
  `Ctrl+←`/`Ctrl+→` walk the queue, `Ctrl+Shift+Del` rejects the rest. Duplicates
  within 0.6 m of an existing box are skipped.
* **Fit guards**: a click that lands on a hedge, kerb or wall is refused instead of
  producing an oversized box (median scatter across the cable ≤ 0.9 m, cable length
  ≤ 35 m, with one automatic retry using a tighter region).
* **Fit performance**: the region grower uses a uniform grid index and a per-class
  point cap. On 74k-point frames a fit takes ~0.14 s (pole) / ~0.21 s (wire) median
  instead of freezing the window for seconds.
* **Dataset statistics** (`Ctrl+I`): frames with boxes / confirmed empty / not yet
  labelled / unreadable, plus boxes per class.

### Carry a box forward (Ctrl+Shift+E)

* Labels one object across the following frames in a background thread: the pose is
  extrapolated from the last frames, the size is their median, each frame is
  re-fitted and the box is appended to that frame's label file (existing objects are
  kept, duplicates are skipped), and the pass stops by itself when the object leaves
  the view. The status line reports how many frames were written and why it stopped.

### Multi-frame overlay

* "Overlay previous frames" draws the points of the N previous frames dimmed, so a
  pole hidden by a tree or a barely visible cable can be seen as a whole. The data has
  no ego pose, so the copies shift with vehicle motion — it is a viewing aid, and the
  documentation says so.

### Refit (Ctrl+R) tuning

* The refit **grows onto the object** instead of only fitting what is already
  inside the box: it looks beyond the box (`grow_margin`), keeps what is connected
  to the object (`max_link_distance`), and repeats until the result stops changing,
  so even a box that is far too short ends up covering the whole pole.
* It **stops covering empty stretches**: the extent follows the longest contiguous
  run of points (`max_empty_gap`), so stray points above a pole or a detached tail
  of a cable no longer stretch the box; a box whose points simply start above the
  ground is trimmed to them as well.
* All of it is editable in the **Refit …** dialog (bottom-right panel) and stored in
  the new `[REFIT]` config section; `Ctrl+Shift+R` re-applies the settings to the
  active box, and the status line reports what changed.

### Interface

* The frame/saving card sits at the **bottom-right corner**, below the object list;
  the class selectors keep the position they always had, so the layout is unchanged.
* After a frame loads, its first box is selected again (upstream behaviour), so the box
  actions work without clicking one first.
* File names are elided from the front (`…083316023.pcd`) because every frame shares
  the same timestamp prefix.

### Next-frame prediction

* Predictions **follow the object's motion**: position and heading come from an
  exponential moving average of the last frames' steps and the size is the median of
  those frames (`predict_use_motion`). A new option allows predicting on frames that
  already have labels (`predict_over_existing`, off by default).
* **`predict_next_frame`** (`Ctrl+Shift+P`, *Labels* menu): a frame without its own
  labels receives the previous frame's boxes. Size and heading are carried over, the
  position is re-fitted to the points inside, and a box whose points are gone is
  dropped (`predict_min_points`, `predict_min_point_ratio`). Predictions arrive as
  unconfirmed proposals unless `predict_as_candidates = False`. Unconfirmed
  proposals are **not written**, so browsing a dataset cannot replace hand labels
  with re-fitted predictions; confirming one (`Enter`) makes it content that is
  saved.
* Upstream's `propagate_labels` still works and is now really saved: it copied the
  previous frame's boxes without marking the frame as edited, so they were shown but
  never written. Both options persist to `config.ini`.

### Editing and workflow

* **Undo/redo** (`Ctrl+Z` / `Ctrl+Shift+Z` / `Ctrl+Y`), snapshot based, with burst
  coalescing: one drag or a run of key presses undoes as a single step.
* **Copy / paste / duplicate** (`Ctrl+C` / `Ctrl+V` / `Ctrl+D`); the clipboard
  deliberately survives frame changes so a good box can be reused in the next frame.
* **Group editing**: `Shift`+click adds boxes to a group; movement, rotation,
  scaling, class, delete and flip then apply to the whole group. `Esc` clears it.
* **Local-axis movement** (`U` / `J` / `M` / `;`) so a rotated box moves along its
  own axes instead of the camera axes.
* **Coarse / fine steps**: `Shift` ×10 and `Alt` ×0.1 on every movement, rotation
  and scaling key.
* **Class size templates** (`Ctrl+T`) with a per-class `default_dimensions`; a
  `null` entry keeps the current value.
* **Dimension lock** (`Ctrl+L`): scaling keys, face dragging and refitting respect it.
* **180° flip** (`Ctrl+U`).
* **Focus view** (`Ctrl+F`): draws only the points inside the active box.
* **Pointer mode**: a button next to *Pick/Span/Fit* (and `Esc`) leaves every drawing
  mode so the mouse only navigates again; drawing buttons toggle off when clicked
  twice.
* **Mouse dragging**: drag the box body to move it, drag a hovered face to resize it,
  middle-drag to rotate around z. A gesture is frozen at press time, so resizing no
  longer flips into camera rotation, and the resize is computed from the *total*
  cursor movement instead of accumulating deltas (both caused visible jitter).
* **`Ctrl` + left-drag keeps rotating the box** (upstream's gesture). The face resize
  is no longer allowed to claim it, and the modifier is read from the mouse event
  itself rather than from the key state, so the gesture does not change if Ctrl is
  pressed after the button.
* **Click vs drag**: a drawing mode only builds a box on a release that moved ≤ 5 px,
  so dragging to rotate the cloud no longer drops a stray box.
* **Next-frame class** combo: pins the class new boxes get, frame after frame.
* **± parameter stepper**: pick one of the nine box parameters and nudge it without
  the keyboard.
* **Status bar** shows the world coordinates under the cursor.

### Data safety

* **Per-file label encoding detection**: `centroid` (absolute degrees or relative
  radians), 8-corner `vertices` and KITTI folders are recognised. A file stored in a
  different encoding than the session writes is **never overwritten**, and the first
  rewrite of any file leaves a `.bak` copy.
* **Rotation units are only reported when provable** (`|angle| > 2π` ⇒ degrees);
  ambiguous small angles keep the configured format instead of being guessed.
* **Class definition compatibility**: a bare-list `_classes.json` (as written by the
  pole/wire auto-labeler) loads instead of crashing at startup, entries without
  `id`/`color` are tolerated, and classes that only appear in label files are merged
  in and persisted.
* **Config defaults**: `default_config.ini` is merged under the user's `config.ini`,
  so options added by an update cannot raise `KeyError` on an older file.
* **Save failures** (read-only folder, full disk) are reported instead of raising out
  of the event loop; the frame stays marked as unsaved.
* **Autosave** (`LABEL/autosave_interval_seconds`, default 60 s) writes only edited
  frames.
* **Status bar activity**: the loaded point cloud (`▸ loaded 13:47:02 1/1292 frame.pcd`)
  and the save state (`✓ saved …`, `● unsaved changes`, `— unchanged, nothing to
  write`, `✗ save FAILED`) with the full path in the tooltip; `Ctrl+Shift+S` or a
  click on either indicator opens the activity log listing every load and write with
  time, result and path.
* **Unedited frames are never written** when moving through a dataset — no file is
  created and no existing file is rewritten; `Ctrl+S` forces a write, which is how a
  frame gets marked as deliberately checked and empty. The status bar shows
  `— unchanged, nothing to write` in that case.

### Interface language

* Switchable **English / Simplified Chinese** (`Settings → Language`), including the
  system-locale option; the switch takes effect immediately without a restart.
* Dialogs, message boxes and status messages are translated (309 strings); log
  messages stay English on purpose.
* `tools/update_translations.py` rebuilds the `.ts`/`.qm` from one reviewable
  dictionary and reports anything untranslated.
* `tools/update_readme_shortcuts.py` regenerates the shortcut tables in both
  READMEs from the live keymap.

### Packaging, tooling and docs

* Source repository with `pyproject.toml` and an editable install; the console
  script's shebang now points at the environment it was installed into.
* `run_labelcloud.sh`: one command to start in a fixed work directory with absolute
  dataset paths, `--list` to show datasets, `DRY_RUN=1` to only write the config, and
  a refusal to open a `vertices` label folder with a centroid session.
* `config.ini` is only regenerated when it is missing or the dataset changed, so
  language, shortcuts and autosave settings survive across launches.
* `[ASSIST]` section to point at the offline pre-annotation tool, choose classes and
  pick the pole parameter profile (`recall` / `strict`).
* `[SHORTCUTS]` section to rebind any command, plus an `F1` shortcut overview.
* Dependency-free regression suite (`tests/check_assist.py`, 23 checks) covering
  encodings, class config, language switching, the keymap, undo, templates, fitting
  on synthetic pole/wire scenes, the proposal queue, statistics, save handling and
  mouse-mode behaviour.
* Bilingual `README.md` / `README_zh_cn.md`.

### Fixed

* Confirming a proposal did not mark the frame as edited, because the candidate flag
  was missing from the undo snapshot — the confirmed box was never written.

* `Ctrl+V`/`Ctrl+Z` used to fall through to the single-key commands and rotated the
  box; modifiers are now matched exactly.
* The picking/spanning/fit buttons could not be toggled off because the comparison
  used object identity.
* An upstream circular import made `import labelCloud.model.bbox` fail depending on
  the import order.
* `.gitignore` patterns for the runtime folders also excluded the source packages
  `labelCloud/io/labels/` and `labelCloud/io/pointclouds/`.
* Restoring a saved option checkbox (for example `predict_next_frame = True`) fired
  its handler during window construction and crashed before the controller had a
  view; the persistence handlers are now connected afterwards.
* `oglhelper.DEVICE_PIXEL_RATIO` had no default, so any ray-based interaction raised
  `TypeError` when the GL widget had not been initialised.
