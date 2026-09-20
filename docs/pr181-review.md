# PR #181 review — `ch-sa/labelCloud` "Feature: AI-assisted pre-labeling pipeline and UX enhancements"

Author: Yiming Yang (fork `YimingYang-MTU/labelCloud`, head commit `96865e624bc7bce551eaa18964f40e26e0d6f8b9`).
Purpose: extract the concrete design decisions worth reusing in our PyQt5 1.1.1 fork for **pole/wire** annotation
on 5–10 Hz LiDAR sequences, CPU only.

## How this was read (and what is verified)

| Source | Result |
| :--- | :--- |
| `https://patch-diff.githubusercontent.com/raw/ch-sa/labelCloud/pull/181.diff` | HTTP 200, 4 844 lines, 37 files, +3490/−549. Read in full, in pieces. Ends cleanly at `mkdocs.yml`; spot-checked against the head files below. |
| PR description (PR HTML page) | Read (`AI-Assisted Pre-Labeling`, `Spatial Copy-Paste Selection`, `Enhanced Viewport Controls`, `Allow editing of default object classes and corresponding default object size`). |
| Head files via `raw.githubusercontent.com/YimingYang-MTU/labelCloud/96865e6/...` | `config.ini`, `labelCloud/control/{controller,bbox_controller,label_manager,pcd_manager}.py`, `labelCloud/view/{viewer,gui,status_manager}.py`, `labelCloud/model/{bbox,point_cloud}.py`, `labelCloud/io/labels/{base,kitti}.py`, `labels/_classes.json`, `.gitignore`. |
| `https://api.github.com/repos/ch-sa/labelCloud/pulls/181` | **HTTP 403 rate limit on every attempt.** `mergeable` / `mergeable_state`, the exact base SHA and the review comments are therefore `UNVERIFIED`. Not needed for the design findings. |
| `https://codeload.github.com/.../tar.gz/<sha>` | Download stalled/corrupt (14 MB partial); abandoned in favour of per-file raw fetches. |

**Line numbers below are the files at PR head `96865e6`** (not the upstream master copy).

Headline structural finding: the PR is **PyQt5** (`from PyQt5 import QtGui, QtOpenGL` — `labelCloud/view/viewer.py:9`) and it is
**not rebased on our fork**; it is a full-file rewrite of the same files our own recent commits touch. Nothing here can be
merged; everything must be hand-ported.

---

## 1. `[LABEL_DEFAULTS]` per-class size table

**Schema** — a new section appended after `[LABEL]` in `config.ini` (head, lines 51–60):

```ini
propagate_labels = False
LABEL_FORMAT = kitti_untransformed  # Instead of "kitti" or "txt"

[LABEL_DEFAULTS]
car_length = 3.9
car_width = 1.6
car_height = 1.5
pedestrian_length = 0.8
pedestrian_width = 0.6
pedestrian_height = 1.7
cyclist_length = 1.8
cyclist_width = 0.7
cyclist_height = 1.7
```

Key shape: `<classname>_length` / `_width` / `_height`, plain floats, lowercase names, **no ids, no nested
per-class block**. `LABEL_FORMAT` on the line above is dead (see §6).

**Where it is read / applied** — two places, both in `labelCloud/control/bbox_controller.py`:

1. Creation, `add_bbox()` (lines 105–128). It does **not** use the box's incoming class at all:

```python
    def add_bbox(self, bbox: BBox) -> None:
        if isinstance(bbox, BBox):
            # Set default class to "car"
            bbox.set_classname("car")
            # Set default dimensions for car
            bbox.set_dimensions(
                config.getfloat("LABEL_DEFAULTS", "car_length"),
                config.getfloat("LABEL_DEFAULTS", "car_width"),
                config.getfloat("LABEL_DEFAULTS", "car_height"))
            # Get the current camera view yaw angle (z-rotation)
            view_direction = self.view.gl_widget.get_camera_yaw()
            bbox_rotation = (view_direction - 90) % 360
            bbox.set_z_rotation(bbox_rotation)
            ...
            self.view.current_class_dropdown.setCurrentText("car")
```

2. Class change, `set_classname()` (lines 175–200) — a hardcoded `if/elif` chain:

```python
        active_bbox.set_classname(new_class)
        if new_class == "car":
            active_bbox.set_dimensions(
                config.getfloat("LABEL_DEFAULTS", "car_length"), ...)
        elif new_class == "pedestrian":
            ...
        elif new_class == "cyclist":
            ...
```

**Class discrimination: by name string only.** Class *ids* (1/2/3 in `labels/_classes.json`) are never consulted, and
there is no fallback branch — any class that is not one of those three literals (i.e. `pole`, `wire`) keeps whatever size
it had, and `add_bbox` overwrites the user's configured default class with `"car"`. It also ignores `LabelConfig`'s
default class, so our `bboxes` created by the picking/drawing strategies would all become cars.

**Consequence visible in the PR itself:** because `update_all() → update_curr_class()` does
`setCurrentText(self.get_classname())`, which re-emits `currentTextChanged` → `set_classname()` → template resize, merely
*selecting* a box would resize it. The author patched around it in `set_active_bbox()` (lines 152–172) by saving and
restoring dimensions/rotations around `update_all()`:

```python
            current_dims = bbox.get_dimensions()
            current_rot = bbox.get_rotations()
            self.active_bbox_id = bbox_id
            self.update_all()
            bbox.set_dimensions(*current_dims)
            bbox.set_rotations(*current_rot)
```

The same guard is **missing** in `paste_bboxes_from_clipboard()` (line 604) and `delete_selected_bboxes()` (line 661),
which assign `active_bbox_id` directly and then call `update_all()` — so a paste can be silently resized to the class
template. This is the clearest design lesson in the PR: *apply a template at creation and at an explicit class change,
not inside the selection/dropdown signal path*.

**What we already have:** our fork derives templates from the class-definitions JSON
(`LabelConfig().get_default_dimensions(classname)`, `labelCloud/io/labels/config.py:268`, used by
`bbox_controller.apply_template()` line 514) and has a per-box `locked` flag (`labelCloud-src/labelCloud/model/bbox.py:44`). The PR's config.ini
table is the weaker version of what we have. If we ever add config.ini templates, make the lookup generic
(`f"{classname}_length"` with `fallback=None`) and keyed for `pole`/`wire`.

---

## 2. Spatial copy-paste across frames

**What is copied** — `copy_selected_bboxes()` (`bbox_controller.py:578–602`). One plain dict per selected box, only four fields:

```python
                bbox_data = {
                    'center': list(bbox.center),          # world/sensor coords, absolute
                    'dimensions': [bbox.length, bbox.width, bbox.height],
                    'rotation': [bbox.get_x_rotation(), bbox.get_y_rotation(), bbox.get_z_rotation()],
                    'classname': bbox.classname,
                }
```

No meta, no per-box lock (the PR has none), no source-frame index, no timestamp/odometry.

**Keys** — `Ctrl+C` / `Ctrl+V`, handled in `Controller.key_press_event` (`controller.py:352–363`):

```python
        if self.ctrl_pressed and a0.key() == Keys.Key_C:
            self.bbox_clipboard = self.bbox_controller.copy_selected_bboxes()
            ...
            return
        if self.ctrl_pressed and a0.key() == Keys.Key_V:
            if not self.bbox_clipboard:
                logging.warning("Clipboard is empty. Nothing to paste.")
                return
            self.bbox_controller.paste_bboxes_from_clipboard(self.bbox_clipboard)
```

The old plain-`C`/plain-`V` y-rotation bindings were deleted, so these combinations are free. Modifier state is tracked
manually (`self.ctrl_pressed` from key-press/key-release), not read from `a0.modifiers()`.

**Transport between frames** — an in-memory list on the *Controller*, not the Qt clipboard and not config
(`controller.py:46`):

```python
        self.bbox_clipboard = [] # To store copied bounding boxes
```

Because the Controller outlives frame changes, the buffer survives `R`/`F`/Next/Prev and custom frame jumps; it is not
persisted across restarts, and it is not visible to other applications.

**Paste target frame** — "whatever frame is on screen when `Ctrl+V` is pressed". There is no source-frame bookkeeping and
no target selection UI.

**Is the box transformed? No.** `paste_bboxes_from_clipboard()` (line 604) writes the same numbers back:

```python
            new_bbox = BBox(cx=center[0], cy=center[1], cz=center[2],
                            length=dimensions[0], width=dimensions[1], height=dimensions[2])
            new_bbox.set_dimensions(*bbox_data['dimensions'])
            new_bbox.set_x_rotation(bbox_data['rotation'][0])
            ...
            self.bboxes.append(new_bbox)
            new_bbox_ids.append(len(self.bboxes) - 1)
        self.selected_bbox_ids = set(new_bbox_ids)
        if new_bbox_ids:
            self.active_bbox_id = new_bbox_ids[0]
```

Paste only *adds*; it never deletes. The README's "duplicate objects across frames with maintained spatial logic" means
literally "same absolute coordinates, no ego-motion compensation". For a 5–10 Hz sequence with a moving platform that
puts the copy where the object *was* in the previous sensor frame — acceptable for a slow pole within one frame step,
wrong for a wire after a few steps. (Note also `paste → update_all → dropdown → set_classname` can resize the pasted
box; §1.)

Our fork already has single-box `Ctrl+C`/`Ctrl+V` on a `BBoxState` (`bbox_controller.py:457–481`, `keymap.py:110–111`);
the only genuinely new pieces here are (a) copying a *set* and (b) a shortcut to "copy here, move N frames, paste there".

---

## 3. Multi-object select

**Selection model** — a `set` of **list indices** on the bbox controller, separate from the single `active_bbox_id`
(`bbox_controller.py:76`):

```python
        self.selected_bbox_ids = set()
```

The label list widget stays single-row: `update_label_list()` (lines 502–517) rebuilds it and calls
`setCurrentRow(self.active_bbox_id)`. **There is no multi-select in the list widget**, no Ctrl+click, no Shift+click in
the list; `selected_bbox_ids` is only ever filled from the 3D viewport.

**Input (rubber band, Shift+left-drag):**

* start — `Controller.mouse_clicked` (`controller.py:237–246`): `if self.shift_pressed and left_click:` sets
  `is_marquee_selecting`, records `marquee_start_pos`, calls `view.gl_widget.start_marquee(...)` and returns.
* update — `mouse_move_event`: while `is_marquee_selecting and shift_pressed`, forwards to `update_marquee(pos)`;
  releasing Shift cancels (`key_release_event`).
* finish — `mouse_released` (`controller.py:301–317`) → `select_bboxes_in_rectangle(start, end)`
  (`bbox_controller.py:528–553`).
* hit test = **projected centre only**:

```python
                center_screen = self._project_3d_to_screen(center_3d)
                if (x1 <= center_screen[0] <= x2 and y1 <= center_screen[1] <= y2):
                    self.selected_bbox_ids.add(i)
```

with `_project_3d_to_screen` (line 555) wrapping `GLU.gluProject(x, y, z, modelview, projection, viewport)` and dividing
by `DEVICE_PIXEL_RATIO`. A long wire whose centre is outside the rubber band will not be selected even if most of it is
inside; conversely a small pole is only caught by its centre point.

* also: double-click a box = select exactly that one and clear the rest; double-click empty space or `Esc` = deselect all
  (`controller.py:203–215`, `bbox_controller.deselect_all_bboxes` line 641).

**Operations that then apply to the whole selection** (all iterate `selected_bbox_ids`):

| Operation | Key | Method |
| :--- | :--- | :--- |
| translate local X/Y, global Z | `W`/`S`/`A`/`D`/`Q`/`E` | `translate_group_along_x/y/z` (734–805) |
| rotate around Z | `Z` / `X` | `rotate_group_around_z` (807) |
| rotate 180° | `U` | `rotate_group_180_degrees` |
| scale length / width / height | `I`/`O`, `K`/`L`, `,`/`.` | `scale_group_along_{length,width,height}` |
| delete | `Del` | `delete_selected_bboxes` (661–676) |
| copy | `Ctrl+C` | `copy_selected_bboxes` |

**Not** applied to the whole selection: class change (the dropdown → `set_classname` touches the active box only), the
properties panel / z-dial (active box only), side dragging. Two behaviours to avoid copying verbatim:
`translate_group_along_x/y` deliberately use **local** axes when `len(selected_bbox_ids) == 1` and **global** axes when
more ("local for single, global for multiple"), and the WASD mapping is transposed relative to upstream — `W` now moves
along local +X ("right") and `D` along local +Y ("forward"), while upstream had `W`/`S` on Y and `A`/`D` on X
(`controller.py:391–399`).

Selection highlight: `BBox.SELETCED_COLOR: Color3f = Color3f(0, 0, 1) # green` (`model/bbox.py:25`, typo in the name and a
wrong comment) plus a new `draw_bbox(self, highlighted=False, selected=False)` parameter (line 162); `paintGL`
(`viewer.py:212–216`) passes `highlighted=is_active, selected=is_selected`, so the active box is green, other selected
boxes blue, and the active box is drawn twice.

**For us:** the separate `set[int]` alongside a single-row list is a cheap, low-risk model (no Qt selection model to
fight), but index-based ids are fragile: any `delete_bbox()` shifts them. Our fork should key selection on the `BBox`
objects (or a stable per-box uuid) and hit-test the projected bounding box, not just the centre.

---

## 4. One-press 180° orientation flip

**Binding:** plain `U` (`controller.py:436–437`):

```python
        elif a0.key() == Keys.Key_U:
            self.bbox_controller.rotate_group_180_degrees() # Changed to handle group
```

(`Key_U` is matched on the key code only, so Shift+U behaves the same; there is no `Ctrl`/`Alt` variant.)

**What it mutates** — z-rotation only, for the whole selection (`bbox_controller.py:822–830`):

```python
    def rotate_group_180_degrees(self) -> None:
        """Rotate all selected bboxes by 180 degrees around Z axis."""
        for bbox_id in self.selected_bbox_ids:
            if 0 <= bbox_id < len(self.bboxes):
                bbox = self.bboxes[bbox_id]
                bbox.set_z_rotation(bbox.get_z_rotation() + 180)
```

x/y rotations are untouched (consistent with the `z_rotation_only` default). An unused single-box twin,
`rotate_180_degrees()` (line 325), does the same for the active box. There is **no normalisation** (`% 360`), so repeated
presses accumulate (30 → 210 → 390 → 570 → 750 …). Checked against our export path: `KittiFormat.export_labels`
(`labelCloud-src/labelCloud/io/labels/kitti.py:171`) always applies `abs2rel_rotation()`, but that helper
(`io/labels/base.py:77–85`) subtracts `2π` **at most once**, so from the fourth flip onwards an out-of-range
`rotation_y` (> 2π) would be written. Normalise on flip (and/or make `abs2rel_rotation` use `% (2π)`) before adopting this.

This is the single best cost/benefit item in the PR for us: for a wire or a pole the only orientation that ever needs
correcting in practice is the 180° ambiguity of the heading, and it is one key that works on a marquee selection.

---

## 5. Viewport locking

There is **no lock flag and nothing is persisted**. "Viewport locking" in this PR = the camera moved out of the point
cloud into the GL widget, so that bbox editing no longer moves the scene (`viewer.py:71–80`):

```python
        # Camera control parameters
        self.camera_distance = 150.0
        self.camera_target = np.array([0, 0, 0])
        self.camera_pan = np.array([0.0, 0.0])
        self.camera_rot_x = 60   # Pitch (similar to working example)
        self.camera_rot_y = 0  # Yaw
        self.camera_rot_z = 0    # Not used for basic view control
```

applied per frame in `_apply_pointcloud_transformations()` (line 253) and driven by widget events: left-drag = orbit
(yaw/pitch), **middle-drag = pan** (`viewer.py:406`), wheel = zoom with adaptive step
(`zoom_ratio = np.clip(self.camera_distance / 100, 0.1, 1.0)`, `self.camera_distance = np.clip(... , -200, 150)`,
lines 449–456).

Cost of that refactor, all of which we would inherit:

* `PointCloud.set_gl_background()` was **deleted** and `pcd_manager.rotate_around_x/z`, `translate_along_x/y`, `zoom_into`
  were replaced by `pass` (diff `labelCloud/control/pcd_manager.py`), so the point cloud's own
  rotation/translation/perspective no longer affects the view.
* Therefore `P`/`Home` (`reset_transformations`, still bound in `key_press_event`) silently does nothing visible, and
  `KEEP_PERSPECTIVE` / `save_current_perspective()` / `Perspective.from_point_cloud()` become dead weight.
* `calculate_init_translation()` was replaced by a fixed camera offset, `base_distance = far_plane * 0.3` (diff
  `labelCloud/model/point_cloud.py`), so "fit the cloud on load" is gone.

The "switching between perspectives" half is **not implemented**:

* `viewer.py:82` defines `self.view_cycle = ["3D", "top", "front", "back", "left", "right"]` and
  `_apply_bbox_view(view_type)` (lines 264–334, quaternion-based, bbox-aligned front/back/top views with an
  `original_view_state` restore) exists — but **`_apply_bbox_view` has no caller** and there is **no `cycle_view_mode`
  method anywhere in `viewer.py`**, while the key binding calls it:

```python
        elif a0.key() == Keys.Key_V:
            self.pcd_manager.view.gl_widget.cycle_view_mode()      # controller.py:433
```

⇒ pressing `V` raises `AttributeError` (PyQt5 ≥ 5.5 promotes that to a fatal error). Any "viewport switching" claim for
this PR is `UNVERIFIED`/broken; the GIF in the README must come from one of the untracked `opengl_test_*.py` scripts.

For us: a widget-owned camera with middle-drag pan and distance-adaptive steps is a reasonable direction for 5–10 Hz
review, but do **not** stub out `pcd_manager` transforms without rewiring `P`/`Home` and perspective saving, and do not
take left-drag away from box manipulation (see §8).

---

## 6. AI pre-label import from OpenPCDet / MMDetection3D

**There is no importer code in this PR.** Grepping the entire 4 844-line diff for `openpcdet|mmdet|proposal|pkl|npy|
prelabel` yields hits only in the new README:

```
+### 🎯 AI-Assisted Pre-Labeling
+*Integrate pre-generated labels from AI models (e.g. openpcdet, mmdetection3d) to drastically reduce manual annotation time.*
```

No new module under `labelCloud/io/labels/`, no json/pkl/npy reader, no menu action, nothing in `label_manager.py` beyond
a changed `export_labels` signature. The README sentence is the entire feature.

What the PR actually ships is a **convention plus a format switch**:

1. `labels/_classes.json` changes the format and the classes (diff, head file identical):

```json
    "default": 1,
    "type": "object_detection",
    "format": "kitti_untransformed",
```

   with classes `unassigned(0)`, `car(1)`, `pedestrian(2)`, `cyclist(3)`.
2. It adds `example/labels/039498.txt` — an ordinary 15-line KITTI label file, e.g.
   `Car 0 0 0 0 0 0 0 1.66 1.65 4.13 43.13 -5.67 -1.08 0.54`.
3. `config.ini` gains `LABEL_FORMAT = kitti_untransformed  # Instead of "kitti" or "txt"` — **dead config**, no code
   reads it (the live format comes from the class-definitions JSON via `LabelConfig().format`).

So the pipeline is: run the detector offline → write its KITTI-format output as `<label_folder>/<pcd_stem>.txt` → the
*existing* `KittiFormat.import_labels()` picks it up when the frame is loaded. Our 1.1.1 fork already supports
`kitti_untransformed` (`labelCloud/definitions/label_formats/object_detection.py:9`,
`labelCloud/control/label_manager.py:23`), so nothing needs porting for the basic convention.

**Is import destructive?** Yes, in the ordinary labelCloud sense: labels on screen *are* the file's labels for that
frame (`next_pcd`/`prev_pcd`/`custom_pcd` → `set_bboxes(pcd_manager.get_labels_from_file())`). Hand corrections made in a
frame that was never saved are lost when you navigate away. This PR also *widens* an existing destructive path
(`controller.py:99–108`):

```python
            should_propagate = config.getboolean("LABEL", "propagate_labels")
            # Propagate labels if enabled (regardless of next frame's labels)
            if should_propagate:
                self.bbox_controller.set_bboxes(previous_bboxes)
                self.view.act_propagate_labels.setChecked(False)
                config.set("LABEL", "propagate_labels", "False")
```

Upstream only propagated into an *empty* frame (`if not self.bbox_controller.bboxes and config.getboolean(...)`); this
version overwrites the next frame's labels (including AI proposals) whenever the toggle is on, then silently unchecks the
toggle and writes `propagate_labels = False` into the config file.

Two practical gotchas for a real detector pipeline:

* class names are taken **verbatim** and never mapped: `bbox.set_classname(meta["type"])` (`io/labels/kitti.py`,
  `import_labels`). OpenPCDet/MMDet3D KITTI output is `Car`/`Pedestrian`/`Cyclist` (capitalised), our definitions are
  lowercase; an unknown name imports but renders in the fallback red (`LabelConfig.get_class_color` warns once and
  returns `#FF0000`). The PR's own example file contains both `Car` and `car` in the same file.
* `kitti_untransformed` needs no calibration file, which is what makes the convention work — but it also means the
  proposals must already be expressed in the point cloud's own frame, and nothing in the PR checks or converts that.

Verdict: reject as shipped; if we later want proposals for pole/wire, build an explicit, name-mapped, non-destructive
"import proposals into this frame" action on top of our existing untransformed KITTI reader.

---

## 7. `min_boundingbox_dimension` and other constants

**Confirmed** — `config.ini`, `[LABEL]` section, head line 49 (diff hunk `@@ -41,12 +42,26 @@`):

```diff
 ; minimum value for the length, width and height of a bounding box
-min_boundingbox_dimension = 0.01
+min_boundingbox_dimension = 0.1
```

Where it bites — `labelCloud/model/bbox.py:23`:

```python
class BBox(object):
    MIN_DIMENSION: float = config.getfloat("LABEL", "MIN_BOUNDINGBOX_DIMENSION")
```

* it is a **class attribute evaluated at import time** from the merged config (`default_config.ini` first, then
  `config.ini` in our fork's `ConfigManager.read_from_file`), so editing `config.ini` at runtime has no effect, and our
  packaged `default_config.ini:47 min_boundingbox_dimension = 0.01` would have to change too;
* it is enforced **only** in `BBox.change_side()` (lines 241–256) as the lower bound for a side drag
  (`if side == "right" and self.length + distance > BBox.MIN_DIMENSION:`), i.e. only for mouse-driven side pulling;
* `set_dimensions()` only rejects values `<= 0`, so a 0.03 m wire box can still exist if it comes from a file or a
  template — but the user cannot drag any side below 0.1 m.

For wires (typically 2–5 cm diameter) a 0.1 m floor makes the thin axis unreachable by dragging. Keep `0.01`, or make it
per-axis (a wire is thin in two axes, a pole in two axes as well).

Other constant changes in the same PR:

| Constant | Change | Note |
| :--- | :--- | :--- |
| `[POINTCLOUD] std_translation` | `0.03 → 0.1` (old line commented out) | read only by the now-stubbed `pcd_manager.translate_along_*` ⇒ dead with the new camera |
| `[POINTCLOUD] std_zoom` | `0.0025 → 0.025` | same: `zoom_into()` was stubbed to `pass` |
| `[LABEL] std_rotation_fine` | **new**, `0.5` | `rotate_around_z_fine()` (281) has no caller; `rotate_group_around_z(fine=True)` uses it |
| `[LABEL] std_rotation_coarse` | **new**, `4.0` | **never read by anything** — `rotate_group_around_z` is `config.getfloat("LABEL", "std_rotation_fine" if fine else "std_rotation")` and both are `0.5`, and `rotate_around_z_coarse()` (308) has no caller. So `Z` and `Ctrl+Z` both rotate 0.5° and the advertised coarse step does not exist. |
| `[LABEL] LABEL_FORMAT` | **new**, dead | see §6 |

---

## 8. Other UX changes worth stealing (and regressions not to copy)

### Worth stealing

* **Autosave mirror + close prompt.** `BaseLabelFormat.save_label_to_file()` (`labelCloud/io/labels/base.py:48–90`)
  writes every save into `<label_folder>/autosave/<stem>_autosave<ext>` and only touches the real file
  `if force_overwrite:`; `GUI.closeEvent` (`view/gui.py:495–514`) asks
  `"Unsaved Changes" / "Save changes?"` with Save/Discard/Cancel and always writes a backup before closing. The *backup
  file* and the *prompt* are worth having — the default (`force_overwrite=False`) is not (see below).
* **Status-bar cursor XYZ + camera angles** (`view/status_manager.py`, `set_coordinates` / `set_camera_rotation`), fed on
  every mouse move from `get_world_coords()`; cheap, and genuinely useful when checking 5–10 Hz sequences.
* **2D overlay technique for rubber bands** — `GLWidget._draw_2d_overlay()` (`viewer.py:112–154`): push projection,
  `GLU.gluOrtho2D(0, self.width(), self.height(), 0)`, `glDisable(GL_DEPTH_TEST)`, draw semi-transparent quad + border,
  restore. Reusable for any in-viewport HUD.
* **Double-click semantics**: double-click a box = select exactly it; double-click empty space or `Esc` = deselect all.
* **New box aligned to the camera yaw** (`bbox_controller.add_bbox`, `get_camera_yaw` + `(view_direction - 90) % 360`):
  a box placed in front of the viewer already faces the right way. Keep the trick; drop the hardcoded `"car"`.
* **Adaptive mouse speeds** based on camera distance (`viewer.py:397–410`, `449–456`) — relevant when a pole at 10 m and
  a wire at 60 m are annotated in the same session.
* **`Context.SHIFT_PRESSED = 4`** (`definitions/context.py`) for the "Shift pressed" status hint while marquee-selecting.
* **`force_overwrite` / `backup` plumbed as one seam** through `LabelManager.export_labels` → `BaseLabelFormat.
  export_labels` → `save_label_to_file`; a clean place to express "explicit save" vs "autosave copy".

### Do not copy — regressions found in the PR

* **The Save button no longer saves the label file.** `view/gui.py:349` is `self.button_save_label.clicked.connect(
  self.controller.save)`, and `next_pcd`/`prev_pcd`/`custom_pcd` call `self.save()`; the new signature is
  `def save(self, force_overwrite=False, backup=True)` (`controller.py:134`) and `save_label_to_file` writes the real
  file only `if force_overwrite:` (`base.py:73`). Net effect: **the toolbar Save button and every frame change write only
  `labels/autosave/<stem>_autosave.txt`; the real label file is updated only by `Ctrl+S`**, which passes
  `force_overwrite=True`. Any user who trusts the Save button loses work.
* **Dirty tracking by object identity.** `saved_state = {id(bbox) for bbox in self.bboxes}` /
  `has_unsaved_changes()` (`bbox_controller.py:88–95`) detects only *new* box objects. Editing a loaded box mutates the
  same object, so the id set is unchanged and `has_unsaved_changes()` returns **False after a real edit**; loading a frame
  creates new objects, so it returns True after a plain load. Both directions are wrong — do not build on it.
* **Mouse box manipulation was removed.** `controller.mouse_move_event` lost the whole `Ctrl+left = rotate bbox`,
  `Ctrl+right = translate bbox` block, and `mouse_scroll_event` lost `side_mode` side-scaling; `rotate_with_mouse`,
  `set_center`, `change_side` remain in the model/controller with **no caller**. For our roadmap item "mouse dragging"
  this PR is a negative example: Shift+left-drag is spent on the marquee and plain left-drag is orbit; dragging boxes
  should be additive in our fork (e.g. plain left-drag on a box to move it, Ctrl+drag to rotate, keep scroll side-pulling).
* **Transposed WASD mapping** (`controller.py:391–399`): `W → translate_group_along_x()` (local "right"),
  `D → translate_group_along_y(forward=True)` (local "forward"); upstream had `W`/`S` on Y and `A`/`D` on X. Also
  `translate_along_x/y` keep a `distance *= -2` factor for `left`/`forward` (dead code, but a latent bug).
* **Debug noise on hot paths**: `print()` in `mouse_move_event`, in every selection/paste (`print(f"Selected bbox {i}")`),
  `logging.debug(traceback.format_stack())` on **every** `set_classname` call (`bbox_controller.py:176`),
  `print("Controller set in GLWidget")` at startup (`viewer.py:99–106`).
* **Seven new scratch scripts** `labelCloud/view/opengl_test_*.py` (~2 500 of the 3 490 added lines) that the app never
  imports, plus `docs/tutorials.md` deleted and removed from `mkdocs.yml`.
* **`.gitignore` replaced by a generic Node/Python template** (51 lines, patterns `*.class`, `*.py[cod]`, `*.log`,
  `*.exe`, `*.mp4` …). It no longer ignores `*.ply`, `*.pcd`, `*.bin`, `*.json` (the old file had those plus `!`
  exceptions for the shipped examples), so point clouds and label files in the working tree become committable —
  presumably done to be able to commit `example/velodyne/039498.ply`.
* **Example/config content overwritten with the author's setup**: `pointcloud_folder = example/velodyne/`,
  `label_folder = example/labels/`, classes car/pedestrian/cyclist, and `labels/039498.json` contains an absolute
  developer path (`"path": "/home/yiming/wads/data/11/velodyne_dsor_ply/039498_dsor.ply"`).
* **Dead code/config to leave behind**: `LABEL_FORMAT`, `alt_pressed` (set and cleared, never read),
  `std_rotation_coarse`, `rotate_around_z_fine/coarse`, `rotate_180_degrees`, `translate_along_*`,
  `translate_group_along_separate_*`, `view_cycle`/`current_view_index`/`_apply_bbox_view`, and the commented-out
  `closeEvent`/`show_save_prompt` block in `gui.py`.

---

## 9. Mergeability assessment

**Files touched (37).** Real code: `labelCloud/control/bbox_controller.py`, `control/controller.py`,
`control/label_manager.py`, `control/pcd_manager.py`, `definitions/context.py`, `io/labels/base.py`,
`io/labels/kitti.py`, `model/bbox.py`, `model/point_cloud.py`, `view/gui.py`, `view/status_manager.py`,
`view/viewer.py`. Non-code: `config.ini`, `labels/_classes.json`, `README.md`, `docs/tutorials.md` (deleted),
`mkdocs.yml`, `docs/assets/extra.css`, `.gitignore`, 6 GIFs under `assets/`, `example/velodyne/039498.ply`,
`example/labels/039498.txt`, `labels/039498.json`, and the 7 new `labelCloud/view/opengl_test_*.py` scratch scripts.

**Qt binding: still PyQt5.** Verified in the head files (`viewer.py:9` `from PyQt5 import QtGui, QtOpenGL`, plus
`from PyQt5.QtGui import QQuaternion, QVector3D`, `from PyQt5.QtCore import Qt, QPoint, QEvent`;
`bbox_controller.py` adds `from PyQt5 import QtGui`, `from PyQt5.QtCore import QPoint`). So there is **no binding-level
blocker** for our PyQt5 fork — the PR is a PyQt5-era branch, not the current PySide6 master. The exact base SHA could not
be read (GitHub API rate-limited) → `UNVERIFIED`, but the base is clearly pre-PySide6 and pre-our-fork.

**A merge is not possible; port by hand.** Concretely, the PR:

* rewrites the event flow — `GLWidget` now owns `mousePressEvent`/`mouseMoveEvent`/`mouseReleaseEvent`/`wheelEvent` and
  forwards them into `Controller.mouse_clicked`/`mouse_move_event`/`mouse_released`, with a new `GLWidget.set_controller()`
  handshake from `Controller.startup`; our fork's `controller.py`/`viewer.py` are exactly the files our own feature
  commits touch, so every hunk conflicts;
* replaces the camera model (deletes `PointCloud.set_gl_background`, stubs the `pcd_manager` manipulators, changes
  `calculate_init_translation`, adds `get_scene_size`/`get_current_distance`) and thereby breaks `P`/`Home` and
  `KEEP_PERSPECTIVE`;
* changes signatures used elsewhere: `BBox.draw_bbox(highlighted, selected)`, `LabelManager.export_labels(...,
  force_overwrite, backup)`, `BaseLabelFormat.save_label_to_file(..., force_overwrite, backup)`,
  `PointCloudManger.save_labels_into_file(..., force_overwrite, backup)`, `Controller.save(force_overwrite, backup)`,
  `BoundingBoxController(controller)` (constructor now takes the `Controller`);
* leaves `Key_V` bound to a method that does not exist (§5) and its "coarse" rotation and view presets unwired (§7).

**What a hand-port into our 1.1.1 tree would look like** (our tree already contains `keymap.py`, `undo.py`,
 `copy_current_bbox`/`paste_bbox`, `apply_template`, `toggle_dimension_lock` from commit `952c143`, so several items
 below are already covered and only need extending):

1. selection state on the bbox controller keyed by box object + `select_bboxes_in_rectangle(start, end)` using
   `GLU.gluProject` of the box **corners**, ~60 lines, plus `_draw_2d_overlay`-style marquee drawing, ~40 lines;
2. Shift+left-drag wiring in our own keymap/event path (our fork doesn't use `GLWidget` as the event owner, so this must be
   adapted rather than copied), ~40 lines;
3. group variants of the existing undo-wrapped translate/rotate/scale, ~100 lines (each wrapped in our `undoable`
   decorator, which the PR has no equivalent of);
4. `rotate_180_degrees` for the selection on a free key with `% 360`, ~10 lines;
5. multi-box clipboard: extend `BBoxState` to a list, ~40 lines;
6. status-bar cursor + camera readout, ~30 lines;
7. autosave mirror on close plus a Save/Discard/Cancel prompt, ~40 lines — with `force_overwrite=True` as the default for
   explicit saves.

Everything else in this PR (camera rewrite, AI convention, config tables, `min_boundingbox_dimension = 0.1`, scratch
scripts) should be left out.

---

## Adopt / Reject

| Feature (PR #181) | Verdict | Reason for our pole/wire fork |
| :--- | :--- | :--- |
| `[LABEL_DEFAULTS]` table in `config.ini`, read by hardcoded `car/pedestrian/cyclist` if/elif | **adopt with changes** | The *idea* (size template per class) is right, but name-keyed literals are useless for `pole`/`wire`; use a generic `<class>_length/width/height` lookup or our existing `LabelConfig().get_default_dimensions()`. |
| Template applied on box creation, box auto-rotated to camera yaw | **adopt with changes** | Keep the yaw alignment; drop `bbox.set_classname("car")` and the forced car size — apply the *currently selected* class template. |
| Template re-applied on class change, guarded by save/restore in `set_active_bbox` | **adopt with changes** | Reapply on class change only, honour our per-box `locked` flag, and fix the signal at the source instead of the save/restore hack (missing in the paste path). |
| Multi-box copy/paste with `Ctrl+C`/`Ctrl+V` into an in-memory list on the Controller | **adopt with changes** | Extend our existing single-box `BBoxState` clipboard to a set; keep it on the Controller so it survives frame changes. |
| Paste target frame = "whatever is on screen" | **adopt as-is** | Zero extra UI, and it matches how wire/pole work is done frame-by-frame. |
| Paste carries absolute coordinates, no ego-motion transform | **reject** | On a moving 5–10 Hz platform the copy lands where the object was in the previous frame; without odometry this cannot be fixed properly, so treat paste as same-frame/two-frame only (or add a manual XY offset later). |
| Marquee multi-select: Shift+left-drag, selection stored as a `set` of indices, `gluProject` hit test | **adopt with changes** | Good, cheap model (list stays single-row), but key selection by box object, hit-test the projected box (a wire's centre escapes a small marquee), and keep click-to-select instead of moving selection to double-click. |
| Group operations on the selection (translate/rotate/scale/delete/copy/180°) | **adopt as-is** | Exactly what repetitive pole/wire work needs; each must be wrapped in our undo history. |
| `translate_group_along_x/y` local-when-single / global-when-multiple + transposed WASD | **reject** | Inconsistent axes and a mapping change vs upstream; pick one frame (local) and keep our existing keys. |
| One-press 180° flip on `U`, z-rotation only, whole selection | **adopt as-is** | The single most useful item here: one key fixes heading ambiguity on a pole or a whole run of wire boxes; add `% 360` normalisation and undo. |
| Camera owned by the widget, adaptive zoom/rotate speed, clamped distance, middle-drag pan | **adopt with changes** | The camera refactor is a good direction but must be done without breaking `P`/`Home` reset, perspective saving, or point-cloud fitting — the PR breaks all three. |
| "Viewport locking" as an explicit feature | **reject** | No lock exists; nothing is stored, and the perspective-cycling half is dead code (`cycle_view_mode` missing ⇒ `V` raises `AttributeError`). Reimplement top/front views deliberately if we want them for poles. |
| AI pre-label import from OpenPCDet / MMDetection3D | **reject** | No implementation at all — only a README claim, a `kitti_untransformed` format switch and "drop KITTI txt in the label folder" (which our fork already reads). An OpenPCDet txt with capitalised class names would also import as unknown red classes. |
| `next_pcd` propagation that overwrites a non-empty next frame | **reject** | It would wipe AI proposals or hand labels on the following frame; upstream only propagated into empty frames. |
| `min_boundingbox_dimension = 0.1` | **reject** | A 10 cm floor on `BBox.change_side` makes a 2–5 cm wire unrepresentable by side-dragging; keep `0.01` (or per-axis minima). |
| `std_rotation_fine` / `std_rotation_coarse` config keys | **adopt with changes** | Fine/coarse steps are on our roadmap, but the PR leaves coarse dead (`Z` and `Ctrl+Z` both 0.5°); wire it through our keymap (we already have Shift ×10 / Alt ×0.1 multipliers). |
| Autosave mirror folder + Save/Discard/Cancel close prompt | **adopt with changes** | Take the backup file and the prompt; reject `force_overwrite=False` as the default — in the PR the Save button and frame navigation never write the real label file. |
| Dirty tracking via `{id(bbox)}` sets | **reject** | Misses in-place edits and reports a load as "unsaved"; use an explicit dirty flag / snapshot hash (our `undo.py` snapshots already give us this). |
| Status-bar cursor XYZ + camera pitch/yaw | **adopt as-is** | Cheap, useful, no coupling. |
| 2D ortho overlay helper for rubber bands | **adopt as-is** | Small self-contained technique for any in-viewport marquee/HUD. |
| Double-click = select one, double-click empty/`Esc` = deselect all | **adopt with changes** | Keep it as an addition; the PR removed plain-click selection, which is a regression. |
| Removal of Ctrl+drag box rotate/translate and scroll-based side pulling | **reject** | Directly opposed to our next roadmap item (mouse dragging); implement dragging additively instead. |
| `.gitignore` rewrite, `docs/tutorials.md` deletion, author-local example paths, 7 `opengl_test_*.py` scratch scripts, debug `print()`s | **reject** | Repo-hygiene regressions with no annotation value. |
