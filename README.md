# labelCloud — pole & wire assist fork

> A fork of [labelCloud](https://github.com/ch-sa/labelCloud) (GPL-3.0) turned into a practical
> annotation tool for **power lines (`wire`)** and **utility poles (`pole`)** in LiDAR sequences.
> It keeps labelCloud's file format and adds the things that actually save time when the same pole
> shows up in a hundred consecutive frames.

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.8-blue.svg)
![Platform](https://img.shields.io/badge/platform-linux-lightgrey.svg)

**English** · [简体中文](README_zh_cn.md) · [Changelog](CHANGELOG.md) · [Design notes](docs/README.md)

---

## Why this fork exists

Labelling poles and wires by hand in labelCloud 1.1.1 is slow for four specific reasons, and this
fork addresses each of them:

| Problem | What this fork does |
| --- | --- |
| A new box is 0.75 × 0.55 × 0.15 m — nothing like a pole (8–18 m tall) or a wire (5–21 m long) | **Per-class size templates** (`Ctrl+T`) and **one-click fitting** (`Ctrl+G`) |
| Boxes have to be corrected one at a time, with no way back | **Undo/redo**, **copy/paste/duplicate**, **local-axis nudging**, **mouse dragging**, a **± parameter stepper** |
| Automatic pre-labels arrive as a whole directory, then have to be deleted one by one | **Proposal review queue**: pre-annotate the current frame (`Ctrl+Shift+G`), then `Enter` to confirm and `Ctrl+→` to jump to the next |
| The same pole is re-labelled in every frame of a 5–10 Hz sequence | **Clipboard that survives frame changes**, box templates, and the groundwork for keyframe interpolation |
| Several boxes often need the same correction | **Group editing**: `Shift`+click adds boxes to a group, then every move/rotate/scale/class/delete/flip applies to all of them at once (`Esc` clears the group) |

The interface is available in **English and Simplified Chinese** (`Settings → Language`), switchable
without restarting.

## Assist features

| Feature | Shortcut | What it does |
| --- | --- | --- |
| **Click-to-fit** | `Ctrl+G` | Grows a region around the clicked point and fits an oriented box of the current class |
| **Refit** | `Ctrl+R` | Re-fits the active box to the points inside it, keeping the cross-section you chose |
| **Snap to ground** | `Ctrl+E` | Puts the box bottom on the local ground |
| **Pre-annotate frame** | `Ctrl+Shift+G` | Runs the offline pole/wire detector for this frame in a background thread and queues the proposals |
| **Confirm proposal** | `Enter` | Turns the dashed orange proposal into a normal box and jumps to the next one |
| **Walk proposals** | `Ctrl+←` / `Ctrl+→` | Previous / next unconfirmed proposal |
| **Reject proposals** | `Ctrl+Shift+Del` | Removes every unconfirmed proposal in the frame |
| **180° flip** | `Ctrl+U` | Flips the box heading |
| **Focus view** | `Ctrl+F` | Draws only the points inside the active box (dense frames) |
| **Dataset statistics** | `Ctrl+I` | Frames labelled / confirmed empty / not yet labelled, and boxes per class |
| **Carry forward** | `Ctrl+Shift+E` | Follows the box into the next frames until the object is gone (5 frames per press) |
| **Keyframe interpolation** | `Ctrl+Shift+I` then `Ctrl+Shift+K` | Boxes the two ends of a gap and fills every frame in between |
| **Quality check** | `Ctrl+Shift+Q` | Reads every label file and lists the boxes that look wrong, with a jump to the frame |

Proposals are drawn **dashed in orange** and never look like confirmed labels. Accepting one is a
single keystroke; rejecting is one keystroke for the whole batch.

## Workflow and safety features

| Feature | Where | What it does |
| --- | --- | --- |
| **Pointer mode** | button next to *Pick/Span/Fit*, or `Esc` | Leaves every drawing mode so the mouse only navigates the cloud again. The drawing buttons also toggle off when clicked twice, and **dragging never creates a box** — a fit only happens on a real click (≤ 5 px of movement) |
| **Next-frame class** | "New boxes in next frames" combo | Pins the class every new box gets, frame after frame: one pass can label poles, the next pass wires, without re-picking the class in each frame |
| **Load indicator** | right of the status bar | `▸ loaded 13:47:02 1/1292  frame.pcd` — which point cloud is on screen, with its position in the folder |
| **Save indicator** | right of the status bar | `✓ saved 13:38:09  frame.json`, `● unsaved changes`, `— unchanged, nothing to write`, or a red `✗ save FAILED`. The tooltip shows the full path |
| **Activity log** | click either indicator, `Ctrl+Shift+S`, or *File → Save Log* | Every frame loaded and every write, with time, result and exact path |
| **Session card** | right panel, above *Current BBox* | The same information at a glance: frame `2/1292`, the save state with its time, the last two events, the prediction state, and buttons for the activity log and the prediction settings |
| **Next-frame prediction** | *Labels → Predict Boxes for the Next Frame*, or `Ctrl+Shift+P` | Carries the boxes of the current frame into the next one: size and heading are kept, the position follows the points, and an object whose points are gone stops being predicted |
| **Autosave** | every 60 s (`LABEL/autosave_interval_seconds`) | Writes only when something was actually edited. A frame you merely browsed past is **not written at all** — press `Ctrl+S` to record it as "checked, and it is empty" |
| **Group editing** | `Shift`+click boxes | Move/rotate/scale/class/delete/flip act on the whole group |
| **Undo/redo** | `Ctrl+Z` / `Ctrl+Shift+Z` | One step per gesture: a whole drag, or a burst of key presses, undoes as a single action |
| **Dimension lock + templates** | `Ctrl+L` / `Ctrl+T` | Protects a fitted size; templates fix the pole cross-section and the wire section |

## How to use it

A practical walk-through of the features that are not obvious from the shortcut
list. Everything below is in the application, no file editing required.

### Fitting a box to an object (`Ctrl+R` refit)

1. Put a box roughly on the object — it may be too small, too long or slightly off;
   it does not have to be right.
2. Press **`Ctrl+R`**. The refit
   * looks **beyond** the box so points it only just misses are included
     (`Look this far beyond the box`),
   * walks along the object and keeps only what is **connected** to it
     (`A point further than this is not part of the object`),
   * **trims stretches without points** so the box cannot cover an empty section
     (`Trim empty stretches longer than`),
   * repeats until the result stops changing, so even a box that is far too short
     grows onto the whole pole,
   * keeps the cross-section you set unless you tick
     `Also re-fit the cross-section`.
3. The status line reports what changed: `Refit: length 2.60 -> 2.64, height 3.00 -> 10.63 m`.
4. Tune it in **Refit …** (bottom-right panel). Practical hints:

   | Symptom | Change |
   | --- | --- |
   | the refit leaves points out | raise *look beyond the box* and *not part of the object* |
   | a point far away is pulled in | lower *not part of the object* |
   | the box covers a section with no points | lower *trim empty stretches* |
   | small specks extend the box | raise *ignore clusters smaller than* |

   **`Ctrl+Shift+R`** applies the current settings to the active box again, so you
   can try a value and immediately see the effect.

### Label one object across many frames (`Ctrl+Shift+E`)

1. Put a box on the object in the frame where it is best visible (fit it with `Ctrl+R`
   if you like).
2. Press **`Ctrl+Shift+E`** — *Assist → Carry This Box Forward to the End*. The box is
   carried into the following frames in the background:
   * its next pose is **extrapolated from the last frames** (position and heading),
     and its **size is the median of those frames**, so it follows the object instead
     of copying one box;
   * each frame's box is **re-fitted to the points** (configurable) and **appended** to
     that frame's label file, so other objects already there are kept;
   * a frame that already contains this object is left alone (no duplicates);
   * the pass **stops by itself when the object is gone** — when the points inside the
     box fall below the prediction thresholds — and the status line reports how many
     frames were written and where it stopped: `Propagated to 5 frames (0 skipped):
     object left the view at 177641487...pcd (3 points, adaptive rule)`.
3. The status bar shows progress while it runs; you can keep working. The result is
   *the answer to "how long was this pole in view"*, which is useful on its own.

One press writes **at most five frames** (`propagate_max_frames`): far enough to get
through a short occlusion, short enough that a prediction which slowly drifts cannot pile
up boxes deep into the sequence. Press it again from the newest frame to continue.
`propagate_refit = False` writes the extrapolated box without re-fitting it.

### Filling a gap between two keyframes (`Ctrl+Shift+I` → `Ctrl+Shift+K`)

Carry-forward follows *motion*. When the object is easy to box at the start and at the end
of a stretch but hidden in between — a pole behind a tree, a cable in a gap of points — the
frames in between can be computed from the two ends:

1. In the earlier frame, box the object and press **`Ctrl+Shift+I`** (*Assist → Set
   Keyframe Here*). The session card shows `Keyframe: frame 40 · pole`.
2. Jump forward — ten, fifty, three hundred frames — and box the **same object** again.
   This second box is the other end.
3. Press **`Ctrl+Shift+K`** (*Assist → Interpolate from the Keyframe to Here*).

The frames in between are filled in the background:

* position and size are **interpolated** between the two boxes, so the result does not
  depend on how steady the vehicle was driving;
* the heading takes the **shortest arc** — a pole that turns from 350° to 10° turns 20°,
  not 340° the other way round;
* every generated box is checked against the points of **its own frame**: a frame where
  the object is not there is **skipped**, never filled with a guess, and a frame that
  already holds the object is **left alone**;
* the writing follows the usual safety rules (backup before the first rewrite, refused
  outright on `vertices`-format files).

The status line reports the result — `Interpolation: filled 48 of 52 frames (4 without
points, 0 already labelled)` — and `propagate_refit` decides whether each interpolated box
is re-fitted to the points it covers (on by default).

### Seeing an object whole: overlay previous frames

The **Overlay previous frames** spin box in the left *Point Cloud* group draws the
points of the N previous frames in a dim grey-blue. A pole that is hidden behind a
tree in this frame, or a cable that only shows a few points, becomes visible as a
whole.

Because the data has **no ego pose**, the copies shift as the vehicle moves — this is
a viewing aid, not a merged cloud. Keep N small (2–5) and remember that fitting still
uses only the current frame. `0` turns it off.

### Predicting the next frame (`Ctrl+Shift+P`)

1. Enable it in the **Labels** menu or with `Ctrl+Shift+P`. The bottom-right panel
   shows `Prediction: on · adaptive 50%`.
2. Label one frame, then move on. A frame **without its own labels** receives the
   previous frame's boxes as **dashed orange proposals**; the status line says
   `Predicted N boxes from the previous frame (M dropped)`.
3. `Enter` confirms the proposal under review and jumps to the next, `Ctrl+→` /
   `Ctrl+←` walk them, `Ctrl+Shift+Del` rejects the rest.
   Unconfirmed proposals are **not written**, so browsing cannot replace your labels.
4. The prediction **follows the object's motion**: position and heading are
   extrapolated from the last frames (an exponential moving average of the
   frame-to-frame steps), and the size is the **median of the last frames**, so a
   single badly fitted box does not define the prediction. `predict_use_motion = False`
   copies the previous box instead.
5. Tick **predict even when the frame already has labels** to use predictions on frames
   that already have their own boxes (off by default, because it mixes guesses into
   your labels).
6. A box is dropped when the object is gone: fewer points than
   `always below this absolute count`, or fewer than the adaptive/fixed share of its
   own recent point count. See **Prediction …**:

   | Setting | Meaning |
   | --- | --- |
   | *Adaptive threshold* | compare with the object's own history (mean − k × deviation); follows a pole that is slowly occluded |
   | *Adaptive sensitivity* | k — higher keeps boxes longer |
   | *Drop when fewer than this share* | for example 50 %: the points halved, so the object is leaving |
   | *... and always below this absolute count* | a floor, so two stray points never predict a box |

7. `predict_as_candidates = False` (dialog checkbox) makes predictions count as
   finished boxes, which are then saved like your own.

### Checking the whole folder before handing it over (`Ctrl+Shift+Q`)

The mistakes that survive a long labelling session are the boring ones, and they only
show up when the dataset is used. **`Ctrl+Shift+Q`** (*Assist → Quality Check …*) reads
every label file of the folder (labels only, so a few hundred frames take a moment) and
lists what looks wrong:

| Reported | Because |
| --- | --- |
| **Size far from the usual size of its class** | the dimension differs from the median of that class in *this* folder by more than `size_ratio` (1.6x) — the person who labelled 200 poles is the best definition of how big a pole is here |
| **Duplicate or overlapping box** | two boxes of one class whose centres are closer than `duplicate_distance` (0.35 m) or whose footprints overlap by more than `duplicate_iou` (55 %) |
| **Tilted although the class is upright** | a class the configuration keeps upright (`z_rotation_only`, per class in `_classes.json` or globally) with roll or pitch |
| **Long axis in length instead of width** | a cable-shaped class template (`width > length`) whose boxes ended up with the long axis in `length` |
| **Impossible size** | a dimension below 5 cm or above 60 m |
| **Class not in `_classes.json`** | a typo in a class name that was added by a label file |
| **Covers (almost) no points** | fewer than `min_points` (5) points inside the box in the current frame — the one rule that needs points, and they are already loaded |
| **Label file cannot be read** | broken JSON, or a format this check cannot parse (a `vertices` file, for example) |

Double-click a row (or select it and press *Go to Frame*) to open that frame and fix it;
*Check again* re-scans after the fix. The check never writes anything. The thresholds are
the `[QUALITY]` config section.

### Knowing what was saved (bottom-right panel)

The card at the bottom-right of the window and the status bar show the same thing:

* `Frame 2/1292 · …083316023.pcd` — which frame is on screen,
* `✓ saved · …83377525.json` (green), `● unsaved changes` (orange),
  `— unchanged, nothing to write` (grey) or `✗ save FAILED` (red),
* the last two events with their times,
* **Activity log** opens the full list (also `Ctrl+Shift+S`): every frame loaded and
  every write, with time, result and the complete path. Hovering the status bar
  entries shows the full path too.

### Quick wins worth remembering

* **Pointer mode** (first button on the left, or `Esc`) leaves every drawing mode so
  the mouse only navigates; dragging never creates a box, a fit needs a real click.
* **Next-frame class** (right panel) pins what new boxes get, so one pass can label
  poles and the next pass wires.
* **`Ctrl+T`** applies the class template (pole cross-section, wire section) and
  straightens the box; **`Ctrl+L`** locks the size against accidental edits.
* **`Ctrl+C` / `Ctrl+V`** carry a box into the next frame; **`Shift`+click** builds a
  group so one command moves/rotates/deletes several boxes at once.
* **`Ctrl+F`** shows only the points inside the active box — the fastest way to see
  whether a box really covers its object.

## Next-frame prediction

Poles and wires are static, so the boxes of one frame are almost right in the next
one. With prediction enabled, every frame without its own labels receives the
previous frame's boxes:

* **size and orientation are carried over** (the objects are rigid);
* the **position is re-fitted** to the points inside the box, so it follows the
  vehicle's motion instead of being copied blindly;
* a box is **dropped when its points are gone** — fewer than `predict_min_points`
  points inside, or less than `predict_min_point_ratio` of the points it held in the
  previous frame. That is the signal that the pole is behind you;
* predictions arrive as **unconfirmed proposals** (dashed orange) unless
  `predict_as_candidates = False`; `Enter` confirms one, `Ctrl+→` walks them.

```ini
[LABEL]
predict_next_frame = True     ; also toggled from the Labels menu (Ctrl+Shift+P)
predict_as_candidates = True  ; start as proposals instead of finished boxes
predict_refit = True          ; re-fit each prediction to its points
predict_min_points = 5        ; drop below this absolute count
predict_min_point_ratio = 0.5  ; ... or below this share of the previous count
```

Predictions arrive as **unconfirmed proposals** and are therefore **not written**:
nothing was decided about them yet, so flipping through a dataset cannot replace
hand labels with re-fitted predictions. Pressing `Enter` confirms one, and a
confirmed box counts as edited content and is saved. Set
`predict_as_candidates = False` to use predictions as finished boxes directly. A
frame that already has its own labels is never overwritten with predictions. The older `propagate_labels` option still works and now really is
saved (upstream copied the boxes without marking the frame as edited).

## Bounding-box conventions

These match the labels this project was built for, and the fitting code follows them:

| Class | Convention |
| --- | --- |
| `pole` | Upright box (`rz = 0`), bottom sitting on the local ground, cross-section from the template (length ≈ 2.6 m, width ≈ 4.0 m), height follows the structure |
| `wire` | The **long axis is stored in `dimensions.width`** (not `length`), and the yaw is set so the box's local **+y** follows the cable |

Per-class behaviour is configured in the class definition file (`_classes.json`):

```json
{
  "classes": [
    { "name": "pole", "id": 1, "color": "#00ff7f",
      "z_rotation_only": true,
      "default_dimensions": { "length": 2.6, "width": 4.0, "height": null } },
    { "name": "wire", "id": 2, "color": "#00aaff",
      "z_rotation_only": false,
      "default_dimensions": { "length": 2.5, "width": null, "height": 2.0 } }
  ],
  "default": 1,
  "type": "object_detection",
  "format": "centroid_abs"
}
```

* `z_rotation_only` — a pole only ever needs yaw; a sagging cable does not, so wires may be tilted.
  `null`/absent means "follow the global `USER_INTERFACE/z_rotation_only`".
* `default_dimensions` — `null` means "keep the current value", so a pole template fixes the
  cross-section while the height stays whatever the structure needs.

Export format is unchanged from upstream labelCloud: `folder` / `filename` / `path` /
`objects[{name, centroid, dimensions, rotations}]`, rotations in **degrees** (`centroid_abs`).
Files written by other tools are detected per file, and a file stored in a different encoding is
**never overwritten** (a `.bak` copy is kept whenever one is rewritten).

## Install

```bash
git clone <this-repo> labelCloud-src
cd labelCloud-src

python3.8 -m venv .venv
.venv/bin/pip install -e .

.venv/bin/labelCloud --version
```

Dependencies: `numpy<2`, `open3d`, `PyOpenGL`, `PyOpenGL-accelerate`, `PyQt5>=5.15.7`, `scipy`.
Tested on Python 3.8 / Linux with an OpenGL-capable display.

## Quick start

```bash
./run_labelcloud.sh --list                    # show the datasets found under DATASETS_ROOT
./run_labelcloud.sh                           # start on the default dataset
./run_labelcloud.sh 2026_0416 labels_lc       # pick a dataset and a label folder
DRY_RUN=1 ./run_labelcloud.sh                 # only (re)generate config.ini, do not start
```

The launcher keeps everything in one work directory instead of scattering `config.ini`, `labels/`
and stray JSON files wherever the app happened to be started:

```
labelcloud-work/
├── config.ini          generated on every start (previous one saved as config.ini.bak)
└── _classes.json       pole/wire classes, colours and templates
```

It also refuses to open a label folder holding 8-corner `vertices` files while the session is
configured for `centroid` boxes — reading those as centroid labels would show an empty frame and
then overwrite them on the next auto-save.

## Recommended workflow

```
        ┌──────────────────────── one frame ────────────────────────┐
        │                                                           │
 Ctrl+Shift+G ──► proposals (dashed orange) ──► Enter  confirm      │
        │              │                            │              │
        │              └── Ctrl+→ walk ──────────────┘              │
        │              └── Ctrl+Shift+Del reject the rest            │
        │                                                           │
 nothing proposed? ──► Ctrl+G click-to-fit ──► Ctrl+R refit ──► Ctrl+E snap
        │                                                           │
        └──────────────► Ctrl+S / autosave ──► next frame ──────────┘
                    (Ctrl+Z undo, Ctrl+C/Ctrl+V to reuse a box)
```

0. Stay in **Pointer mode** while you look around; arm *Fit Box* only while you are fitting, and
   leave it with `Esc` or the pointer button.
1. **Pre-annotate** the frame and work through the proposals with `Enter`.
2. For anything missed, **click it** (`Ctrl+G`) — the box is fitted to the points, not dropped at a
   fixed size.
3. Polish with `Ctrl+R` (refit), `Ctrl+E` (ground) and the local-axis keys `U/J/M/;`.
4. Copy a good box with `Ctrl+C` and paste it in the next frame with `Ctrl+V` — the clipboard
   survives frame changes on purpose.

## Keyboard shortcuts

`Shift` multiplies the step size by **10**, `Alt` divides it by **10** (movement, rotation and
scaling keys). Every binding can be changed in the `[SHORTCUTS]` section of `config.ini`, for
example `copy_box = Ctrl+Shift+C`. `F1` shows the same table inside the application, translated.

<!-- BEGIN SHORTCUTS -->

### Point Cloud

| Keys | Action |
| --- | --- |
| `R / Left` | Load previous point cloud |
| `F / Right` | Load next point cloud |
| `P / Home` | Reset the point cloud view |
| `Ctrl+S` | Save labels |

### Bounding Box

| Keys | Action |
| --- | --- |
| `W` | Move bounding box backward |
| `S` | Move bounding box forward |
| `A` | Move bounding box left |
| `D` | Move bounding box right |
| `Q` | Move bounding box up |
| `E` | Move bounding box down |
| `U` | Move along the box's own x-axis |
| `J` | Move against the box's own x-axis |
| `M` | Move along the box's own y-axis |
| `;` | Move against the box's own y-axis |
| `Z` | Rotate around z-axis counterclockwise |
| `X` | Rotate around z-axis clockwise |
| `C` | Rotate around y-axis counterclockwise |
| `V` | Rotate around y-axis clockwise |
| `B` | Rotate around x-axis counterclockwise |
| `N` | Rotate around x-axis clockwise |
| `I` | Increase length |
| `O` | Decrease length |
| `K` | Increase width |
| `L` | Decrease width |
| `,` | Increase height |
| `.` | Decrease height |

### Labels

| Keys | Action |
| --- | --- |
| `T / Up` | Select previous bounding box |
| `G / Down` | Select next bounding box |
| `Y` | Assign previous class |
| `H` | Assign next class |
| `Del` | Delete the active bounding box |
| `Esc` | Cancel drawing / deselect |
| `Ctrl+Z` | Undo |
| `Ctrl+Shift+Z / Ctrl+Y` | Redo |
| `Ctrl+C` | Copy the active bounding box |
| `Ctrl+V` | Paste the copied bounding box |
| `Ctrl+D` | Duplicate the active bounding box in place |
| `Ctrl+L` | Lock/unlock the box dimensions |
| `Ctrl+T` | Apply the class template (dimensions + upright) |
| `Ctrl+Shift+P` | Toggle next-frame prediction |

### Assist

| Keys | Action |
| --- | --- |
| `Ctrl+G` | Fit a box around the object under the cursor |
| `Ctrl+R` | Refit the active box to the points inside it |
| `Ctrl+Shift+G` | Pre-annotate this frame and queue the proposals |
| `Return / Enter` | Confirm the proposal under review |
| `Ctrl+Right` | Next unconfirmed proposal |
| `Ctrl+Left` | Previous unconfirmed proposal |
| `Ctrl+Shift+Del` | Reject all proposals in this frame |
| `Ctrl+U` | Flip the box by 180 degrees |
| `Ctrl+E` | Snap the active box onto the ground |
| `Ctrl+Shift+I` | Set the first keyframe for interpolation |
| `Ctrl+Shift+K` | Fill the frames between the keyframe and here |
| `Ctrl+Shift+E` | Carry the box forward through the next frames |
| `Ctrl+Shift+R` | Refit again after changing the refit settings |

### Help

| Keys | Action |
| --- | --- |
| `Ctrl+I` | Show dataset statistics |
| `Ctrl+Shift+S` | Show the activity log |
| `Ctrl+Shift+Q` | Check the labels of the whole folder for mistakes |
| `F1` | Show this shortcut list |

### View

| Keys | Action |
| --- | --- |
| `Ctrl+F` | Show only the points inside the active box |

<!-- END SHORTCUTS -->

Mouse:

| Gesture | Effect |
| --- | --- |
| drag on the box body | move the box |
| drag on a face you hover | resize that face (the resize is computed from the total movement, so it does not jitter) |
| drag anywhere else | rotate the point cloud (view) — unchanged from upstream |
| **`Ctrl` + left-drag** | **rotate the box** — upstream's gesture, kept free of the face resize |
| `Ctrl` + right-drag | move the box to the cursor |
| middle-drag | rotate the box around z |
| double-click | select a box |
| `Shift` + click | add/remove a box from the group selection (the status bar shows the group size) |

With more than one box selected, every movement, rotation, scaling, class, delete and flip command
acts on the whole group.

## Configuration

`config.ini` is read from the current working directory and merged over
`labelCloud/resources/default_config.ini`, so options added by an update never break an older file.
Beyond upstream's options:

```ini
[LABEL]
; save the current frame automatically every N seconds (0 disables it)
autosave_interval_seconds = 60

[USER_INTERFACE]
; system (follow the OS locale), en, or zh_CN
language = system
; carry a box into at most this many frames per Ctrl+Shift+E
propagate_max_frames = 5

[REFIT]
; Ctrl+R: how far to look beyond the box, what still counts as the same object,
; and when an empty stretch is trimmed off (all editable in the "Refit ..." dialog)
grow_margin = 0.6
max_link_distance = 1.2
max_empty_gap = 1.5
min_cluster_points = 3
refit_cross_section = False

[QUALITY]
; Ctrl+Shift+Q: how far a box may differ from the median size of its class (1.6x),
; when two boxes of one class count as duplicates, and how few points make a box
; a leftover (checked for the current frame only)
size_ratio = 1.6
duplicate_iou = 0.55
duplicate_distance = 0.35
min_points = 5

[ASSIST]
; folder of the offline pole/wire pre-annotation tool; leave empty to disable it
polewire_path = /path/to/tools/pole_wire_autolabel
classes = pole,wire
; pole parameters: recall (more boxes, fewer misses) or strict (fewer, cleaner)
pole_profile = recall

[SHORTCUTS]
; any command can be rebound, e.g.
; copy_box = Ctrl+Shift+C
```

## Companion offline tool

The pre-annotation used by `Ctrl+Shift+G` comes from a separate, self-contained tool
(`tools/pole_wire_autolabel`, pure geometry: ground model, canopy rejection for poles,
neighbourhood PCA for wires). This repository does not require it — without it the button reports
an error and every other feature keeps working.

Measured on 12 real frames of a 1292-frame dataset, the in-app path reproduces that tool's output
box-for-box (`pole` recall 0.92 / precision 0.79; `wire` recall 0.33 / precision 1.00 with a mean
matched BEV IoU of 0.74) at 0.03–1.18 s per frame, off the UI thread.

## Development

```bash
# regression checks (no pytest needed, each case runs in its own working directory)
.venv/bin/python tests/check_assist.py

# rebuild the Chinese translation catalogue after adding strings
.venv/bin/python tools/update_translations.py
```

`tests/check_assist.py` covers class-config compatibility, per-file label encodings and the
overwrite guard, language switching, the shortcut table, undo/coalescing, templates and locks, the
fitting engine on synthetic pole/wire scenes, the proposal queue, dataset statistics and save
failure handling.

Adding a translatable string: wrap it in `self.tr(...)` (or
`QCoreApplication.translate("labelCloud", ...)` outside a `QObject`), add the Chinese text to
`labelCloud/i18n/translations_zh_cn.py` and rerun `tools/update_translations.py`. Note that
`pylupdate5` ignores a `translate()` call whose source text has a **trailing comma**.

## Compatibility and limits

* Label files stay byte-compatible with upstream labelCloud (`centroid_abs`, degrees).
* `centroid_rel` (radians), 8-corner `vertices` and KITTI label folders are read correctly, and a
  folder in another encoding is not overwritten by accident.
* Rotations are only reported as degrees/radians when that can be *proven* from the values; an
  ambiguous file keeps the configured format instead of guessing.
* Fitting is geometric: it needs no trained model, and it does not try to be one. Dense scenes where
  a pole is wrapped in vegetation (where geometric recall drops) are the case a segmentation model
  would help with — point-wise segmentation is the natural next step.
* In-app pre-annotation is CPU-only, one frame at a time.
* Fit quality is guarded: a click that lands on a hedge, kerb or wall is **refused** instead of
  producing an oversized box, and a wire longer than 35 m is treated as a leaked region.
* Keyframe interpolation works in the sensor frame. The frames carry no ego pose, so a gap in which
  the vehicle moved a long way and turned sharply is the case where the interpolated boxes drift;
  the per-frame point check then skips those frames instead of writing boxes into empty space.
* Still missing compared to an ideal tool: rubber-band marquee selection (group editing itself is
  implemented, via `Shift`+click), and a persistent track id that survives a re-label (the passes
  recognise an object by position, not by identity).

## Credits and license

Forked from [ch-sa/labelCloud](https://github.com/ch-sa/labelCloud) 1.1.1 by Christoph Sager.
Licensed under the **GNU General Public License v3.0 or later** — see [LICENSE](LICENSE). Because
this is a derivative work, any redistribution must stay under the same license.
