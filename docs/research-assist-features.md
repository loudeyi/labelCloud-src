# Semi-automatic annotation features for a labelCloud fork — wires & poles

Scope: what assistive annotation features exist in comparable open-source 3D point-cloud
annotation tools, and what is realistically portable into a **PyQt5 + OpenGL + Open3D
labelCloud fork**. Target task: 3D boxes on **power lines (wires)** and **utility poles** in a
~0.5 s-interval LiDAR sequence where the same pole appears in dozens of consecutive frames.

Sources were read directly where the artefacts already exist on this machine:

- labelCloud **1.1.1** installed at `labelcloud-hzh/lib/python3.8/site-packages/labelCloud`
  (PyPI latest = 1.1.1, released 2024-08-18 — [PyPI JSON](https://pypi.org/pypi/labelCloud/json)).
- **SUSTechPOINTS** clone at `/home/tyy/hzh/SUSTechPOINTS`, HEAD `50fa188`
  ([upstream](https://github.com/naurril/SUSTechPOINTS)).
- **LitePT** clone at `/home/tyy/DSH-WS/LitePT` ([upstream](https://github.com/prs-eth/LitePT)).

---

## Bottom line

The highest-leverage move is **not** a trained model — it is stealing SUSTechPOINTS' *keyframe +
constant-velocity interpolation* workflow, which is exactly designed for the "sparse keyframes,
interpolate the rest" regime and is documented as the intended labelling method for a 20 s scene
sampled at 2 Hz ([`README_guide.md` L116–122](https://github.com/naurril/SUSTechPOINTS/blob/master/README_guide.md)).
That workflow is ~200 lines of numpy in its core (linear step between two human-confirmed boxes,
plus an EMA-velocity extrapolator for the tail), needs no model, and maps cleanly onto labelCloud's
existing `BBox` list + `propagate_labels` hook — which today is only a crude whole-frame copy
(`controller.py` L67–77). **One caveat that could beat it outright:** if per-frame poses exist, rigid
propagation (`B_f′ = T_f′⁻¹·T_f·B_f`) is *exact* for static infrastructure rather than an
approximation, and no open-source LiDAR annotator currently does it — so check for poses before
building the interpolator. Second-highest is **per-class dimension templates + copy/paste of a box
between frames**: labelCloud has neither (class JSON carries only `name`/`id`/`color`), and both are
S-sized changes. An upstream PR that implements a large chunk of this already exists
([ch-sa/labelCloud#181](https://github.com/ch-sa/labelCloud/pull/181), open, unmerged) and should be
read before writing any code. A learned path is only realistic as **point-wise semantic
segmentation** (LitePT-style) producing pole/wire point masks that are then box-fitted
geometrically — pretrained KITTI/Waymo car detectors will not produce poles or wires.

---

## What the baseline (labelCloud 1.1.1) already has

Verified against the installed source, not just the README. Links point at `master` where the file
still exists there; the `propagate_labels` logic was confirmed byte-for-byte identical on master.

| Capability | Reality in 1.1.1 | Source |
|---|---|---|
| Box parameterisation | centre `(x,y,z)` + `length,width,height` + **three Euler rotations**; `z_rotation_only = True` by default | `resources/default_config.ini`, `model/bbox.py` |
| Picking mode | click front-top edge, mouse-wheel sets z-rotation; dimensions come from **global** `std_boundingbox_*` | `labeling_strategies/picking.py` |
| Spanning mode | 4 vertices define length/width/height | `labeling_strategies/spanning.py` |
| Ground alignment | "Align" mode: click 3 points on the ground plane, cloud is re-aligned | `control/alignmode.py` |
| Semantic seg. | bbox-based: *Assign* paints all points inside the box with the class → `*.bin` | [README](https://github.com/ch-sa/labelCloud/blob/master/README.md) |
| 2D camera image | button opens the related image in a **separate window**; no projection, no calib-driven box overlay | `view/gui.py` `show_2d_image`; [PR #44](https://github.com/ch-sa/labelCloud/pull/44) |
| `propagate_labels` | **copies the previous frame's whole bbox list into the next frame, only if that frame has no labels yet**; no IDs, no motion compensation, no interpolation | `control/controller.py` L67–77 |
| Per-class dimensions | **absent** — `_classes.json` entries are `{name,id,color}` only | `resources/default_classes.json` |
| Copy/paste a box | **absent** | `control/controller.py` key handler |
| Tracking / interpolation | **absent** | upstream [shortcut table](https://github.com/ch-sa/labelCloud/blob/master/README.md) |

Full shortcut set (upstream README + `controller.py` L246–355): `WASD` translate, `QE` up/down,
`Z/X` `C/V` `B/N` rotate z/y/x, `I/O` length, `K/L` width, `,/.` height, side-hover + wheel resize,
`R/←` `F/→` prev/next frame, `T/↑` `G/↓` prev/next box, `Y/H` class ±1, `1`–`9` select box,
`Ctrl+S` save, `Del` delete, `P/Home` reset view, `Esc` cancel.

**Upstream PR to read first:** [ch-sa/labelCloud#181 — "Feature: AI-assisted pre-labeling pipeline
and UX enhancements"](https://github.com/ch-sa/labelCloud/pull/181) (opened 2026-01-30, still open).
Its README diff advertises: AI pre-label import from OpenPCDet/MMDetection3D, multi-object select,
**spatial copy-paste across frames**, viewport locking, one-press 180° orientation flip, and a
`[LABEL_DEFAULTS]` config section giving **per-class default length/width/height**
(`car_*`, `pedestrian_*`, `cyclist_*`). Author: Yiming Yang (Michigan Tech). Caveats visible in the
diff: the per-class table is hardcoded to those three road classes, and it raises
`min_boundingbox_dimension` from `0.01` to `0.1` — which would make a thin wire unrepresentable.
Its patches still import `from PyQt5 import QtGui`, so it was branched from a PyQt5-era commit and is
**not guaranteed to apply to current master** (see the toolkit trap below).

---

## Candidate features

Effort: **S** ≈ under a day in the existing architecture, **M** ≈ days, **L** ≈ a week+ / new subsystem.
Value is for *this* task (thin elongated wires + tall thin poles, temporally dense sequence).

| Feature | Tool(s) that do it | Mechanism (how it works) | Effort | Value | Source |
|---|---|---|---|---|---|
| Linear interpolation between two boxes of the same object | SUSTechPOINTS | Find the two non-null (human) annotations bracketing a gap; `step = (ann[end]-ann[start])/(end-start)`; fill `ann[i] = ann[i-1] + step`; **recompute `step` from the far keyframe after every fill** so later auto-corrections propagate | **M** | **High** | [`public/js/ml.js` L312–380](https://github.com/naurril/SUSTechPOINTS/blob/master/public/js/ml.js) |
| Constant-velocity extrapolation past the last keyframe | SUSTechPOINTS | `MaFilter`: EMA velocity `v = decay·(x−x_prev) + (1−decay)·v`, `decay = 0.5`; `predict() = [x+v for the 6 pose components] + [x for the 3 scale components]` — **dimensions are frozen**, only pose is extrapolated | **S** | **High** | [`public/js/ml.js` L524–558](https://github.com/naurril/SUSTechPOINTS/blob/master/public/js/ml.js) |
| Interpolation done in **global/world** coordinates | SUSTechPOINTS | Annotations are converted to global vectors before interpolating and back after, so ego-motion does not have to be handled by the interpolation itself | **M** | **High** | [`public/js/box_op.js` L676–710](https://github.com/naurril/SUSTechPOINTS/blob/master/public/js/box_op.js) |
| Ego-pose / world-coordinate mode | SUSTechPOINTS | Per-frame ego pose fetched from `/load_ego_pose`; UI can display in LiDAR frame or GPS/UTM world frame | **L** | Med (High if poses exist) | [`public/js/ego_pose.js`](https://github.com/naurril/SUSTechPOINTS/blob/master/public/js/ego_pose.js), [`README_guide.md` L134–138](https://github.com/naurril/SUSTechPOINTS/blob/master/README_guide.md) |
| Copy/paste a box to an adjacent frame | SUSTechPOINTS | Manual copy/paste migrates a box between frames, keeping its size; recommended to label one frame, copy to the neighbour, adjust both, then batch-annotate | **S** | **High** | [`README_guide.md` L118, L154](https://github.com/naurril/SUSTechPOINTS/blob/master/README_guide.md) |
| Multi-object select + **batch edit across frames** | SUSTechPOINTS | A mode showing the same object over many frames; click / ctrl-click / shift-click / drag to select boxes, right-click menu → interpolate, auto, delete, finalize, fit | **M** | **High** | [`README_guide.md` L172–200](https://github.com/naurril/SUSTechPOINTS/blob/master/README_guide.md) |
| **`finalize`** — mark a human-confirmed box | SUSTechPOINTS | Finalized boxes become the anchor inputs for all auto algorithms and are never overwritten by them; more finalized boxes ⇒ better auto results | **S** | **High** | [`README_guide.md` L119, L192](https://github.com/naurril/SUSTechPOINTS/blob/master/README_guide.md) |
| Per-class **dimension templates** (drag centre only) | SUSTechPOINTS (size is copied/frozen), PR #181 | Fix l/w/h per class; annotator sets only centre + yaw. SUSTechPOINTS keeps size fixed while dragging and always keeps size during interpolate/auto | **S** | **High** | [`README_guide.md` L93, L153, L155](https://github.com/naurril/SUSTechPOINTS/blob/master/README_guide.md); [PR #181 diff](https://github.com/ch-sa/labelCloud/pull/181) |
| **Click-to-fit box** (fit to nearest points) | SUSTechPOINTS | Double-click a box edge → snap that face to the nearest interior point; `Ctrl`+drag → move then auto-shrink to fit | **M** | **High** | [`doc/shortcuts_cn.md`](https://github.com/naurril/SUSTechPOINTS/blob/master/doc/shortcuts_cn.md), [`README_guide.md` L217–221](https://github.com/naurril/SUSTechPOINTS/blob/master/README_guide.md) |
| One-click **fit position / size / rotation**, and "I am lucky" | SUSTechPOINTS | Separate operations: `scale` (refit size), `move` (refit position), `rotate` (refit yaw, size frozen), and a combined "I am lucky" | **M** | **High** | [`README_guide.md` L223–226](https://github.com/naurril/SUSTechPOINTS/blob/master/README_guide.md) |
| Rotated-AABB box fit from points + a given yaw | SUSTechPOINTS (model-free part of pre-annotate) | Rotate the object's points by the yaw, take axis-aligned min/max in the rotated frame ⇒ dims + centre; `pmin[2] -= 0.2` ground offset | **S** | **High** | [`algos/pre_annotate.py` L195–221](https://github.com/naurril/SUSTechPOINTS/blob/master/algos/pre_annotate.py) |
| Orientation from **motion direction** across frames | SUSTechPOINTS | Yaw taken from the object's displacement between frames; needs ≥1 correctly positioned neighbouring frame | **S** | **High** | [`README_guide.md` L147, L227–230](https://github.com/naurril/SUSTechPOINTS/blob/master/README_guide.md) |
| Class/attribute **sync across all frames** | SUSTechPOINTS | Fix the class once, then "Sync object type & attr" propagates it over the object's whole track | **S** | Med | [`README_guide.md` L166–170](https://github.com/naurril/SUSTechPOINTS/blob/master/README_guide.md) |
| Trajectory view | SUSTechPOINTS | Plots the object's box centres in world coordinates; double-click a point to jump to that frame with the box selected | **M** | Med | [`README_guide.md` L196](https://github.com/naurril/SUSTechPOINTS/blob/master/README_guide.md); `algos/trajectory.py` |
| 180° orientation flip (one key) | PR #181 | One-press yaw += 180° for fast heading correction | **S** | Med | [PR #181](https://github.com/ch-sa/labelCloud/pull/181) |
| Model-prediction **import as pre-labels** | PR #181 | Import OpenPCDet / MMDetection3D proposal files and edit them as ordinary boxes | **S** (path) / **L** (the model) | Med | [PR #181](https://github.com/ch-sa/labelCloud/pull/181) |
| Crop cloud to box ("Save points inside as") | labelCloud 1.1.1 | Already present — `act_crop_pointcloud_inside` | — | Med | `view/gui.py` L208 |
| Right-click context menu / toolbox | SUSTechPOINTS | All fit/auto/finalize operations exposed on a context menu over the box and as BEV toolbox buttons | **S** | Med | [`doc/bev-toolbox.png`](https://github.com/naurril/SUSTechPOINTS/tree/master/doc), `README_guide.md` L180–197 |
| **Click-to-fit from picked points** | Open3D (primitive) | `OrientedBoundingBox.create_from_points(points)` — a **static**, no `PointCloud` needed; also `create_from_points_minimal` and `OrientedBoundingEllipsoid.create_from_points` | **S** | **High** | [pybind source](https://cdn.jsdelivr.net/gh/isl-org/Open3D@main/cpp/pybind/geometry/boundingvolume.cpp) |
| Grow → refit loop | Open3D (primitive) | `obb.get_point_indices_within_bounding_box(points)` → refit on the grown set; iterate | **S** | **High** | [pybind source](https://cdn.jsdelivr.net/gh/isl-org/Open3D@main/cpp/pybind/geometry/boundingvolume.cpp) |
| **Verticality / covariance features for pole candidates** | PDAL (implementable in numpy) | Per-point neighbourhood covariance → `eigh` → linearity, planarity, scattering; **verticality is highest for thin vertical strips** | **M** | **High** | [`filters.covariancefeatures`](https://pdal.io/en/stable/stages/filters.covariancefeatures.html); Demantké et al. 2011; Guinard & Landrieu 2017 |
| Ground removal for spinning LiDAR | Patchwork++, PDAL | Adaptive ground likelihood estimation + region-wise plane fitting; beats one global RANSAC plane on multi-level ground | **M** | **High** | [arXiv:2207.11919](https://arxiv.org/abs/2207.11919), [PDAL filters](https://pdal.io/en/stable/stages/filters.html) |
| Cylinder fit for the pole shaft | PCL, trimesh, Geometric Tools | `SACMODEL_CYLINDER` (7 coeffs, needs ~10000 iterations vs 100 for a plane); or a known-axis least-squares fit | **M** | Med | [PCL tutorial](https://pcl.readthedocs.io/projects/tutorials/en/latest/cylinder_segmentation.html), [trimesh.bounds](https://trimesh.org/trimesh.bounds.html) |
| **Catenary fit for a wire span** | esri/Gribov-Duri + scipy | 3-parameter `y = c + a·cosh((x−m)/a)`; init `a₀ = 1/(2k)` from a robust **parabola**, then `least_squares(method='trf', loss='soft_l1')` | **L** | **High** | [arXiv:2201.12499](https://arxiv.org/abs/2201.12499) |
| Per-class size table (precedent to copy) | 3D BAT, SUSTechPOINTS | A static JSON/JS class→`[l,w,h]` table plus a "Set to default size" action | **S** | **High** | [`default_vehicle_sizes.json`](https://raw.githubusercontent.com/walzimmer/3d-bat/master/src/application/config/default_vehicle_sizes.json), [`obj_cfg.js`](https://raw.githubusercontent.com/naurril/SUSTechPOINTS/master/public/js/obj_cfg.js) |
| Guess class from drawn dimensions | SUSTechPOINTS | `guess_obj_type_by_dimension(scale)` scores class sizes against the box, picks the best match | **S** | Med | [`obj_cfg.js`](https://raw.githubusercontent.com/naurril/SUSTechPOINTS/master/public/js/obj_cfg.js) |
| **Rigid pose-based propagation** (better than interpolation for static objects) | nobody in OSS LiDAR (verified negative); Supervisely does the pose-free variant | `B_f′ = T_f′⁻¹ · T_f · B_f` — exact for static infrastructure; or pairwise **point cloud registration** when no poses exist | **M** | **High** | [Supervisely 3D docs](https://docs.supervisely.com/labeling/labeling-toolbox/3d-point-cloud-episodes-2) |

---

## Temporal / propagation & interpolation (the decisive section)

This is where the 0.5 s-interval sequence is won. SUSTechPOINTS' documented data regime is
strikingly close to it: a 20 s scene, 40 raw frames, **2 frames per second annotated and the other 8
filled by linear interpolation** ([`README_guide.md` L117](https://github.com/naurril/SUSTechPOINTS/blob/master/README_guide.md)).
The prescribed procedure (L118) is:

1. Label the object in the **best-visibility frame** (near, unoccluded) so size and heading are accurate.
2. **Copy/paste the box to the previous or next frame**, adjust both. Labelling two frames first
   "gives the object an initial velocity, which helps the tracking during auto-annotation".
3. Run batch annotation (*edit multiple instances*) over the remaining frames.
4. Alternate **run algorithm → hand-fix one or two boxes → run algorithm**, which they state
   explicitly is the most efficient mode of operation.
5. Open `trajectory`, sanity-check for jumps, then `finalize` → `save` → `exit`.

The actual interpolation is small and portable. Four properties matter, and all four are visible in
the source:

- **Keyframes are human boxes only.** The input vector is nulled for boxes whose `annotator` field
  marks them algorithm-produced, so auto-generated boxes never become anchors
  ([`box_op.js` L679](https://github.com/naurril/SUSTechPOINTS/blob/master/public/js/box_op.js)).
  This is the same idea as `finalize`.
- **Constant step, re-derived.** `interpolate_step = (anns[end]-anns[start])/(end-start)`, filled
  forward as `anns[i-1] + step`, then the step is **recomputed from the remaining span** each time a
  box was auto-adjusted — so a correction mid-gap is absorbed by the rest of the gap
  ([`ml.js` L330, L371](https://github.com/naurril/SUSTechPOINTS/blob/master/public/js/ml.js)).
- **Angles are interpolated as scalars, not slerped**, with a guard: if an auto-adjusted yaw differs
  from the interpolated one by more than π/2, the result is flipped by π
  ([`ml.js` L342–348](https://github.com/naurril/SUSTechPOINTS/blob/master/public/js/ml.js)). Fine for
  a pole whose yaw barely changes; a known weak spot for large rotations.
- **Tail extrapolation holds dimensions fixed.** `MaFilter.predict()` velocity-extrapolates only the
  first six components (position + rotation) and copies the last three (scale) from the last
  observation ([`ml.js` L550–553](https://github.com/naurril/SUSTechPOINTS/blob/master/public/js/ml.js)).
  For poles and wires this is exactly right: geometry is rigid, only pose moves.

### The published formula, and one implementation to copy verbatim

For a box with `t = (f − f_A)/(f_B − f_A)`:

```
c(t)    = (1−t)·c_A + t·c_B            # centre
dims(t) = (1−t)·dims_A + t·dims_B      # l, w, h
yaw(t)  = ψ_A + t·wrap(ψ_B − ψ_A)      # shortest arc
```

That is **linear for centre and dimensions, shortest-arc for yaw — not SLERP, not SE(3)**. CVAT
implements exactly this: `getPosition()` computes `t` and calls `interpolatePosition`, cuboid
in-betweening is a per-coordinate lerp of the 8-point array with `shape.rotation = 0; // is not
supported` ([track.ts](https://raw.githubusercontent.com/cvat-ai/cvat/develop/cvat-core/src/annotations-objects/track.ts),
[cuboid-track.ts](https://raw.githubusercontent.com/cvat-ai/cvat/develop/cvat-core/src/annotations-objects/cuboid-track.ts)).
Its angle-wrap helper is worth **copying verbatim** —
[`findAngleDiff`](https://raw.githubusercontent.com/cvat-ai/cvat/develop/cvat-core/src/annotations-objects/object-utils.ts)
handles the ±180° boundary correctly, which naive lerp does not.

Note the difference from SUSTechPOINTS: CVAT lerps **the 8 vertices**, which shrinks/lerps edges
rather than producing a rigid in-between box; SUSTechPOINTS lerps **centre/rotation/scale**. For a
long thin wire box these differ visibly under large yaw change.

**3D BAT** ([arXiv:1905.00525](https://arxiv.org/abs/1905.00525),
[code](https://github.com/walzimmer/3d-bat)) is the closest prior art to build from: a two-keyframe
data model per object (`interpolationStart` / `interpolationEnd` + file indices), and in
continuous-sequence mode, editing length/width **also shifts the centre by half the delta along yaw**
(`x += (v−scale)·cos(yaw)/2`) so the box face stays put. Supervisely's interpolation app uses spline
interpolation and **fails if an object has only one keyframe** in the tracked span
([README](https://raw.githubusercontent.com/supervisely-ecosystem/3d-track-interpolation/master/README.md)).

### The stronger idea for *this* dataset: propagate rigidly, don't interpolate

The survey turned up something that should change the plan. If per-frame poses exist, then with
`T_f = T_world←sensor(f)`:

```
B_world = T_f · B_f        then        B_f′ = T_f′⁻¹ · T_f · B_f
```

Dimensions are invariant, the rotation part carries the heading, the translation maps the centre. For
**wires and poles, which are static**, this is **exact up to pose error** — it is not an
approximation, unlike interpolation. On a 0.5 s sequence where the same pole appears in dozens of
consecutive frames, this removes the per-frame work rather than approximating it.

Two supporting facts:

- **No open-source LiDAR annotator the survey checked documents pose-based box propagation** (3D BAT,
  SUSTechPOINTS, LATTE, CVAT cuboids, Segments.ai, Supervisely all interpolate in the sensor frame).
  Reported as a verified negative — so this is a genuine differentiator, and also why there is no
  reference implementation to copy.
- **Supervisely does the pose-free version of the same thing**, using point cloud registration to
  compute the offset between neighbouring clouds rather than reading poses: *"we obtain a
  transformation matrix that can be used to align the source point cloud with the target point
  cloud"* ([Supervisely 3D docs](https://docs.supervisely.com/labeling/labeling-toolbox/3d-point-cloud-episodes-2)).
  That is the fallback when no poses are available.
- **Kognic** is the only platform found that documents motion compensation explicitly, and its
  rationale matches this use case: *"Motion compensation is of particular importance… when point
  clouds are aggregated across frames"*
  ([Kognic docs](https://developers.kognic.com/docs/kognic-io/scenes/lidars_with_imu_data/)).

That last quote points at the strongest workflow of all: **aggregate N sweeps into a map frame, label
each wire and pole once, then back-project with `T_f⁻¹`.** It eliminates interpolation entirely.
Pose conventions to read before implementing: **Waymo** defines a vehicle pose as *"a 4x4 transform
matrix from the vehicle frame to the global frame"* with global = East-North-Up, and labels as
*"7-DOF 3D upright bounding box (cx, cy, cz, l, w, h, θ)"* — the same parameterisation as labelCloud
([Waymo paper](https://ar5iv.labs.arxiv.org/html/1912.04838) §3.2). **[UNVERIFIED: the exact KITTI
odometry pose wording and the nuScenes `ego_pose` convention — the devkits were unreachable.]**

**Porting note for labelCloud.** `next_pcd()` already snapshots `previous_bboxes` and re-applies
them when the new frame has no labels (`controller.py` L67–77). That is the natural hook: replace the
unconditional copy with (a) a per-object track ID on `BBox`, (b) keyframe anchors (human-edited),
(c) the linear fill + EMA tail above. Keep interpolation in the **same coordinate frame** the boxes
are stored in — SUSTechPOINTS explicitly interpolates in *global* coordinates and converts back
(`box_op.js` L679–697), which sidesteps ego-motion entirely; only if poses are unavailable do you
need the "both frames in the LiDAR frame" fallback, and then a moving ego vehicle will bias the
interpolated centres. Nothing in labelCloud currently carries a pose, track ID, or timestamp, so
that metadata is new state — S–M of work, and the part most likely to be under-scoped.

---

## Model-based options

Be blunt about what is realistic.

**Not realistic: pretrained car detectors.** SUSTechPOINTS' own shipped model demonstrates the
ceiling. `algos/models/deep_annotation_inference.h5` is loaded by `pre_annotate.py` and predicts
**only a yaw class**: 512 points sampled per object → `pred_cls` → `(pred_cls*3 + 1.5)·π/180`, i.e.
120 classes at 3° resolution, z-rotation only
([`pre_annotate.py` L15–47](https://github.com/naurril/SUSTechPOINTS/blob/master/algos/pre_annotate.py)).
It is a *refinement* model that requires the object's points and an existing box — it detects nothing.
A KITTI/Waymo-trained detector is trained on cars, pedestrians and cyclists; poles and wires are not
in those taxonomies, and a wire is a few points thick. Importing such a model gives a long tail of
junk boxes.

**Also weaker than it looks: SUSTechPOINTS' full auto-annotate pipeline is dead code.** Everything
that would *detect* objects — PCL clustering via an external binary
(`/home/lie/code/pcltest/build/cluster`), the object-vs-environment filter model
(`deepannotate_rp_discrimination_obj_xyzi.h5`), the nearby-object filter, and the box-dimension
calculator — sits inside an `if False:` block
([`pre_annotate.py` L50](https://github.com/naurril/SUSTechPOINTS/blob/master/algos/pre_annotate.py)),
so `annotate_file` / `pre_annotate` are not even defined at runtime, while `main.py` still routes
`/auto_annotate` to `pre_annotate.annotate_file`
([`main.py` L152–154](https://github.com/naurril/SUSTechPOINTS/blob/master/main.py)). The only live
route is `/pre_annotate` → `predict_yaw` ([`main.py` L146](https://github.com/naurril/SUSTechPOINTS/blob/master/main.py)).
So "AI-assisted" in this tool means "re-orient an existing box", not "find objects".

**Realistic: point-wise semantic segmentation.** This is the learned path that fits the problem.
LitePT is already checked out in this workspace and is a lightweight point transformer backbone for
semantic segmentation, with pretrained weights published on Hugging Face
([README](https://github.com/prs-eth/LitePT), [arXiv 2512.13689](https://arxiv.org/abs/2512.13689)).
The shape that works here is: **segment pole/wire points → fit boxes geometrically** (rotated AABB,
as in `pre_annotate.py` L195–221, or a line/catenary fit for wires). That contributes points, not
boxes, and it composes with every model-free feature in the table above. It still needs a labelled
pole/wire training set — which is what the engineer is producing — so the sequencing is: ship the
geometric + temporal assists first, label a few hundred frames, then train segmentation on those.
For validating that model there is a public benchmark in exactly this domain — **TS40K**: 40,000 km of
transmission systems, 22 annotated classes, wires and pylons, benchmarking both 3D semantic
segmentation and 3D object detection ([arXiv:2405.13989](https://arxiv.org/abs/2405.13989),
[code](https://github.com/dlavado/TS40K)).

---

## Model-free geometry: what the libraries actually give you

> **Provenance.** This section comes from a delegated survey that read Open3D `main` source,
> PCL/PDAL/scikit-learn/trimesh docs, CVAT and 3D BAT source, and the power-line literature. Its
> inline verification markers are preserved: **[UNVERIFIED]** means the survey could not fetch the
> primary source (several MDPI DOIs return 403 to automated fetchers; GitHub HTML was intermittently
> unreachable). I did not re-verify these independently — treat the markers as load-bearing.

### Click-to-fit is nearly free, but know what Open3D's OBB really is

`PointCloud.get_oriented_bounding_box()` is **PCA of the convex hull, then an axis-aligned box in
that frame** — it computes the hull, takes mean/covariance of *hull vertices only*, eigendecomposes,
and projects. Open3D's own docstring calls it *"an approximation to the minimal bounding box"*
([pybind source](https://cdn.jsdelivr.net/gh/isl-org/Open3D@main/cpp/pybind/geometry/geometry.cpp),
[BoundingVolume.cpp](https://cdn.jsdelivr.net/gh/isl-org/Open3D@main/cpp/open3d/geometry/BoundingVolume.cpp)).

The primitive worth using is the **static** `o3d.geometry.OrientedBoundingBox.create_from_points(points)`
— it takes your picked points directly, no `PointCloud` needed. Siblings:
`create_from_points_minimal(points)`, `AxisAlignedBoundingBox.create_from_points(points)`,
`OrientedBoundingEllipsoid.create_from_points(points)` (min-volume, Khachiyan), and
`obb.get_point_indices_within_bounding_box(points)` — the last one is what makes a
**click → fit → grow → refit** loop a few lines. The Tensor API exposes
`method ∈ {PCA, MINIMAL_APPROX, MINIMAL_JYLANKI}`.

Two corrections to assumptions in the original brief:

- **`get_axis_aligned_bounding_box()` takes no arguments — there is no `robust=True` for AABB.**
  `robust` exists only on the oriented variants. One is pure min/max accumulation.
- **`robust=True` does not mean "robust statistics."** The docstring is literal: *"uses a more robust
  method which works in degenerate cases but introduces noise to the points coordinates."* It
  switches qhull from `"Qt"` to `"QJ"` — i.e. it **randomly jitters your points**
  ([Qhull.cpp](https://cdn.jsdelivr.net/gh/isl-org/Open3D@main/cpp/open3d/geometry/Qhull.cpp)).
  **Never use it for a box you will save as ground truth.**

### Region growing and clustering

Open3D's `cluster_dbscan(eps, min_points)` implements Ester et al. 1996, but
[`PointCloudCluster.cpp`](https://cdn.jsdelivr.net/gh/isl-org/Open3D@main/cpp/open3d/geometry/PointCloudCluster.cpp)
shows **phase 1 precomputes the full radius-neighbour list for every point** — memory is
O(Σ neighbours), and that cost is paid **even for a single seed**. On a dense scan it can blow up.
Practical recipe for click-to-grow: **crop a local AABB around the click → `voxel_down_sample` →
DBSCAN on the crop.** That defeats the memory issue and most of the density variation, since `eps` is
an absolute distance while LiDAR spacing grows with range — the textbook DBSCAN limitation, which is
why OPTICS/HDBSCAN exist.

**Open3D has no region-growing implementation (verified negative).** PCL's
`pcl::RegionGrowing` is the reference: sort by curvature, grow from the flattest point, accept
neighbours whose normal deviates less than `setSmoothnessThreshold` (tutorial uses 3°), push accepted
points below `setCurvatureThreshold` as new seeds
([PCL tutorial](https://pcl-docs.readthedocs.io/en/latest/pcl/doc/tutorials/content/region_growing_segmentation.html);
Rabbani, van den Heuvel & Vosselman, ISPRS 2006). 3° is deliberately tight — sparse wire points need
10–20°, which then leaks across wire/vegetation boundaries.

### Poles: the standard model-free pipeline

**(1) ground removal / height-normalisation → (2) clustering → (3) covariance-eigenvalue test →
(4) footprint test → (5) cylinder fit.**

Step 3 has an exactly implementable, citable definition in PDAL's
[`filters.covariancefeatures`](https://pdal.io/en/stable/stages/filters.covariancefeatures.html):
**linearity, planarity, scattering** (Demantké, Mallet, David & Vallet, *Dimensionality based scale
selection in 3D lidar point clouds*, ISPRS 2011) and **verticality** (Guinard & Landrieu, IAPRS 2017),
described as *"higher for vertical structures, highest for thin vertical strips."* These are
computable in numpy from `pcd.estimate_covariances(...)` + `np.linalg.eigh`. **Independent
confirmation this is the right route for poles:** Supervisely's own 3D docs state that *"points of
poles and building tend to have high verticality scores, while ground points usually have low
verticality scores"* ([Supervisely 3D docs](https://docs.supervisely.com/labeling/labeling-toolbox/3d-point-cloud-episodes-2)).

**There are named, benchmarked pole pipelines to copy — this is not a from-scratch design.**
**Yang et al. 2018** is the best template, with an explicit 3-stage structure: *(i) "point cloud is
preprocessed to remove outliers, downsample and filter ground points"; (ii) "the PLOs are extracted
from the point cloud by spatial independence analysis and cylindrical or linear feature detection";
(iii) "the PLOs are automatically classified by 3D shape matching."* Reported **completeness 92.7 % /
correctness 97.4 % / overall accuracy 92.3 %** on their Data I, and 90.5 / 97.1 / 91.3 % on the ISPRS
WG III/5 benchmark ([DOI 10.3390/rs10121891](https://doi.org/10.3390/rs10121891)). Stage (ii) is
exactly "cluster → cylindrical-or-linear feature test". The classic earlier detector is
**Lehtomäki et al. 2010**, which found *"77.7 % of the poles which were found by a manual
investigation"* at *"81.0 %"* correctness, using *"clustering of isolated points on horizontal
cross-section"* — i.e. the horizontal-slice footprint test
([DOI 10.3390/rs2030641](https://doi.org/10.3390/rs2030641)). Related: Pu et al. 2011
([DOI](https://doi.org/10.1016/j.isprsjprs.2011.08.006)), Rodríguez-Cuenca et al.
([DOI](https://doi.org/10.1016/j.isprsjprs.2013.10.008), voxel-based).
*(Yang's pipeline details are quoted from its abstract; Pu and Rodríguez-Cuenca stage details are
**[UNVERIFIED]** — MDPI and several publisher pages return 403 to automated fetchers, so those items
are verified at metadata+abstract level only.)*

For the **joint pole+wire** case there is a pipeline whose reconstruction stage clears the model-free
bar: **Sohn, Jwa & Kim 2012** classifies linear+planar features, separates power-line points,
sub-classifies the rest, localises pylons from *"prior knowledge of contextual relations between
power line and pylon"*, then fits per-span **catenary curve models in 3D**, progressively extended by
model hypothesis-and-verification with parameters tuned by stochastic non-linear least squares
([DOI 10.5194/isprsannals-i-3-167-2012](https://doi.org/10.5194/isprsannals-i-3-167-2012)). Honest
caveat: its *classification* stage is an MRF (probabilistic, not parameter-free) — but the
**wire/pylon reconstruction stage is purely geometric and directly reusable.**

**No primary source was found for Hough-transform or RANSAC vertical-cylinder pole detection**
(searches returned only irrelevant or non-resolving hits) — the pole-specific cylinder fit remains a
genuine literature gap, so treat cylinder fitting as a reasonable engineering choice rather than a
cited best practice.

For ground removal on **spinning LiDAR**, PDAL's CSF/PMF/SMRF are ALS-oriented; **Patchwork++** is
the one designed for 32/64-beam spinning LiDAR and exists precisely because a single global RANSAC
plane *"fail[s] to estimate an appropriate ground plane when the ground is above another structure,
such as a retaining wall"* ([arXiv:2207.11919](https://arxiv.org/abs/2207.11919),
[code](https://github.com/url-kaist/patchwork-plusplus)). PDAL's own docs warn that
*"`filters.smrf` performs much better… prefer this over `filters.pmf`"*. **PMF is the most
parameter-fragile of the three**: its threshold is `slope × cell_size × Δwindow + initial_distance`
capped at `max_distance`, so with sparse far-range ground returns too-small `initial_distance` or
`cell_size` classifies **real ground as non-ground**. Practical ranking for a 32/64-beam spinning
LiDAR: **Patchwork++ (adaptive, no tuning) > SMRF > CSF > PMF > a single global RANSAC plane.** If you
use CSF, there is a maintained Python binding: `pip install cloth-simulation-filter` →
`import CSF`, Apache-2.0 ([PyPI](https://pypi.org/project/cloth-simulation-filter/),
[C++](https://github.com/jianboqi/CSF); R wrapper [RCSF](https://github.com/Jean-Romain/RCSF)).
**[UNVERIFIED: the Python attribute names for rigidness / class_threshold / time_step / iterations —
the PyPI README shows only `bSloopSmooth` and `cloth_resolution`.]** The height-above-ground step that
survives sloped terrain (unlike a global plane) is
[`filters.hag_dem`](https://pdal.io/en/stable/stages/filters.hag_dem.html), or the numpy equivalent:
interpolate a ground surface from ground-classified points with `scipy.interpolate.griddata` and
subtract.

For the shaft: **PCL `SACMODEL_CYLINDER`**, 7 coefficients, minimal sample 3, normals optional
(`normal_distance_weight` defaults to 0). The PCL tutorial uses **`setMaxIterations(10000)`** versus
100 for a plane, because a 3-point/7-parameter model is far more iteration-hungry
([tutorial](https://pcl.readthedocs.io/projects/tutorials/en/latest/cylinder_segmentation.html)).
Clip the infinite cylinder by projecting points onto the axis to recover pole height. **Also worth
knowing: PCL has `SACMODEL_STICK` — *"a line with user-given min/max width"* — which is a more natural
pole primitive than a full cylinder**, since a pole is a bounded-width line rather than an infinite
one ([sample consensus models](https://pointclouds.org/documentation/group__sample__consensus.html)).

The RANSAC backbone for all of the above is Fischler & Bolles 1981,
[DOI 10.1145/358669.358692](https://doi.org/10.1145/358669.358692).

### Wires: no line RANSAC in Open3D, and the catenary is the field's answer

**Open3D has no line/cylinder RANSAC — `segment_plane` is its only primitive fitter (verified
negative).** Python options: `pyransac3d` (default `thresh=0.2` is far too loose — use 0.03–0.10 m;
its own docstring warns the cylinder fit *"does NOT present good results on real data"*), or sklearn
`RANSACRegressor`, which **fits `y = f(X)` and is not a 3D line fitter** — you must PCA-rotate so the
wire runs along one axis and fit projected lines, or supply a custom estimator returning the
orthogonal projection. `min_samples` must be set explicitly for any non-`LinearRegression` estimator.

The catenary is `y = c + a·cosh((x − m)/a)` — **3 parameters**. The best open primary source is
Gribov & Duri (Esri), *Reconstruction of Power Lines from Point Clouds*
([arXiv:2201.12499](https://arxiv.org/abs/2201.12499)), which uses MST clustering with a max-gap
threshold (bridges split wire returns), dynamic programming to partition a polyline into per-catenary
segments, then k-means with catenary refit. **Its honest limitation: fitting is plain least squares,
explicitly non-robust — robustness comes from the DP penalty and assignment, not from RANSAC.**

Practical robust recipe, all in the existing stack: robust **parabola** via
`RANSACRegressor(PolynomialFeatures(2) → LinearRegression)` to pick inliers → initialise
`a₀ = 1/(2k)` (since `cosh(u) ≈ 1 + u²/2`) → robust nonlinear refit with
`scipy.optimize.least_squares(..., method='trf', loss='soft_l1', f_scale=0.05)`. **`method='lm'`
supports only `loss='linear'` and no bounds, so `'trf'` is mandatory.** Guard three failures: `cosh`
overflow (always init `a` from the parabola and centre/scale x); a free-orientation wire needs 5
parameters, so **fit the vertical plane first**, then the 3-parameter catenary inside it; and with a
partial arc `a` and `m` are strongly correlated.

Literature entry points: [Munir, Awrangjeb & Stantic 2023 review](https://doi.org/10.3390/rs15040973)
(best single starting point, 84 refs); Jwa & Sohn 2012, *piecewise catenary curve model growing*
([DOI](https://doi.org/10.14358/PERS.78.11.1227)); McLaughlin 2006, *Extracting transmission lines
from airborne LIDAR data*, IEEE GRSL 3(2):222 — **cite by title/journal, not by DOI: the DOI could
not be resolved on a second verification pass and must be treated as [UNVERIFIED]**; Zhu & Hyyppä 2014
([DOI](https://doi.org/10.3390/rs61111267)); Kukko et al. 2019 for MLS
([DOI](https://doi.org/10.1016/j.autcon.2019.03.023)). On sensing difficulty, Girard et al. name it
exactly: *"conductors provide minimal surface for LiDAR beams limiting the number of conductor points
in a scan… not all conductors are consistently detected… distinguishing LiDAR points corresponding to
conductors from other objects, such as trees and pylons, is difficult"*
([arXiv:2506.20812](https://arxiv.org/abs/2506.20812)). **[UNVERIFIED: several MDPI DOIs are cited at
bibliographic-record level — the publisher returns 403 to automated fetchers.]**

**A dataset to validate against:** **TS40K** (WACV 2025) — 40,000 km of transmission systems, 22
annotated classes, benchmarking both semantic segmentation and 3D object detection
([arXiv:2405.13989](https://arxiv.org/abs/2405.13989), [code](https://github.com/dlavado/TS40K)).

### Elongated objects: why the upright box is structurally wrong

The yaw-only reduction is legitimate for cars **by assumption**, stated verbatim in the IoU-loss
paper: *"the general 3D BBox with three degree-of-freedoms for rotation can be reduced to one (e.g.,
'yaw' angle) **by assuming that all the objects should lay on a relative flat road ground**"*
([arXiv:1908.03851](https://arxiv.org/abs/1908.03851) §3.3). **A wire's long axis is not
ground-parallel**, so an upright yaw-only box is the wrong primitive structurally — independent of how
carefully it is drawn. That is the crisp answer to why car-style boxes fit wires badly.

For poles the failure is different: a pole is rotationally symmetric, so **yaw is unidentifiable** —
every yaw gives the same IoU when width ≈ length. A stored pole yaw is unfalsifiable, not measured.
**[Reasoning, not citation — the survey found no paper asserting this.]**

Aspect ratio also breaks the usual QA. KLD states the mechanism: gradient weight on the angle should
*"adjust… according to the aspect ratio… a slight angle error would cause a serious accuracy drop for
large aspect ratios objects"* ([arXiv:2106.01883](https://arxiv.org/abs/2106.01883)). **Consequence:
IoU-threshold QA is near-degenerate in yaw and hypersensitive to along-wire centre error for wires —
use centreline and endpoint error instead.**

**Curve primitives are essentially absent from 3D annotation tools (verified negatives):** CVAT is
cuboid-only in 3D tasks with no spline/bezier, and its polylines are a 2D-image tool
([3D annotation](https://docs.cvat.ai/docs/annotation/manual-annotation/modes/3d-object-annotation/),
[shape types](https://docs.cvat.ai/docs/annotation/manual-annotation/shapes/types-of-shapes/));
Supervisely's 3D tools are Cuboid / Smart Tool / Point Cloud Pen / Measure Distance
([docs](https://docs.supervisely.com/labeling/labeling-toolbox/3d-point-clouds)). The closest
commercial precedent for control-point curve annotation over a cloud is **Kognic's 3D lane tool**
(*"place points where you want to have control points"* —
[docs](https://docs.kognic.com/task-view-guide/3d-lane)), and the only mainstream point-cloud tool
with a true **spline** primitive is **CloudCompare**, which has no annotation database
([Polyline](https://www.cloudcompare.org/doc/wiki/index.php/Polyline),
[Spline](https://www.cloudcompare.org/doc/wiki/index.php/Spline)). ~~No tool the survey could verify
performs click-to-trace annotation of individual wires.~~ **CORRECTED — this claim is wrong.** A
purpose-built commercial power-line annotation UI with exactly that interaction does exist; see
`## Tool survey (part 2)` below. Read that section before treating the absence of a wire-tracing tool
as a finding.

---

## Traps — things that look good but don't work here

- **Upstream master has moved from PyQt5 to PySide6.** Current `master`
  [`controller.py`](https://github.com/ch-sa/labelCloud/blob/master/labelCloud/control/controller.py)
  opens with `from PySide6 import QtCore, QtGui`, while the installed 1.1.1 and this fork are PyQt5
  (the 1.1.1 wheel requires `PyQt5>=5.15.7` — [PyPI](https://pypi.org/pypi/labelCloud/json)). Do not
  plan to `git merge` master into the fork; read it for ideas and port by hand. This also means the
  PR #181 code above may not apply cleanly.
- **`z_rotation_only = True` is the default and it blocks tilted wires.** With it on, only yaw is
  editable ([`default_config.ini`](https://github.com/ch-sa/labelCloud/blob/master/labelCloud/resources/default_config.ini),
  [README](https://github.com/ch-sa/labelCloud/blob/master/README.md)). A catenary wire that is not
  horizontal cannot be enclosed by an axis-upright box. 9-DoF must be enabled before any wire
  labelling begins — and be aware every downstream export/convention then carries roll and pitch.
- **PR #181 raises `min_boundingbox_dimension` from `0.01` to `0.1`.** Adopting that PR wholesale caps
  the minimum box edge at 10 cm and makes a thin wire unrepresentable. Take the features, not that
  constant.
- **`propagate_labels` is not tracking.** It copies the entire previous frame's box list into any
  frame that has no label file yet ([`controller.py` L67–77](https://github.com/ch-sa/labelCloud/blob/master/labelCloud/control/controller.py)).
  No IDs, no motion compensation. On a 0.5 s sequence with a moving ego vehicle every propagated
  pole will be offset, and on a *static* scene it silently duplicates boxes into frames whose labels
  were merely not saved yet. Useful as a seed for a real interpolator, harmful as a feature.
- **Labelling pole-by-pole across frames instead of object-by-object.** SUSTechPOINTS' first
  recommendation is explicitly the opposite of frame-by-frame: finish one object across the whole
  scene, then move to the next ([`README_guide.md` L116](https://github.com/naurril/SUSTechPOINTS/blob/master/README_guide.md)).
  labelCloud's UI (prev/next frame, `1`–`9` box select, no track concept) actively encourages the
  slow pattern.
- **Interpolating yaw as a linear scalar.** It is what SUSTechPOINTS does, with only a π/2 guard
  ([`ml.js` L342–348](https://github.com/naurril/SUSTechPOINTS/blob/master/public/js/ml.js)). It is
  fine for poles and acceptable for wires with a stable orientation; it is not correct for large
  rotations and there is no slerp in the codebase.
- **Believing the "AI" button.** `/auto_annotate` is routed to a function that does not exist at
  runtime because its definition is inside `if False:`
  ([`main.py` L152](https://github.com/naurril/SUSTechPOINTS/blob/master/main.py),
  [`pre_annotate.py` L50/L280](https://github.com/naurril/SUSTechPOINTS/blob/master/algos/pre_annotate.py)).
  Do not plan a fork around it.
- **The 2D image coupling in labelCloud is not a coupling.** `show_2d_image` opens the JPEG in a
  separate window with no calibration, no projection and no box overlay
  ([`view/gui.py`](https://github.com/ch-sa/labelCloud/blob/master/labelCloud/view/gui.py),
  [PR #44](https://github.com/ch-sa/labelCloud/pull/44)). Real 3D↔2D box coupling
  (`calib_folder`, `kitti` format) exists only as a label transform, not as a UI affordance.
- **`robust=True` silently jitters your points.** It is not robust statistics — it switches qhull to
  joggle mode to survive degenerate hulls, *"introduc[ing] noise to the points coordinates"*
  ([Qhull.cpp](https://cdn.jsdelivr.net/gh/isl-org/Open3D@main/cpp/open3d/geometry/Qhull.cpp)). Using
  it on a click-to-fit box that you then save as ground truth corrupts the label.
- **PCA cannot give you a wire's roll.** For a long thin tube the eigenvalues split λ₁ ≫ λ₂ ≈ λ₃, so
  the wire *direction* is well-conditioned but the two cross-section axes are nearly degenerate and
  the roll about the wire axis is **numerically arbitrary** — the box visibly spins between
  neighbouring selections. Pin roll by convention, or use an ellipsoid/catenary for wires. This is
  the single most likely way a click-to-fit feature disappoints in practice.
- **IoU-threshold QA is the wrong metric for wires.** With an extreme aspect ratio the IoU-vs-yaw
  curve is near-degenerate while a small along-wire centre error dominates
  ([KLD, arXiv:2106.01883](https://arxiv.org/abs/2106.01883)). Use centreline and endpoint error.
- **Do not go shopping for a spline/curve annotation primitive — it does not exist.** CVAT is
  cuboid-only in 3D, Supervisely's 3D tools are box/pen/distance, and the only mainstream
  point-cloud tool with a true spline is CloudCompare, which has no annotation database. If wires
  need curves, that UI is bespoke work.
- **Correction to the delegated survey, from my own reading.** That survey reported as a "verified
  negative" that SUSTechPOINTS' README documents no A→B keyframe interpolation. That is **wrong** —
  it evidently read `README.md`, not `README_guide.md`, which documents the interpolation workflow in
  detail (L117–119, L153–154) and whose implementation I read directly in `public/js/ml.js`. The
  interpolation feature is real; treat the survey's negative here as a miss, not a finding.
- **Per-class templates are a schema change, not a config tweak.** `_classes.json` in 1.1.1 has no
  dimension field ([`default_classes.json`](https://github.com/ch-sa/labelCloud/blob/master/labelCloud/resources/default_classes.json)),
  and `picking.py` reads the *global* `STD_BOUNDINGBOX_*` values. Both the schema and the two
  labeling strategies must change together.

---

## Sections that are thin

**Status: the three gaps originally listed here have since been closed.** They are recorded below
because the *order* in which this report was assembled matters — the feature table, the temporal
section and the traps were all written before the part-2 survey landed, and a few of their
conclusions are corrected further down. Read `## Tool survey (part 2)` before acting on any
"no tool does X" claim above.

- **~~Non-labelCloud annotation tools~~ — CLOSED** by `## Tool survey (part 2)`. The general tool
  survey did eventually land (its first agent was stopped, a replacement completed it), covering
  Xtreme1/BasicAI, CVAT 3D, Supervisely, Segments.ai and others. It also corrected the brief:
  `SpringVC/point-cloud-annotation-tool` **does not exist** — the real project is
  `springzfx/point-cloud-annotation-tool`, and it was abandoned in 2019.
- **~~Power-line-specific tooling~~ — CLOSED, with a correction.** The earlier claim that *"no tool
  the survey could verify performs click-to-trace annotation of individual wires"* is **wrong**:
  a purpose-built commercial power-line annotation UI does exist and is documented in part 2. The
  extraction literature is also covered above (Jwa & Sohn, Zhu & Hyyppä, Kukko, the 2023 and 2024
  reviews, Gribov & Duri, TS40K).
- **Model-free geometry** — covered in the section above (Open3D OBB/clustering internals, PCL region
  growing and cylinder fitting, PDAL covariance features and ground filters, RANSAC line fitting,
  catenary fitting, Patchwork++), now with named, benchmarked pole pipelines.

**What remains genuinely uncertain** is not coverage but *verification depth*. Claims marked
**[UNVERIFIED]** throughout — MDPI papers verified at metadata+abstract level only (the publisher
returns 403 to automated fetchers), the McLaughlin 2006 DOI, the O'Rourke and Barequet & Har-Peled
DOI landing pages, the nuScenes `ego_pose` convention, and CSF's Python attribute names — were **not**
independently re-checked by me. I read labelCloud and SUSTechPOINTS at source first-hand; the geometry
and tool-survey material came from delegated agents whose markers I preserved rather than promoted.

---

## Tool survey (part 2)

Closes the two holes left in **Sections that are thin** above: comparable tools (the whole of
focus area A) and purpose-built power-line/pole tooling. Everything below was read this session from a
primary source — repo README or source file, official docs page, or vendor user guide. **UNVERIFIED**
marks anything not confirmed against a primary source.

Four corrections come out of this survey — one to a claim made earlier in this file, three to
assumptions in the brief.

- **A purpose-built power-line annotation UI *does* exist, and it is fully documented.** The earlier
  "Elongated objects" section concludes *"No tool the survey could verify performs click-to-trace
  annotation of individual wires."* That is wrong. **TerraSolid TerraScan** ships an entire commercial
  Powerlines toolbox with exactly that interaction — see the next subsection. Its absence from the
  earlier survey is a miss, not a finding.
- **`SpringVC/point-cloud-annotation-tool` does not exist.** GitHub has no user named `SpringVC` (user
  search → 0 results) and `SpringVC/point-cloud-annotation-tool` → HTTP 404. The real project is
  **`springzfx/point-cloud-annotation-tool`** — MIT, C++/PCL/VTK/Qt5, 516 stars, **last push
  2019-04-30, i.e. abandoned** ([repo](https://github.com/springzfx/point-cloud-annotation-tool)).
- **Xtreme1 and BasicAI are one lineage, not two independent tools.** Xtreme1 is the open-source
  project; `basic.ai` is its commercial cloud — the docs say so directly ("our cloud version at
  <https://www.basic.ai/>", [welcome-to-xtreme1](https://docs.xtreme1.io/xtreme1-docs/welcome-to-xtreme1)).
  BasicAI's docs confirm the OSS branch was retired: "The hosted Xtreme1 (open source project) web
  interface is no longer officially supported"
  ([basic.ai docs](https://docs.basic.ai/docs/pandaset-dataset-tutorial)).
- **`anno3d` is a real tool *and* a file format — two different things share the name.** Neither is a
  box-annotation labeler you can adopt, but both are worth knowing:
  1. **`anno3d` = the CLI of [`annofab-3dpc-editor-cli`](https://pypi.org/project/annofab-3dpc-editor-cli/)**
     (kurusugawa-computer) — `anno3d version` → `annofab-3dpc-editor-cli 0.2.2a1`
     ([README](https://github.com/kurusugawa-computer/annofab-3dpc-editor-cli)). This is the front-end CLI
     for **Annofab's `3dpc` (3D point cloud) editor**, a Japanese **commercial** platform. Its doc
     sidebar is itself informative: annotation types are **バウンディングボックス (bounding box)** and
     **セグメント (segment)**; there is a **トラッキング (tracking) panel**; tools include inspection
     comments and a **定規 (ruler)**; and — the directly relevant part — two features are grouped under
     **"CLIで設定する機能" (features configured via the CLI)**: **「Cuboidの規定サイズ」 (preset cuboid
     size)** and **「アノテーション範囲」 (annotation area)**
     ([3D editor index](https://annofab.readme.io/docs/3dpc-editor)). The *page titles and their
     grouping* are verified from the navigation; the page bodies are JS-rendered and could **not** be
     read, so the exact semantics of preset-size and annotation-area are **UNVERIFIED**.
  2. **anno3d is also the label-file format** of the **3D-Annotator** project (KIT / Fraunhofer IOSB),
     storing **8-bit *semantic segmentation* indices only — no bounding boxes at all**
     ([UTF-8 v2 spec](https://github.com/3D-Annotator/3D-Annotator/blob/main/frontend/src/anno3d/v2/targets/utf8/Specification.md):
     magic `# ANNO3D-UTF-8`, `model_type ∈ {point_cloud, mesh, texture_mesh}`, then
     `label <class> <count>` index blocks). Irrelevant to a box workflow, but its three targets
     (UTF-8 / binary / PNG) are a clean model for a compact point-label sidecar.
  The nearest tool named **ActiveAnno3D** is a third thing: the active-learning extension of 3D BAT
  ("2024/01: Active learning support … **ActiveAnno3D**", [3D BAT](https://github.com/walzimmer/3d-bat),
  [`walzimmer/active-anno-3d`](https://github.com/walzimmer/active-anno-3d)).

### Master table

`Model?` = does the assist need a trained model? **No** = pure geometry/state, portable as-is.
**Yes** = trained model required. **Pluggable** = the tool defines a model interface, so the feature is
dead without a model the operator supplies.

| Tool | Relevant feature | Mechanism | Model? | Source |
|---|---|---|---|---|
| **Xtreme1** (OSS, LF AI & Data sandbox) | **3 clicks → auto-fitted cuboid** | "click 3 time to draw the outline of the object, then a cuboid that fits the object will be generated by the AI-assisted tool" | **Yes** | [LiDAR Annotation Tool](https://docs.xtreme1.io/xtreme1-docs/product-guides/lidar-annotation-tool) |
| Xtreme1 | **Auto-Fit on its own key** | `U` = "Turn on/off Auto Fit" — creation then snaps to the object | **Yes** | [same](https://docs.xtreme1.io/xtreme1-docs/product-guides/lidar-annotation-tool) |
| Xtreme1 | Copy/paste **and copy-by-drag** | `Ctrl/⌘+C` / `V`; `Ctrl/⌘+Drag` = "Copy by Drag Object" | No | [same](https://docs.xtreme1.io/xtreme1-docs/product-guides/lidar-annotation-tool) |
| Xtreme1 | **Review panel on a hotkey** | `R` = "Open/Close Review Panel" | No | [same](https://docs.xtreme1.io/xtreme1-docs/product-guides/lidar-annotation-tool) |
| Xtreme1 | 3-view box editing (overhead / side / rear) driven by keys | `ZX` rotate, `AWSD` side-view move, `QE` rear-view move, `C` head direction, `V` flip head; shortcuts do **not** reset view scale | No | [same](https://docs.xtreme1.io/xtreme1-docs/product-guides/lidar-annotation-tool) |
| Xtreme1 | Frame-series tracking | ships **AB3DMOT** as the tracking model | **Yes** | [welcome](https://docs.xtreme1.io/xtreme1-docs/welcome-to-xtreme1) |
| Xtreme1 | Model pre-annotation with class + confidence filters | ships **OpenPCDet** for 3D detection; custom models pluggable | **Yes** | [welcome](https://docs.xtreme1.io/xtreme1-docs/welcome-to-xtreme1) |
| **BasicAI** (commercial; on-prem sales-gated) | **AI-assisted boxing** | "anchor the starting and ending points. AI will automatically detect the object and create a cuboid around it", vs "**Manual Boxing: Anchor three points**"; `U` toggles manual↔AI | **Yes** | [Object Detection & Tracking](https://docs.basic.ai/docs/object-detection-tracking) |
| BasicAI | **Per-class standard dimensions** | Class → "**Standard** (optional): Set the standard **Length**, **Width**, **Height**, and **Points** … as a reference for annotators", plus Constraints (`minHeight`, `minPoints`); in-tool "Set as Standard" button | No | [Class](https://docs.basic.ai/docs/class), [tracking](https://docs.basic.ai/docs/object-detection-tracking) |
| BasicAI | **Interpolation tracking, with `Fixed` vs `dynamic` size** | "Calculate the object position in specific frames based on the current results. **At least two ground truth values on the timeline are required**"; "`Fixed` only changes position info without altering the box size, while `dynamic` changes both" | No | [tracking](https://docs.basic.ai/docs/object-detection-tracking) |
| BasicAI | **Snap to point** | `I` = "snap to point" | No | [tracking](https://docs.basic.ai/docs/object-detection-tracking) |
| BasicAI | **Polyline as a first-class primitive for linear objects** | "Annotate lines in point clouds; commonly used for representing linear objects like roads, **pipelines**"; the vendor blog names power lines explicitly. Split `Shift+F`, merge, and derive "a centerline from two polylines" with `.` | No | [Class](https://docs.basic.ai/docs/class), [blog](https://www.basic.ai/blog-post/introduction-to-3d-polygon-and-polyline-annotation) |
| BasicAI | Track management + trajectory | persistent `trackId` "consistent across frames"; Timeline with Merge/Split/Fold; `P` = trajectory | No | [export format](https://docs.basic.ai/docs/export-result-description), [tracking](https://docs.basic.ai/docs/object-detection-tracking) |
| **CVAT** (OSS, MIT) | **3D cuboid track interpolation — real, and verified in source** | Draw cuboid → **Track**; interpolation between keyframes is automatic (there is no "Interpolate" button). `CuboidTrack.interpolatePosition()` lerps the whole points array — with layout `[x,y,z, rotX,rotY,rotZ, w,h,d, …]` that means **position and size interpolate linearly** — but overrides indices 3–5 with **shortest-arc** angle interpolation via `findAngleDiff`; the separate `rotation` field is explicitly unsupported for cuboids | No | [3D object annotation](https://github.com/cvat-ai/cvat/blob/develop/site/content/en/docs/annotation/manual-annotation/modes/3d-object-annotation.md), [`cuboid-track.ts`](https://github.com/cvat-ai/cvat/blob/develop/cvat-core/src/annotations-objects/cuboid-track.ts) |
| CVAT | Bulk **Propagate shapes** to a target frame | copies shapes current frame → target frame; Community-supported | No | [shapes converter](https://github.com/cvat-ai/cvat/blob/develop/site/content/en/docs/annotation/manual-annotation/utilities/shapes-converter.md) |
| CVAT | **Nearly everything else is absent in 3D — say it explicitly** | 3D workspace has **no AI/OpenCV/Snap controls**; 3D canvas has **no `interact()`** hook; no per-class default dimensions; only the cuboid primitive (no polyline/points/mask in 3D); docs state "**The Review mode is not applicable for 3D tasks.**" | n/a | [3D workspace](https://github.com/cvat-ai/cvat/blob/develop/site/content/en/docs/annotation/annotation-editor/3d-task-workspace.md), [manual QA](https://github.com/cvat-ai/cvat/blob/develop/site/content/en/docs/qa-analytics/manual-qa.md) |
| **Supervisely** (**not** open source; only the SDK is Apache-2.0) | **Smart tool + Auto Cuboid Adjustment** | lasso a region → fitted cuboid; click an object → fitted cuboid | **Yes** (pluggable assistant) | [3D point cloud episodes](https://docs.supervisely.com/labeling/labeling-toolbox/3d-point-cloud-episodes-2.md) |
| Supervisely | **Ground segmentation, 5 algorithms** | Patchwork++, GndNet, quantile, ground-plane fitting, grid-based slope | Mixed (GndNet learned) | [same](https://docs.supervisely.com/labeling/labeling-toolbox/3d-point-cloud-episodes-2.md) |
| Supervisely | **Cuboid tracking that needs no learning** | "calculating the offset between neighboring point clouds using **Point Cloud Registration** Algorithms"; direction forward/backward/both, with progress | **No** | [same](https://docs.supervisely.com/labeling/labeling-toolbox/3d-point-cloud-episodes-2.md) |
| Supervisely | **Spline interpolation between first and last keyframe** | Ecosystem app "3D BBox Interpolation", "a modification of **spline** interpolation" | No | [app](https://ecosystem.supervisely.com/apps/3d-track-interpolation), [blog](https://supervisely.com/blog/3d-object-interpolation-in-point-clouds/) |
| Supervisely | **3D polylines + a measure-distance ruler** | ruler reports X/Y/Z per point plus per-segment and cumulative length | No | [3D point cloud episodes](https://docs.supervisely.com/labeling/labeling-toolbox/3d-point-cloud-episodes-2.md) |
| Supervisely | **A documented 3D-assistant plugin contract** — the most portable idea here | six HTTP endpoints: `/interactive_3d_detection`, `/track`, `/generate_clusters`, `/get_labeling_proposal`, `/segment_ground`, `/transfer_masks_to_pcd`; app flagged `"is3DAIAssistant": true` | Pluggable | [Create 3D assistant](https://developer.supervisely.com/app-development/create-3d-assistant.md) |
| **Segments.ai** (commercial cloud) | **Merged point cloud view for static objects** | stack the frames a *static* object appears in so it becomes dense and complete, then "draw a perfect cuboid around a static object" | **No** | [merged point cloud view](https://docs.segments.ai/how-to-annotate/label-3d-point-clouds/merged-point-cloud-view-for-static-objects) |
| Segments.ai | **Smart cuboid initialization** | hold `Alt` + drag a selection over points → fitted cuboid with position, dimensions **and rotation**. Modes: **Simple** (smallest cuboid, drag direction = yaw), **Smart** (default; smallest cuboid + predicted orientation, **filters ground points and outliers**, outlier-tolerance slider), **AI** (deep model, beta) | Simple/**Smart: No**; AI: Yes | [cuboid interface](https://docs.segments.ai/how-to-annotate/label-3d-point-clouds/3d-point-cloud-cuboid-interface) |
| Segments.ai | **Auto-adjust cuboid on `Q`** | "collects the point cloud points inside the cuboid and snaps it to a tighter fit"; **the same page also says it keeps orientation and does not filter ground/outliers** — the two statements conflict, so treat the exact behaviour as **UNVERIFIED** | **No** | [same](https://docs.segments.ai/how-to-annotate/label-3d-point-clouds/3d-point-cloud-cuboid-interface) |
| Segments.ai | **Same-dimensions track constraint** | Settings → Labeling: "all keyframes in a track will maintain the same object dimensions (width, height, depth), allowing only position and rotation changes between frames" | **No** | [track IDs](https://docs.segments.ai/how-to-annotate/label-sequences-of-data/use-track-ids-in-sequences) |
| Segments.ai | **Batch mode — one object across many frames** | "working **object by object** is usually the most efficient way"; batch mode shows the selected object in a grid of frames so you adjust the object rather than walking frames | **No** | [batch mode](https://docs.segments.ai/how-to-annotate/label-3d-point-clouds/batch-mode-for-dynamic-objects) |
| Segments.ai | **Keyframe + remove-keyframe interpolation** | keyframes auto-created on any edit; drag a keyframe diamond to move it and "interpolation is automatically recalculated"; `×` = remove-keyframe marking explicit absence | **No** | [keyframe interpolation](https://docs.segments.ai/how-to-annotate/label-sequences-of-data/use-keyframe-interpolation) |
| Segments.ai | **Per-category default cuboid dimensions** | set in Dataset → Settings → Labeling; double-click creates a cuboid already at those dimensions, and dims follow a category change while still unaltered | **No** | [cuboid interface](https://docs.segments.ai/how-to-annotate/label-3d-point-clouds/3d-point-cloud-cuboid-interface) |
| Segments.ai | Per-field **propagate to next/previous frame** | arrow buttons beside each numeric input in the Cuboid info pane; disabled for fields already synced across frames | **No** | [same](https://docs.segments.ai/how-to-annotate/label-3d-point-clouds/3d-point-cloud-cuboid-interface) |
| Segments.ai | Yaw-only rotation by default | "By default, only yaw rotation (around the z-axis) is enabled" until "Enable 3D cuboid rotation" is ticked — **the same trap as labelCloud's `z_rotation_only`** | No | [same](https://docs.segments.ai/how-to-annotate/label-3d-point-clouds/3d-point-cloud-cuboid-interface) |
| **3D BAT** (source-available, **non-commercial licence**) | Broad assist set: "AI assisted labeling, Batch-mode editing, **Interpolation mode**, Automatic tracking, Auto ground detection, **Keyboard-only annotation mode**, Auto save function, Review annotations, Sequence mode, Active learning, **Copy labels to next frame**" | web/TypeScript; mechanics in the next two rows | Mixed | [README](https://github.com/walzimmer/3d-bat) |
| 3D BAT | **Velocity extrapolation, credited in-source to SUSTechPOINTS** | `MaFilter.predict()` = `[...(x+v).slice(0,6), ...x.slice(6)]` — pose extrapolated, **scale frozen**; `decay = 0.5` for all 9 components | **No** | [`ma_filter.ts`](https://github.com/walzimmer/3d-bat/blob/master/src/application/util/ma_filter.ts) |
| 3D BAT | **Per-object copy flag + interpolation bracket + track ID** | every object carries `trackId`, a `copyLabelToNextFrame` boolean and `interpolationEndFileIndex`; frame advance deep-copies **only flagged objects** and re-selects via `getObjectIndexByTrackIdAndClass(trackId, class, frame)` | **No** | [`tool_main.ts`](https://github.com/walzimmer/3d-bat/blob/master/src/application/label_tool/tool_main.ts) |
| **`springzfx/point-cloud-annotation-tool`** | **A real, source-verified "fit the box to the points I selected" primitive — the one open implementation outside SUSTechPOINTS.** `Annotation::adjustToAnchor()` (`Annotaion.cpp` L117–150) keeps the orientation the user set and recomputes **centre + scale along the box's own axes** from anchor points captured at rubber-band selection. It fires **automatically on mouse-release**: `boxWidget->AddObserver(vtkCommand::EndInteractionEvent, boxWidgetCallback1)` (L109) → `vtkBoxWidgetCallback1::Execute()` → `anno->adjustToAnchor()` (`vtkBoxWidgetCallback.cpp` L37–40). Workflow: rubber-band select → pick class → box appears → rotate → release → **it refits itself** | C++/PCL/VTK/Qt5 desktop. Orientation is **user-supplied, not PCA-derived**; the initial box from `computeOBB` is pure min/max **axis-aligned** (yaw = 0) and rotation is about Z only | **No** (model-free) | [`Annotaion.cpp`](https://github.com/springzfx/point-cloud-annotation-tool/blob/master/src/Annotaion.cpp), [`vtkBoxWidgetCallback.cpp`](https://github.com/springzfx/point-cloud-annotation-tool/blob/master/src/vtkBoxWidgetCallback.cpp) |
| `springzfx` — what it does **not** have | Rubber-band select with Shift = union / Ctrl = difference (plain set ops, **not** region grow); ground removal by **z-threshold + RANSAC plane** (not box snapping). **Absent: interpolation, tracking, copy-paste, auto-save, track management, ground snapping, magic wand, per-class dimensions, review queue** | — | — | [repo](https://github.com/springzfx/point-cloud-annotation-tool) |
| **Open3D-ML** | **Ships no labelling GUI at all** — verified against the full repo tree (326 entries, zero gui/editor/brush/paint paths) | — | n/a | [Open3D-ML](https://github.com/isl-org/Open3D-ML) |
| **`mark220620/pointcloud_annotator`** | The one real **Open3D `visualization.gui`** labeller found: per-point 16-class nuScenes brush, **auto-save on frame change**, keyboard frame navigation. **0 stars, no LICENSE file (treat as all-rights-reserved), single-day upload** | Open3D GUI + brush | **No** | [repo](https://github.com/mark220620/pointcloud_annotator) |
| **MSALT** (`LiDAR-Motion-Segmentation/MSALT`) | The only modern full "smart" stack found: **SAM 2 assist**, "**linear propagation and Copy-to-Next**", batch box editing | needs trained weights (`sam2_hiera_large.pt`, `yolo26l.pt`) | **Yes** | [repo](https://github.com/LiDAR-Motion-Segmentation/MSALT) |
| **anylabeling / X-AnyLabeling** | **Nothing relevant — no 3D at all.** Shapes are `polygon, rectangle, point, line, circle, linestrip`; the `cuboid` shape is a **2.5D image-space box** (8 image vertices + a `depth_vector`), not metric 3D | — | n/a | [anylabeling](https://github.com/vietanhdev/anylabeling), [X-AnyLabeling](https://github.com/CVHub520/X-AnyLabeling) |
| anylabeling | Stealable **2D-only** patterns: checked/unchecked **review queue** (`Ctrl+Alt+K`, jump to next/prev unchecked, `checked::0` search filter) and a **model-plugin architecture** (`Model` base + `Meta` capability declaration + YAML registry + manager with LRU cache and next-file preload) | — | Pluggable | [user guide](https://xanylabeling.com/docs/x-anylabeling/user_guide) |
| **3D-Annotator** (OSS, KIT / Fraunhofer IOSB; Django + React + three.js) | **Rich point/mesh painting toolkit, but no boxes** — 3D-Brush (movable sphere paints everything within its radius), Lasso (freeform, foreground *and* background), Polygon, point-cloud Brush ("selects and labels all points within its boundary, **regardless of their depth**"), one-click Fill, plus **label locking** ("points and triangles that are already labeled with that label cannot be overwritten") and per-label visibility/opacity | screen-space region painting onto point labels | **No** | [README](https://github.com/3D-Annotator/3D-Annotator) |
| 3D-Annotator | **What it does *not* have — verified from its own roadmap** | "add support for bounding boxes" and "add models for pre-annotation" are both **unchecked** in Future plans; "add support for classification" also unchecked. It is semantic segmentation only, though "If there are existing labels, such as those from a pre-annotation task, they can be uploaded as a starting point" | n/a | [README](https://github.com/3D-Annotator/3D-Annotator) |
| **`anno3d`** (the format, not a tool) | Compact per-point label sidecar | `# ANNO3D-UTF-8` magic header + metadata + `data_start` + `label <class> <count>` index blocks; UTF-8, binary and PNG targets | **No** | [UTF-8 v2 spec](https://github.com/3D-Annotator/3D-Annotator/blob/main/frontend/src/anno3d/v2/targets/utf8/Specification.md) |
| **ActiveAnno3D** (`walzimmer/active-anno-3d`) | **Active-learning selection loop for 3D detection** — picks which frames/objects a human should label next, based on model confidence | deep ensemble / uncertainty scoring feeding the 3D BAT UI | **Yes** | [`active-anno-3d`](https://github.com/walzimmer/active-anno-3d), [3D BAT changelog](https://github.com/walzimmer/3d-bat) |
| **PCAT** — ⚠️ **two unrelated projects share this name; disambiguate.** `crayonsea/PCAT` (**PyQt5** + pptk) | **The closest architectural sibling found — a PyQt5 point-cloud labeler** with semantic labelling first, then **per-class instance labelling**. Rubber-band point selection where Ctrl / Ctrl-Shift **adds to / removes from** the current selection and right-click clears it; double-click moves the viewpoint to the point under the cursor; `[` / `]` toggles the displayed attribute (RGB ↔ Label); **`z` toggles overwrite vs non-overwrite labelling**, so already-labelled points can be protected | custom classes in `labels.json` (name, colour, id); load/export hooks in `file_utils.py` | **No** | [README](https://github.com/crayonsea/PCAT) |
| PCAT (`crayonsea/PCAT`) | **Caveats that disqualify it as a dependency** | Python 3.7, **Windows 10 only** (depends on `pywin32`, explicitly cannot run on Linux); author's own note "Demo项目，请自行魔改" (demo project, modify it yourself); **no LICENSE file** | n/a | [README](https://github.com/crayonsea/PCAT) |
| **PCAT** (`halostorm/PCAT_open_source` — **a different project**) | The only surveyed tool shipping **3D cuboids *and* polylines (kerb/lane) *and* a ground polygon** together, plus **heuristic, non-model ground auto-generation** (`F2`, "auto-generates 95% of the ground"), auto-save on file switch, and keyboard review nav (`Shift+N` / `Shift+P`). 437★ | ROS / Rviz / PCL; **Python 2.7**, **no LICENSE file anywhere in the tree** | **No** (heuristic ground) | [repo](https://github.com/halostorm/PCAT_open_source) |
| **BuildFrame** (`zzxy666/BuildFrame`) | **A labelCloud fork that replaced boxes with polylines — proof this is feasible in this codebase.** Based on labelCloud (GPLv3+), it **removes the 3D bounding-box annotation** and **adds a roof point/line drawing mode** with live preview and closure detection, saves outlines as **OBJ (vertices + lines)**, adds **LAS/LAZ reading**, fixes the large-cloud depth-buffer problem via near/far plane adjustment, adds standard-view hotkeys, and adds **ground filtering** | direct fork of labelCloud | **No** | [README](https://github.com/zzxy666/BuildFrame) |
| **Semantic Segmentation Editor** (**Hitachi** Automotive & Industry Laboratory — **not** Halmstad, and **not** Open3D) | Web-based 2D **and 3D** labelling; point-cloud labelling of ~1M-point clouds; supports PCD (ASCII/binary/binary-compressed) and RGB point clouds. **Its "Magic Tool" is a 2D *bitmap* threshold, not a 3D magic wand** | Meteor + React + Paper.js + three.js | **No** | [README](https://github.com/Hitachi-Automotive-And-Industry-Lab/semantic-segmentation-editor), **MIT** |
| **Annofab `3dpc` editor** (Japanese, commercial) | 3D editor with **bounding box** + **segment** annotation types, a **tracking panel**, inspection comments and a **ruler**; two features are exposed only through the **`anno3d` CLI**: **preset cuboid size** and **annotation area** | web editor + `annofab-3dpc-editor-cli` on PyPI | No (tracking panel model **UNVERIFIED**) | [3D editor index](https://annofab.readme.io/docs/3dpc-editor), [`annofab-3dpc-editor-cli`](https://github.com/kurusugawa-computer/annofab-3dpc-editor-cli) |
| **KITTI-360 Annotation Tool** | The tool used to annotate KITTI-360; raw 2D/3D annotation over LiDAR + images. Has **real auto-save** and a **real human review queue** — `taskLists.txt` with an `Editable=0/1/2` status per task | CherryPy + jinja2 + sqlite3 server, JS + WebGL front end; **MIT** | No | [repo](https://github.com/autonomousvision/kitti360LabelTool) |
| **PointAtMe** (VR) | Box annotation of whole **sequences** inside VR (Oculus Rift + Touch); the output already carries a **track** id plus position, quaternion orientation and scale | VR / game engine | No | [repo](https://github.com/dfki-ric/pointatme) |
| **`lidarstudio/PointCloud-Label`** (Chinese) | **Profile / cross-section editing instead of 3D box picking** | annotate 电力塔 / 地线 / 电力线 / 其他 (power tower / ground wire / power line / other) by editing 2-D **profiles (剖面编辑)** in Lidar Studio, explicitly to produce semantic-segmentation training data | **No** | [PointCloud-Label](https://github.com/lidarstudio/PointCloud-Label), [Lidar-Studio](https://github.com/lidarstudio/Lidar-Studio) |
| **TerraScan** (proprietary; powerline tools are **"Not Lite"**) | **Purpose-built powerline annotation workflow** — see the next subsection | catenary least-squares vectorization + manual 3-click catenary + attachment checking | No | [Powerlines](https://www.terrasolid.com/guides/tscan/intropowerlines.html) |

**Licensing / tier reality, stated plainly:** Xtreme1 is genuinely open source (LF AI & Data sandbox);
BasicAI is commercial with on-prem **from $6,600/y** and its free tier is a cloud plan, not a
self-hosted one ([pricing](https://www.basic.ai/basicai-data-annotation-platform/3d-lidar-point-cloud-annotation-tool));
Supervisely's platform is **not** open source and self-hosting is Enterprise with a licence key
([pricing](https://supervisely.com/pricing/)); Segments.ai is a commercial cloud; 3D BAT is
source-available under a **UC Regents non-commercial licence** ("Permission to make commercial use of
this software may be obtained by contacting…", [LICENSE](https://github.com/walzimmer/3d-bat));
anylabeling and X-AnyLabeling are **GPL-3.0** and X-AnyLabeling has **migrated PyQt5 → PyQt6** in
v4.0.0-beta.1, so its UI code cannot be lifted into a PyQt5 tool even ignoring the licence.
Whether each individual Supervisely 3D AI feature is in the free cloud tier is **UNVERIFIED**.

**Baseline re-verification (labelCloud `master`).** A fresh source pass confirms the gap is real and not
a rebuild risk: a grep for `fit`, `oriented_bounding_box`, `create_from_points`, `interpolat`, `track`,
`paste`, `snap`, `region_grow`, `dbscan` and `cluster` over **all non-test `.py` files returns nothing**.
Auto-save *is* real (`controller.py` L64–66 `next_pcd` → `self.save()`, also L82–83, L91, L276), as is
the `propagate_labels` config read at L74, and `AlignMode` ("span a triangle with three points on the
plane that serves as the ground") — but note that AlignMode rotates the **point cloud** so the floor is
z-up; it does **not** snap boxes to the ground. So box fitting, interpolation, tracking, snapping and
region growing are genuinely absent rather than duplicated elsewhere
([`controller.py`](https://github.com/ch-sa/labelCloud/blob/master/labelCloud/control/controller.py),
[`alignmode.py`](https://github.com/ch-sa/labelCloud/blob/master/labelCloud/control/alignmode.py)).

### Power-line & pole specific

The earlier "Model-free geometry" section already covers Open3D's OBB, PCL cylinder/RANSAC,
`pyransac3d`, Patchwork++/PDAL ground filters, `filters.covariancefeatures` verticality, and Gribov &
Duri's catenary paper. This subsection adds only what is new, and leads with the finding that
contradicts that section's negative.

**1. TerraScan ships the missing feature: a complete, documented power-line annotation UI.** It is
proprietary and *paid* — every powerline tool is marked **"Not Lite"**, i.e. absent from free TerraScan
Lite — but the user guide publishes the algorithm and the full parameter list, which makes it the
domain's reference design. TerraScan splits the work into three toolboxes (Vectorize Wires, Vectorize
Towers, View Powerline) and documents an 11-step workflow: classify ground → classify above-ground →
classify *by centerline* → classify *by echo* → Place Tower String → **Detect Wires (automatic)** →
**Place Wire String (manual fallback)** → Check Wire Attachments → Assign Wire Attributes → Place Tower
→ Find Danger Objects → reports
([Powerlines](https://www.terrasolid.com/guides/tscan/intropowerlines.html),
[Vectorize Wires toolbox](https://www.terrasolid.com/guides/tscan/tboxvectorizewires.html)).

**[Detect Wires](https://www.terrasolid.com/guides/tscan/tooldetectwires.html)** is a catenary
least-squares fit: it "searches points along a catenary curve… least squares fitting for both, the xy
line equation and the elevation curve equation of the catenary". Its parameters are the distilled
engineering knowledge, and three of them are the answer to the elongated-object problem:

| Parameter | Documented meaning | Why it matters here |
|---|---|---|
| **Max gap** | "maximum gap between consecutive laser points on a wire" | **A wire is a sparse chain, not a dense blob.** Connectivity must be defined by a *gap along a fitted curve*, not by Euclidean distance — which is exactly why isotropic DBSCAN fragments conductors. The guide warns to start small and per-segment because "the chance of false detections increases" with a large value |
| Linear / Elevation tolerance | separate tolerances for the XY line fit and the Z curve fit | the wire is fitted in two decoupled parts, which avoids the ill-conditioning of a 5-parameter free-orientation catenary |
| **Ignore points** | "Distance from tower within which points are ignored for wire detection. Points close to the tower can be from tower structures and should be ignored when determining the mathematical shape of the wire" | **In a pole+wire scene the points near the pole are the *wrong* points for fitting the wire.** No other source surveyed states this |
| Max offset / Max angle | corridor half-width from the tower string; max wire-to-string angle | prunes vegetation returns |
| Require | min points on a single wire, 3–999 | sparsity guard |
| Minimum / Maximum | bounds on the catenary constant to accept a wire | rejects implausible fits |

**[Place Wire String](https://www.terrasolid.com/guides/tscan/toolplacecatenarystring.html)** is the
"click a few points → fit" primitive the earlier section said did not exist: a wire is defined by
**three curvature points** (plus optional separate start/end points, which affect length but not
shape), with three options that together are the wire analogue of SUSTechPOINTS' `Ctrl`+drag fit:

- **Snap to** — "the three curvature points are snapped to the closest laser points in a given class.
  This lock is normally on."
- **Fit using** — "the wire string is fitted to laser points in the given class within the given
  tolerance."
- **Classify to** — "laser points within the given radius around the wire string are classified into
  the given class."

That is the whole feature — *click roughly → snap to points → refit → paint the enclosed points* — and
it is the correct interaction for a wire, where dragging a 9-DoF box never is.

**[Find Powerline Wires](https://www.terrasolid.com/guides/tscan/toolfindpowerlinewires.html)** is the
tower-free variant for dense MLS or consistently-sampled ALS, and "searches only wires following
catenary shape". Its distinctive parameter is **Wires apart** — "Distance threshold for picking
neighboring points. Should be **larger than point spacing but smaller than distance between parallel
wires**" — a neighbour radius constrained by two *physical* scales instead of tuned blind. Also
`Tolerance from wire`, `Min wire length`, `Max angle`, and `Limit result by height from ground` with a
`Min distance` "slightly lower than the actual lowest wire position". TerraScan further distinguishes
**Merge Wires** (no tower between) from **Connect Wires** (tower between) — a distinction any
single-linkage chainer gets wrong at every pylon. And **Check Wire Attachments** validates and adjusts
catenary attachment points at towers: the wire-specific form of the keyframe-anchor idea, where a few
human-confirmed *endpoints* regenerate the whole conductor.

**2. Datasets with real conductor + pole point labels — two are usable today.** The earlier section
cites TS40K; these are the rest, and they are better for *pretraining* because two are permissively
licensed.

| Dataset | Modality | Classes that matter | Licence / access |
|---|---|---|---|
| **[DALES 2](https://huggingface.co/datasets/mbendjilali/DALES-2)** | ALS, LAZ, ~5.2 GB | per-point **semantic + instance**, 15 classes incl. `Powerline`, `Utility pole`, `Light pole`, `Traffic pole` | **MIT, not gated** — the only "download today" option; read via the HF mirror |
| **[ECLAIR](https://github.com/SharperShape/eclair-dataset)** | ALS (helicopter), 582 M pts | 11 classes incl. **Transmission Wires, Distribution Wires, Poles, Transmission Towers**; 624 human-verified + 622 pseudo-label tiles | repo MIT, **dataset CC BY-NC-SA 4.0 (non-commercial)**, Google-Form access |
| **[GridNet-HD](https://huggingface.co/datasets/heig-vd-geo/GridNet-HD)** | UAV LiDAR + co-registered RGB, 2.449 B pts | 12 groups incl. **Pylon, Conductor cable, Structural cable, Insulator** | **CC-BY-4.0**, ~170 GB, **test labels withheld** |
| **[Zenodo 7701809](https://zenodo.org/records/7701809)** | ALS (Dutch AHN3, 10 areas) | hand-labelled per-point, 6 classes incl. `powerline` | **CC-BY-4.0, direct download** — 528 MB labelled + 546 MB raw |
| **[TTPLA](https://github.com/R3ab/ttpla_dataset)** | aerial **RGB, not LiDAR** | transmission towers + power lines, COCO polygons | Apache-2.0; useful only as a 2D pretraining set |

DALES 2 and ECLAIR are the only two that are both permissively licensed *and* carry wires **and** poles
point-wise. Verified negatives from the same sweep: **no LiDAR power-line data on Kaggle or Zenodo**,
no downloadable State Grid / Tianchi / CCF / AI Studio 电力线 point-cloud set, and **no "University of
Ottawa PLD" and no "SFU powerline LiDAR"** — both appear to be literature misattributions.

**3. Adaptable code not already listed above.**

- **[`zwshi-pku/3DLiDAR`](https://github.com/zwshi-pku/3DLiDAR)** — Apache-2.0, MATLAB + C++ (mex):
  linear-feature candidate extraction → clustering → **catenary model fitting and densification**;
  driver `demo_extract_powerline.m`, published parameters `radius=0.5, angleThr=10, LThr=0.98`;
  Chinese-authored (PKU). This is the closest thing to a reference *implementation* of the catenary
  pipeline (the earlier section cites Gribov & Duri's *paper*). MATLAB is the adoption cost.
- **[`liuxinren456852/powerline-detection-from-3D-LiDAR-point-clouds`](https://github.com/liuxinren456852/powerline-detection-from-3D-LiDAR-point-clouds)**
  — **XGBoost + Hough Transform** on the Toronto-3D MLS dataset. A different, non-catenary route to
  the same problem. Repo README verified via search; contents **UNVERIFIED**.
- **PCL `SACMODEL_STICK`** — a line model with user-given min/max width, i.e. a ready-made
  conductor/ribbon primitive, alongside `SACMODEL_LINE`, `SACMODEL_PARALLEL_LINE` and
  `SACMODEL_CYLINDER` ([sample consensus](https://pointclouds.org/documentation/group__sample__consensus.html)).
  C++ only; Python bindings are unmaintained.
- **[CSF](https://github.com/jianboqi/CSF)** — Apache-2.0, C++, maintained; `pip install
  cloth-simulation-filter`, Python API `CSF.CSF()` → `do_filtering(ground, non_ground)` returning index
  vectors. This is the implementation PDAL's `filters.csf` wraps.
- **PDAL specifics:** there is **no powerline-specific filter** (verified against the full filter
  index), and **`filters.monge` does not exist** (HTTP 404). [`filters.cluster`](https://pdal.io/en/stable/stages/filters.html)
  (Euclidean → `ClusterID`) is the workhorse for splitting a corridor into per-object segments before
  any per-wire test.
- **Pole primitives:** [`trimesh.bounds.minimum_cylinder`](https://trimesh.org/trimesh.bounds.html) →
  `{radius, height, transform}` (MIT) is the right enclosing primitive for a rotationally symmetric
  pole; **OpenCV `minAreaRect`** (rotating calipers — verified from `modules/imgproc/src/rotcalipers.cpp`)
  gives the BEV minimum-area rectangle for a pole footprint or crossarm.
- **Ground removal:** **LAStools `lasground`/`lasclassify` are not open source** — free only for
  non-profit, non-military personal or educational use, binaries only
  ([licence text](https://lastools.github.io/download/LICENSE.txt)), so they are unusable in a
  commercial pipeline. Use PDAL `filters.smrf`/`filters.csf` or CSF directly.

**4. Elongated thin objects — the representation question.** The earlier section establishes *why* the
upright yaw-only box is structurally wrong for a wire (its long axis is not ground-parallel) and why
PCA cannot recover a wire's **roll** (λ₁ ≫ λ₂ ≈ λ₃ leaves the cross-section axes degenerate). What
this survey adds is which representations are actually in production use, in increasing order of fit:

1. **Oriented box along the principal axis** — what labelCloud can express and all its exporters
   understand. Fit with `get_oriented_bounding_box` or a minimum-volume OBB. Two known traps already
   documented in this file: `min_boundingbox_dimension` (PR #181 would raise it to `0.1`, making a wire
   unrepresentable) and `z_rotation_only = True`. In this project's own convention the long axis
   already lives in `dimensions.width` (`recon-polewire.md` §B.5).
2. **Minimum-area rectangle in BEV plus a height** (`cv::minAreaRect`) — cheaper and far more stable
   than a full 3-D OBB precisely because the wire's roll is not identifiable. Good default when the
   export must stay a box.
3. **Polyline / catenary linestring — what the field actually uses.** TerraScan vectorizes wires as
   **catenary line strings, never boxes**; Supervisely and BasicAI both ship 3-D polylines and both name
   linear infrastructure (pipes, power lines) as the use case; the TTPLA repack on Hugging Face ships
   wire labels as **polylines**, not masks. The earlier section's negatives about *annotation-tool*
   spline support still stand — but the *representation* is well established.

The practical consequence for a box-export tool: **annotate the wire internally as a
polyline/catenary, and derive the box as its OBB at export time.** That keeps the fast, correct
interaction (3 clicks + refit) while leaving the on-disk schema unchanged.

**5. A second non-obvious option: profile / cross-section editing.** The Chinese
[`lidarstudio/PointCloud-Label`](https://github.com/lidarstudio/PointCloud-Label) project annotates
power data into 电力塔 / 地线 / 电力线 / 其他 by **editing 2-D profiles (剖面编辑)** in Lidar Studio,
explicitly to produce semantic-segmentation training data. For a corridor scanned along a vehicle path
this is a much cheaper interaction than 3-D box dragging — but it produces *point* labels, not boxes,
so it complements the box workflow rather than replacing it.

### Verdicts

1. **Steal Segments.ai's "merged point cloud view for static objects"** — because a pole or wire is
   thin and partially occluded in any single 0.5 s frame, and stacking the frames a *static* object
   appears in yields one dense object you fit **once** then propagate; no model, and it attacks
   "box-by-box adjustment" at its root
   ([docs](https://docs.segments.ai/how-to-annotate/label-3d-point-clouds/merged-point-cloud-view-for-static-objects)).
2. **Steal dimension control at *both* levels — Segments.ai's "same-dimensions track constraint" plus
   per-category default dimensions, and BasicAI's `Fixed` mode and class `Standard` l/w/h** — because
   poles and wires are rigid, so l/w/h should be born correct at creation *and* frozen for the whole
   track with only pose interpolated; this is the same insight as SUSTechPOINTS' `MaFilter` freezing
   scale, and it makes the annotation immune to per-frame size drift
   ([Segments.ai track constraint](https://docs.segments.ai/how-to-annotate/label-sequences-of-data/use-track-ids-in-sequences),
   [Segments.ai defaults](https://docs.segments.ai/how-to-annotate/label-3d-point-clouds/3d-point-cloud-cuboid-interface),
   [BasicAI](https://docs.basic.ai/docs/object-detection-tracking), [BasicAI classes](https://docs.basic.ai/docs/class))
   — **but keep `min_boundingbox_dimension` at `0.01`**, since a 10 cm minimum edge makes a wire
   unrepresentable.
3. **Steal the TerraScan wire interaction: 3 clicks → snap to points → refit → classify points within
   radius** — because it is the wire-specific primitive SUSTechPOINTS' box fit does not provide, it is
   fully documented, it needs no model, and it is a few dozen lines of numpy; implement it as a
   catenary/polyline and derive the OBB only at export
   ([TerraScan](https://www.terrasolid.com/guides/tscan/toolplacecatenarystring.html)) — and note that
   **BuildFrame already proves polyline drawing works inside a labelCloud fork**, so the UI risk is
   lower than it looks ([BuildFrame](https://github.com/zzxy666/BuildFrame)).
4. **Adopt TerraScan's three wire parameters rather than inventing your own** — `Max gap` for
   connectivity, `Wires apart` bounded below by point spacing and above by inter-wire spacing, and
   `Ignore points` near the tower — because these encode that a wire is a sparse chain whose fit must
   exclude the pylon it attaches to, and getting them wrong is what makes a naive detector produce
   garbage ([Detect Wires](https://www.terrasolid.com/guides/tscan/tooldetectwires.html),
   [Find Powerline Wires](https://www.terrasolid.com/guides/tscan/toolfindpowerlinewires.html)).
5. **Steal the auto-refit-on-release interaction — Segments.ai's `Q`, Xtreme1's `U`, and `springzfx`'s
   `adjustToAnchor()` firing on mouse-release** — because all three reduce "make this box correct" to a
   single gesture, and `springzfx` is the proof that the *fully automatic* variant (select points →
   release → box refits, orientation preserved) is model-free and shippable; the geometry is a
   rotated-AABB refit this codebase can already do with Open3D
   ([Segments.ai](https://docs.segments.ai/how-to-annotate/label-3d-point-clouds/3d-point-cloud-cuboid-interface),
   [Xtreme1](https://docs.xtreme1.io/xtreme1-docs/product-guides/lidar-annotation-tool),
   [`Annotaion.cpp`](https://github.com/springzfx/point-cloud-annotation-tool/blob/master/src/Annotaion.cpp)).
6. **Steal the "one object across many frames" view (Segments.ai batch mode, 3D BAT sequence mode,
   SUSTechPOINTS multi-frame edit)** — because Segments.ai and SUSTechPOINTS independently conclude that
   object-by-object beats frame-by-frame, and labelCloud's current UI (prev/next frame + `1`–`9` box
   select, no track concept) actively enforces the slow pattern
   ([Segments.ai](https://docs.segments.ai/how-to-annotate/label-3d-point-clouds/batch-mode-for-dynamic-objects)).
7. **Steal CVAT's one genuinely better 3-D detail — shortest-arc interpolation of the three rotation
   angles** — because SUSTechPOINTS interpolates yaw as a scalar with only a π/2 guard, and CVAT's
   `findAngleDiff` (normalise to [0,2π) → shortest arc → wrap to (−π,π]) is ~10 lines that removes a
   whole class of box flips ([`cuboid-track.ts`](https://github.com/cvat-ai/cvat/blob/develop/cvat-core/src/annotations-objects/cuboid-track.ts)).
8. **Ignore CVAT, Supervisely, anylabeling and `springzfx/point-cloud-annotation-tool` as sources of
   code or dependencies** — CVAT's 3-D workspace has no AI, no snap and no review mode by its own docs;
   Supervisely's good 3-D assist features are commercial-only behind an Apache-2.0 *client* SDK;
   anylabeling has no point-cloud support at all and is GPL-3.0 + PyQt6; springzfx has been
   unmaintained since 2019 and is C++/PCL/VTK. Take each as a **specification**, not as code
   ([CVAT](https://github.com/cvat-ai/cvat/blob/develop/site/content/en/docs/qa-analytics/manual-qa.md),
   [Supervisely](https://supervisely.com/pricing/), [anylabeling](https://github.com/vietanhdev/anylabeling),
   [springzfx](https://github.com/springzfx/point-cloud-annotation-tool)).
9. **Ignore `anno3d` as a box-annotation reference and steal the "don't clobber my labels" toggle
   instead** — because the CLI `anno3d` only configures someone else's commercial editor
   (preset cuboid size, annotation area) and the *format* `anno3d` holds per-point classes with no box
   concept, while **two unrelated tools independently ship a protected-label mode** — 3D-Annotator's
   label **locking** ("already labeled … cannot be overwritten") and PCAT's **`z` overwrite /
   non-overwrite** toggle — which is the cheapest possible guard against an assist feature destroying
   human edits ([annofab-3dpc-editor-cli](https://github.com/kurusugawa-computer/annofab-3dpc-editor-cli),
   [anno3d spec](https://github.com/3D-Annotator/3D-Annotator/blob/main/frontend/src/anno3d/v2/targets/utf8/Specification.md),
   [3D-Annotator](https://github.com/3D-Annotator/3D-Annotator), [PCAT](https://github.com/crayonsea/PCAT)).
10. **Sequence the work as pole-correction UX first, wire detection second, and pretrain on DALES 2
    rather than waiting for your own frames** — because wires are near-solved in the benchmarks while
    **distribution poles sit at F1 0.69–0.74 / IoU 51–59 %** (DALES agrees: KPConv poles 0.750 vs power
    lines 0.955), and DALES 2 is MIT, ungated and carries both classes point-wise with instance IDs
    ([ECLAIR](https://github.com/SharperShape/eclair-dataset),
    [DALES](https://arxiv.org/abs/2004.11985), [DALES 2](https://huggingface.co/datasets/mbendjilali/DALES-2)).

### Not verified / explicitly unconfirmed

- **~~No repo implementing "click a point → fit an oriented box" was found anywhere outside
  SUSTechPOINTS.~~ CORRECTED — `springzfx` does implement it.** `Annotation::adjustToAnchor()`
  (`Annotaion.cpp` L117–150, wired to `EndInteractionEvent` at L109 via
  `vtkBoxWidgetCallback.cpp` L37–40) refits a box's centre and extents to the anchor points captured
  from a rubber-band selection, keeping the orientation the user set, and fires automatically on
  mouse-release. It is C++/VTK rather than Python, and its **orientation is user-supplied rather than
  PCA-derived**, but the interaction pattern is the one described and it is model-free.
  **Still unverified:** the *full* feature — a click that both selects a cluster *and* derives an
  oriented box from it with no user-supplied rotation — was not found in reusable Python.
  The building blocks are verified to exist (`VisualizerWithEditing` picking,
  `get_minimal_oriented_bounding_box`, `trimesh.oriented_bounds`), and the reason tools lack the
  feature appears to be UX/undo/rotation plumbing rather than the algorithm. TerraScan implements the
  wire analogue, in a proprietary product only.
- **`zwshi-pku/3DLiDAR` was verified only at README + LICENSE level** — its MATLAB sources were not run,
  and the parameter values quoted are the author's published defaults, not measured here.
- **LiDAR360 / LiPowerline (数字绿土) and DJI Terra** are Chinese commercial power-line suites that
  advertise tower coordinates, **conductor catenary curves (导线悬垂曲线)** and conductor spacing
  ([DJI Terra whitepaper](https://terra-1-g.djicdn.com/263b7ee0f1fe477c91b7ca44348166fe/DJI%20Terra/%E7%99%BD%E7%9A%AE%E4%B9%A6/%E5%A4%A7%E7%96%86%E6%99%BA%E5%9B%BE%E6%93%8D%E4%BD%9C%E7%99%BD%E7%9A%AE%E4%B9%A6V5.1.pdf));
  both LiPowerline product PDFs returned **HTTP 404**, so their feature details are **UNVERIFIED**.
- **TerraScan `Check Wire Attachments`, `Merge Wires`, `Connect Wires`** were verified as existing with
  descriptions, but their parameter lists were not read in full.
- **Which model powers BasicAI's "AI-assisted boxing"** is undocumented. **X-AnyLabeling keyframe
  interpolation** — nothing found. **Supervisely auto-save** and **free-tier gating of individual 3D AI
  features** — not documented.
- **Segments.ai `Q` auto-adjust semantics conflict between two paragraphs on the same page** (keeps
  orientation vs updates rotation; filters outliers vs does not) — behaviour **UNVERIFIED**.
- **TowerDataset licence** (HF gate returns 401), **Eka-Korn dataset licence**, **InsPLAD licence**,
  and the **DALES *original* access route** (both the UDayton redirect and the old IEEE DataPort page
  are dead — use DALES 2 instead) are all **UNVERIFIED**.
- **No railway catenary point-cloud dataset was found anywhere**; RailSem19's catenary class and
  OSDaR23's licence are **UNVERIFIED**.
- **Chinese platform coverage is a gap:** no primary-source landing page could be verified for a
  downloadable 电力线 point-cloud dataset on Tianchi / State Grid / CCF / Baidu AI Studio / ModelScope.
- **Annofab `3dpc` details.** The doc page **titles and their grouping** are verified from the sidebar
  (bounding box + segment types, tracking panel, ruler, and "Cuboidの規定サイズ" / "アノテーション範囲"
  under "CLIで設定する機能"), but the page **bodies are JS-rendered and could not be read** — so what
  "preset cuboid size" and "annotation area" actually do is **UNVERIFIED**, as is the licence of
  `annofab-3dpc-editor-cli` and whether the tracking panel is model-based or manual.
- **PCAT is three things, and two of them are unrelated annotation tools** — `crayonsea/PCAT` (PyQt5 +
  pptk, Windows-only, per-point semantic only) and `halostorm/PCAT_open_source` (ROS/Rviz, 437★, the one
  with cuboids + polylines + heuristic ground) are **different projects with the same name**; a third
  ROS/Ubuntu variant is published by "WenwenDu". **Neither PCAT repo has a LICENSE file** (treat as
  all-rights-reserved), and both are effectively dead — Python 2.7 for halostorm.
- **PointAtMe, KITTI-360 Annotation Tool, KITTI 3D Ground Truth Annotator and the Hitachi Semantic
  Segmentation Editor** were verified at README level only; licences were checked for the Hitachi tool
  (**MIT**) and KITTI-360 (**MIT**) and **not** for the others. None of them ships a box-fitting or
  interpolation assist worth
  citing beyond what is in the table.
