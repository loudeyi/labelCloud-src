# labelCloud — pole & wire assist fork

> A fork of [labelCloud](https://github.com/ch-sa/labelCloud) (GPL-3.0) turned into a practical
> annotation tool for **power lines (`wire`)** and **utility poles (`pole`)** in LiDAR sequences.
> It keeps labelCloud's file format and adds the things that actually save time when the same pole
> shows up in a hundred consecutive frames.

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.8-blue.svg)
![Platform](https://img.shields.io/badge/platform-linux-lightgrey.svg)

**English** · [简体中文](README_zh_cn.md) · [Changelog](CHANGELOG.md)

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

Proposals are drawn **dashed in orange** and never look like confirmed labels. Accepting one is a
single keystroke; rejecting is one keystroke for the whole batch.

## Workflow and safety features

| Feature | Where | What it does |
| --- | --- | --- |
| **Pointer mode** | button next to *Pick/Span/Fit*, or `Esc` | Leaves every drawing mode so the mouse only navigates the cloud again. The drawing buttons also toggle off when clicked twice, and **dragging never creates a box** — a fit only happens on a real click (≤ 5 px of movement) |
| **Next-frame class** | "New boxes in next frames" combo | Pins the class every new box gets, frame after frame: one pass can label poles, the next pass wires, without re-picking the class in each frame |
| **Save indicator** | right of the status bar | `✓ saved 13:38:09  labels_lc/frame.json`, `● unsaved changes`, or a red `✗ save FAILED`. The tooltip shows the full path |
| **Save log** | click the indicator, `Ctrl+Shift+S`, or *File → Save Log* | Lists the recent writes with time, result and exact path |
| **Autosave** | every 60 s (`LABEL/autosave_interval_seconds`) | Writes only when something was actually edited. A frame you merely browsed past is **not written at all** — press `Ctrl+S` to record it as "checked, and it is empty" |
| **Group editing** | `Shift`+click boxes | Move/rotate/scale/class/delete/flip act on the whole group |
| **Undo/redo** | `Ctrl+Z` / `Ctrl+Shift+Z` | One step per gesture: a whole drag, or a burst of key presses, undoes as a single action |
| **Dimension lock + templates** | `Ctrl+L` / `Ctrl+T` | Protects a fitted size; templates fix the pole cross-section and the wire section |

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

### Help

| Keys | Action |
| --- | --- |
| `Ctrl+I` | Show dataset statistics |
| `Ctrl+Shift+S` | Show the save log |
| `F1` | Show this shortcut list |

### View

| Keys | Action |
| --- | --- |
| `Ctrl+F` | Show only the points inside the active box |

<!-- END SHORTCUTS -->

Mouse: drag the box body to move it, drag a hovered face to resize it, middle-drag to rotate
around z, double-click a box to select it, **`Shift`+click to add or remove a box from the group
selection** (the status bar shows the group size). With more than one box selected, every movement,
rotation, scaling, class, delete and flip command acts on the whole group. `Ctrl` + mouse keeps the
original labelCloud behaviour.

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
* Still missing compared to an ideal tool: rubber-band marquee selection (group editing itself is
  implemented, via `Shift`+click) and keyframe interpolation across frames (designed, not yet
  implemented).

## Credits and license

Forked from [ch-sa/labelCloud](https://github.com/ch-sa/labelCloud) 1.1.1 by Christoph Sager.
Licensed under the **GNU General Public License v3.0 or later** — see [LICENSE](LICENSE). Because
this is a derivative work, any redistribution must stay under the same license.
