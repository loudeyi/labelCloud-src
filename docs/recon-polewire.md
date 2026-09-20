# Recon: pole/wire auto-pre-annotation toolchain → embedding into labelCloud

Scope: reconnaissance only. Nothing outside `/home/tyy/DSH-WS/.scratch/` was modified.
Host: `x86_64`, no `nvidia-smi`, no `torch` in any interpreter on this box.
labelCloud venv: `/home/tyy/DSH-WS/labelcloud-hzh` (Python 3.8.10, `labelCloud 1.1.1` installed at
`lib/python3.8/site-packages/labelCloud`, `numpy 1.24.4`, `scipy 1.10.1`, `PyQt5`, `PyOpenGL`, `open3d` all import cleanly).

---

## A. polewire API surface

Package root: `/home/tyy/DSH-WS/tools/pole_wire_autolabel/` (NOT installed; not on any `sys.path` by default).
Third-party imports across the whole package: **`numpy` only** for `boxes/pcd_io/labels/pipeline`,
**`numpy` + `scipy`** for `ground/poles/wires`, **`matplotlib`** (lazy, inside the function) for `visualize`.
`scipy` is used as `scipy.spatial.cKDTree` (poles, wires) and `scipy.ndimage` (ground, guarded by `try/except`).
No torch, no GPU, no file I/O other than reading `.pcd` / reading-writing `.json`.

### A.1 `polewire/__init__.py` — the public façade

```python
from .boxes import bev_iou, bev_iou_poly, corners, points_in_box, rot_matrix, nms
from .ground import estimate_ground
from .labels import box, read_labels, write_labels, write_classes_json
from .pcd_io import read_pcd
from .pipeline import Config, find_pcds, process_directory, process_frame
from .poles import PoleParams
from .wires import WireParams
```

Note: `import polewire` transitively imports `pipeline → poles, wires → scipy`. There is **no** way to get
just the JSON writer without pulling scipy in (import `polewire.labels` directly to avoid it).

### A.2 `polewire/pcd_io.py` — point-cloud I/O (numpy only)

| function | signature | notes |
|---|---|---|
| `read_pcd` | `read_pcd(path, fields=("x","y","z")) -> np.ndarray` | returns `(N, len(fields))` **float64**. Handles `DATA ascii` and `DATA binary`. Raises `NotImplementedError` for `binary_compressed`. |
| `write_pcd_ascii` | `write_pcd_ascii(path, points) -> None` | debug helper; writes `FIELDS x y z`, `DATA ascii`. |

Relevant for integration: `read_pcd` parses the same file labelCloud already loaded with Open3D, so an
in-process caller should **not** re-read the file (see §C.6).

### A.3 `polewire/labels.py` — LabelCloud JSON (numpy only)

| function | signature | notes |
|---|---|---|
| `box` | `box(name, center, dims, rot=(0.0,0.0,0.0)) -> dict` | the internal box record: `dict(name=str, center=np.ndarray(3), dims=np.ndarray(3), rot=np.ndarray(3))`. `dims = (length, width, height)`, `rot` = **degrees**. |
| `read_labels` | `read_labels(path) -> List[dict]` | understands both `centroid/dimensions/rotations` and an 8-corner `vertices` encoding (converted back to centre/dims/euler). |
| `write_labels` | `write_labels(path, pcd_path, folder, objects) -> None` | writes `{folder, filename, path, objects[]}`; **atomic** (`path + ".tmp_write"` then `os.replace`); every number rounded to 8 decimals (`_round(v, nd=8)`); `indent="\t"` + trailing newline. `path` field = `os.path.abspath(pcd_path)`. |
| `write_classes_json` | `write_classes_json(directory, class_names) -> str` | ⚠️ **writes a flat JSON array** `["pole","wire"]` — see the incompatibility in §C.7. |
| `load_classes_json` | `load_classes_json(directory) -> Optional[list]` | reads back that flat array. |

### A.4 `polewire/boxes.py` — oriented-box maths (numpy only)

Convention documented at the top of the file, identical to labelCloud's:

```python
# local x = length, local y = width, local z = height
# rotations = extrinsic XYZ euler angles in degrees  ->  R = Rz @ Ry @ Rx
```

| function | signature |
|---|---|
| `rot_matrix` | `rot_matrix(rx, ry, rz) -> (3,3)` |
| `rot_z` | `rot_z(rz_deg) -> (3,3)` |
| `corners` | `corners(box) -> (8,3)` world corners |
| `points_in_box` | `points_in_box(points, box, margin=0.0) -> bool mask` |
| `local_coords` | `local_coords(points, box) -> (N,3)` |
| `bev_iou` | `bev_iou(box_a, box_b, res=0.1, max_cells=4_000_000) -> float` — rasterised, auto-coarsens `res` |
| `bev_iou_poly` | `bev_iou_poly(box_a, box_b) -> float` — Sutherland–Hodgman polygon clipping |
| `nms` | `nms(boxes, scores, radius=1.2) -> List[box]` — greedy centre-distance NMS |

### A.5 `polewire/ground.py` — per-frame ground model (numpy + optional scipy.ndimage)

```python
@dataclass
class GroundModel:
    x0: float; y0: float; cell: float
    z: np.ndarray                                  # (nx, ny) height map
    plane: np.ndarray = field(default_factory=lambda: np.zeros(3))
    kind: str = "map"                              # "map" | "plane"

    def at(self, points): ...        # ground z at each point
    def height(self, points): ...    # z - ground  (height above ground, metres)
    def ground_z(self, x, y) -> float
```

```python
def estimate_ground(points, cell=1.5, method="mode", quantile=2.0, bin_size=0.3,
                    min_pts=3, smooth=3, erode_size=1, spike_meters=2.0,
                    fill_iters=60, min_cells=8) -> GroundModel
```

Docstring advertises three methods: `"median3"` (described as *default* in the docstring), `"mode"`
(densest z band), `"quantile"`. **The actual default in the signature is `"mode"`**, and
`pipeline.Config.ground_method` is also `"mode"`; only the docstring says `median3`. Frames with
`< 200` points or `< min_cells` filled cells fall back to a robust global plane (`kind="plane"`).

### A.6 `polewire/poles.py` — pole detection (numpy + scipy.spatial.cKDTree)

`PoleParams` (all defaults):

```python
cell=0.4  gap=3  min_span=2.5  min_pts=8  max_radius=3.0  max_cells=400
min_cos=0.80  min_height=3.0  min_bins=0.50  max_anchor=1.2  canopy_max=1.0
run_gap=1.5  extractor="component"   # or "grow" (recall-oriented)
pole_min_h=0.4
box_length=2.6  box_width=4.0  pad_h=0.6  sink=0.4
min_box_height=3.0  max_box_height=18.0
```

| function | signature | returns |
|---|---|---|
| `detect` | `detect(points, ground, params=PoleParams())` | `(accepted, rejected)` — lists of feature dicts (`centre, n, span, radius, cos_z, occupied, anchor, canopy, isolation, ztop, ztop98, zbot, n_cells, points`) |
| `fit_box` | `fit_box(candidate, ground, params=PoleParams(), name="pole")` | one box dict, ground-anchored: bottom = `ground_z(cx,cy) - sink`, top = `ztop98 + pad_h` clipped to `max_box_height` |
| `detect_boxes` | `detect_boxes(points, ground, params=PoleParams(), name="pole")` | `(boxes, accepted)`; applies `B.nms(..., radius=max(box_length, box_width)*0.5)` |

Private helpers: `_components_2d`, `_canopy_ratio`, `_isolation`, `_component_clusters`, `_vertical_runs`.
`_isolation` builds a `cKDTree` on the above-ground XY of the whole frame — the other main CPU consumer.

### A.7 `polewire/wires.py` — wire detection (numpy + scipy.spatial.cKDTree)

`WireParams` (all defaults):

```python
min_height=2.5   ball=2.0   kmax=200   v3z_min=0.85   flat_max=0.35
cluster_radius=1.0  min_points=15  min_length=4.0  max_length=30.0
min_across=1.2  min_thickness=0.8
pad_along=0.6  pad_across=0.6  pad_h=0.4
```

| function | signature | returns |
|---|---|---|
| `ribbon_mask` | `ribbon_mask(points, ground, params=WireParams()) -> np.ndarray[bool]` | points whose local 2 m ball PCA is a flat near-horizontal sheet |
| `fit_box` | `fit_box(cluster, params=WireParams(), name="wire") -> (box, meta)` | **the long axis goes into `width`** |
| `detect_boxes` | `detect_boxes(points, ground, params=WireParams(), name="wire") -> (boxes, info)` | one box per connected ribbon cluster |

The wire **orientation convention** is explicit in `fit_box` (wires.py:122-133):

```python
    # local frame: width axis = wire direction, length axis = perpendicular horizontal
    perp   = np.array([-horizontal[1], horizontal[0], 0.0])
    along  = Q @ horizontal
    across = Q @ perp
    length = float(across.max() - across.min()) + 2 * params.pad_across
    width  = float(along.max() - along.min())  + 2 * params.pad_along
    ...
    # yaw such that the box's local +y (width) points along the wire
    rz = float(np.degrees(np.arctan2(horizontal[1], horizontal[0])) - 90.0)
    rz = (rz + 180.0) % 360.0 - 180.0
```

### A.8 `polewire/pipeline.py` — frame/directory pipeline (numpy only)

```python
@dataclass
class Config:
    classes: tuple = ("pole", "wire")
    pole: poles.PoleParams = field(default_factory=PoleParams)
    wire: wires.WireParams = field(default_factory=WireParams)
    ground_cell: float = 1.5
    ground_quantile: float = 5.0
    ground_method: str = "mode"
    def to_json(self): ...

def process_frame(pcd_path, cfg=None) -> (List[box], dict)      # ← the in-process entry point
def find_pcds(root) -> List[str]                                # root, or root/images/*.pcd
def process_directory(root, out_dir=None, cfg=None, limit=None, jobs=1,
                      overwrite=True, verbose=True) -> dict
def write_run_config(out_dir, cfg, extra=None) -> str
```

`process_frame` debug dict: `{points, ms, pole_candidates, poles, wires, wire_points, total}`.
`process_directory` stats dict: `{frames, boxes, poles, wires, skipped, failed, seconds, failure_list}`.
`jobs` is accepted but **completely unused** (no parallelism implementation) — a single-threaded loop.
On a per-frame exception it still writes an **empty** `objects: []` JSON for that stem (pipeline.py:101-104).

### A.9 `polewire/visualize.py` — debug rendering (numpy + lazy matplotlib)

`render_frame(pcd_path, gt_path=None, pred_path=None, out_path=None, title=None)` and
`render_dataset(root, out_dir, stems=None, limit=None)`. Imports `matplotlib` with `Agg` **inside** the
function, so the rest of the package does not require it.

### A.10 Top-level CLIs

* `autolabel.py` — argparse wrapper. Key flags: `--dataset` (required), `--out` (default
  `<dataset>/labels_auto`), `--classes pole,wire`, `--limit N`, `--no-overwrite`, `--ground-cell 1.5`,
  `--ground-method {mode,median3,quantile}`, `--ground-quantile 5.0`, plus 8 `--pole-*` and 7 `--wire-*`
  knobs. Ends with `write_classes_json(out_dir, classes)` + `write_run_config(...)`.
  README's parameter table lists `--ground-quantile` default as `2.0`; the code says `5.0` — doc/CLI drift.
* `evaluate.py` — `--dataset | --gt/--pred`, `--iou 0.2`, `--centre 1.5`, `--out report.md`.
  `match_frame(gt, pred, iou_thr=0.2, centre_thr=1.5)`: a GT/pred pair counts as a hit if BEV IoU ≥ 0.2
  **or** centre distance ≤ 1.5 m (same class only).
* `inspect_frames.py` — `--dataset --stem/--stems/--limit/--out/--pred`, renders BEV + side-view PNGs.

### A.11 CPU cost — claimed vs measured

* **Claimed** (README §7 / REPORT §4): *"单帧约 0.4~1.7 s（104~192 s / 100 帧，本机 CPU）"* — CPU only, no GPU.
* **Measured here** (labelCloud venv Python 3.8 / numpy 1.24 / scipy 1.10, dataset `2026_04131(未标)/images`):

| frame | points | pole only | wire only | pole+wire | boxes |
|---|---|---|---|---|---|
| `1776414480983377525` | 122 | — | — | **18 ms** | 0 |
| `1776414484…` | 11 073 | — | — | 24 ms | 0 |
| `1776414501…` | 19 194 | — | — | 129 ms | 1 pole |
| `1776414527378325873` | 45 929 | 60 ms | **826 ms** | 790 ms | 1 wire |
| `1776414517…` | 35 267 | — | — | 1 141 ms | 1 wire |

  Over 10 annotated frames: min 18 ms, **median 80 ms**, p90 1 141 ms, max 1 142 ms.
  `estimate_ground` alone on the 46 k-point frame: **31 ms**.
  → Cost is dominated by the **wire** module (per-point 2 m ball query + batched `eigh` over up to
  `kmax=200` neighbours). Pole-only is roughly an order of magnitude cheaper.
  Numbers scale with point count, and the frames in this dataset range from ~120 to ~50 k points.

---

## B. Label JSON schema, exactly

Dataset `2026_04131(未标)` layout:

```
datasets_y40/2026_04131(未标)/
├── images/        1292 × <stem>.pcd
├── labels_lc/      531 entries: 530 × <stem>.json + test.txt   ← hand labels (no _classes.json)
└── labels_auto/   1294 entries: <stem>.json + _classes.json + _autolabel_config.json
```

`labels_lc` class counts over the 530 files: **`pole` 201, `wire` 281**. Max 1 object per file in the
sampled subset. `images/` has 1292 PCDs but only 531 hand-labelled — the rest are the actual work queue.

### B.1 Example 1 — hand-labelled **wire** (`labels_lc/1776414527378325873.json`, verbatim)

```json
{
	"folder": "images",
	"filename": "1776414527378325873.pcd",
	"path": "/mnt/smb-data/pillars_datasets/pointpillars_datasets_y40/2026_04131/images/1776414527378325873.pcd",
	"objects": [
		{
			"name": "wire",
			"centroid": {
				"x": 15.86707539,
				"y": 3.40568049,
				"z": 1.38096791
			},
			"dimensions": {
				"length": 3.45,
				"width": 17.47,
				"height": 2.25
			},
			"rotations": {
				"x": 0.10471975,
				"y": -0.0,
				"z": -0.07330383
			}
		}
	]
}
```

### B.2 Example 2 — hand-labelled **pole** (`labels_lc/1776414498383606101.json`, verbatim)

```json
{
	"folder": "images",
	"filename": "1776414498383606101.pcd",
	"path": "/mnt/smb-data/pillars_datasets/pointpillars_datasets_y40/2026_04131(\u672a\u6807)/images/1776414498383606101.pcd",
	"objects": [
		{
			"name": "pole",
			"centroid": {
				"x": 39.68588525,
				"y": -9.90412498,
				"z": 2.96593953
			},
			"dimensions": {
				"length": 1.65,
				"width": 4.18,
				"height": 11.07
			},
			"rotations": {
				"x": 0.0,
				"y": 0.0,
				"z": 0.0
			}
		}
	]
}
```

### B.3 For contrast — the matching `labels_auto` output for the same two stems

`labels_auto/1776414527378325873.json` (wire; note the very different `rz` but the same "long axis in
width" shape):

```json
	"objects": [
		{
			"name": "wire",
			"centroid":  { "x": 15.76024848, "y": 5.72610858,  "z": 1.34775123 },
			"dimensions":{ "length": 3.10629978, "width": 15.20335461, "height": 2.89692671 },
			"rotations": { "x": 0.0, "y": 0.0, "z": 174.57482881 }
		}
	]
```

`labels_auto/1776414498383606101.json` (pole; note the templated `length/width = 2.6/4.0` and the
height clipped to the `min_box_height = 3.0` floor):

```json
	"objects": [
		{
			"name": "pole",
			"centroid":  { "x": 39.77284776, "y": -11.18953794, "z": 4.98293633 },
			"dimensions":{ "length": 2.6, "width": 4.0, "height": 3.0 },
			"rotations": { "x": 0.0, "y": 0.0, "z": 0.0 }
		}
	]
```

The only structural difference between `labels_lc` and `labels_auto` files is the `path` value
(`labels_lc` points at the SMB mount, `labels_auto` at the local workspace copy) and `folder`
(polewire uses `os.path.basename(os.path.dirname(pcd))`, labelCloud uses `pcd_path.parent.name` —
the same string for this layout).

### B.4 Field-by-field annotation

| field | type | meaning / gotcha |
|---|---|---|
| `folder` | str | parent directory **name** of the PCD (`"images"`). Purely informational; `CentroidFormat.import_labels` ignores it. |
| `filename` | str | PCD basename **with** extension. Ignored on import (the JSON's own stem is what matters). |
| `path` | str | absolute path of the PCD. Ignored on import. Written as `str(pcd_path)` by labelCloud, `os.path.abspath()` by polewire. |
| `objects` | list | may be empty (`[]`) — that is a legitimate "nothing in this frame" label. |
| `objects[].name` | str | class name as a raw **string**, not an id. Must exist in `_classes.json` for a non-red colour, but import never validates it. |
| `objects[].centroid.{x,y,z}` | float | **box centre** (not the point-cloud centroid), in the same coordinate frame as the PCD's xyz (metres). Not affected by the GUI's pan/zoom/rotate, which live in `PointCloud.trans_*` / `rot_*`. |
| `objects[].dimensions.length` | float > 0 | full extent along the box's **local x** (metres). |
| `objects[].dimensions.width` | float > 0 | full extent along **local y**. **For wires this is the LONG axis.** |
| `objects[].dimensions.height` | float > 0 | full extent along **local z**. |
| `objects[].rotations.{x,y,z}` | float | intrinsic Euler angles in **degrees** (the `centroid_abs` format). Applied as `R = Rz @ Ry @ Rx` — see `boxes.rot_matrix` and `BBox.get_vertices()`. labelCloud stores them as `angle % 360`, so `-0.0733` written by hand comes back as `359.9267` after a save round-trip. The `centroid_rel` format instead uses **radians in −π..π** — the two are not interchangeable. |
| number formatting | | labelCloud: `np.round(v, export_precision)` with `export_precision = 8` (`resources/default_config.ini:33`) → `.tolist()`, so 8 decimals or fewer. polewire: `_round(v, nd=8)`. Files use a TAB indent. |

### B.5 The wire convention: the long axis lives in `dimensions.width`

This is the single most important schema quirk and it is deliberate, documented and implemented:

* `REPORT.md:48`: *"wire 形状 | **长轴在 `dimensions.width`**（不是 length！），W 5~21 m、L 2.1~3.4 m、H 1~3 m | 出框时长边写入 `width`，yaw 使 local +y 指向电线走向"*.
* README §4.3: *"按主方向生成长轴放在 `width` 的扁框（这是你手工标注的约定：电线框的长边是 `dimensions.width`），yaw 使得 local +y 指向电线方向"*.
* `wires.py:131-133`: `rz = degrees(atan2(horizontal[1], horizontal[0])) - 90.0`, normalised to (−180, 180].
* Real data confirms it: the hand-labelled wire above is `length 3.45 × width 17.47`; the auto one is
  `length 3.11 × width 15.20`. A 17 m "width" is nonsensical for a box unless the convention is known.
* Practical consequence for any assist feature: when you *read* a wire box back, the wire direction is
  the **local +y** axis, i.e. `R[:,1]`, and `length` is the across-wire slab thickness. If a future model
  or export path is axis-agnostic (e.g. LitePT's AABB-vertices JSON), wires will come back with the long
  axis in `length` and must be transposed before/after handing to a human.
* `wires.fit_box` also enforces `length >= min_across = 1.2` and `height >= min_thickness = 0.8`, so no
  degenerate slabs.

---

## C. labelCloud integration seams

All paths below are relative to
`/home/tyy/DSH-WS/labelcloud-hzh/lib/python3.8/site-packages/labelCloud/`.
Version 1.1.1. **There is no plugin system, no extension point, and no existing auto-label hook** —
`grep -rn "autolabel|assist|pole|wire|predict" --include=*.py .` returns nothing. Any assist feature is a
code change inside the package.

```
Controller (control/controller.py:20)
 ├── pcd_manager    : PointCloudManger      (control/pcd_manager.py:27)
 ├── bbox_controller: BoundingBoxController  (control/bbox_controller.py:56)
 ├── drawing_mode   : DrawingManager         (control/drawing_manager.py:11)
 └── view           : GUI                    (view/gui.py:118)   ← set in startup()
```

### C.1 How labels are held in memory

`control/bbox_controller.py:59-63`:

```python
    def __init__(self) -> None:
        self.view: GUI
        self.pcd_manager: PointCloudManger
        self.bboxes: List[BBox] = []
        self.active_bbox_id = -1  # -1 means zero bboxes
```

That list **is** the single source of truth for the current frame; it is re-populated on every frame
change from disk (`control/controller.py:64-77`):

```python
    def next_pcd(self, save: bool = True) -> None:
        if save:
            self.save()
        if self.pcd_manager.pcds_left():
            previous_bboxes = self.bbox_controller.bboxes
            self.pcd_manager.get_next_pcd()
            self.reset()
            self.bbox_controller.set_bboxes(self.pcd_manager.get_labels_from_file())
            if not self.bbox_controller.bboxes and config.getboolean("LABEL", "propagate_labels"):
                self.bbox_controller.set_bboxes(previous_bboxes)
            self.bbox_controller.set_active_bbox(0)
```

### C.2 How a bbox is instantiated

`model/bbox.py:22-48` — all six geometry arguments are **positional**; the three dimensions are optional
and fall back to a config default, so omit them only if you want the template size:

```python
class BBox(object):
    MIN_DIMENSION: float = config.getfloat("LABEL", "MIN_BOUNDINGBOX_DIMENSION")
    HIGHLIGHTED_COLOR: Color3f = Color3f(0, 1, 0)

    def __init__(self, cx: float, cy: float, cz: float,
                 length: Optional[float] = None, width: Optional[float] = None,
                 height: Optional[float] = None) -> None:
        self.center: Point3D = (cx, cy, cz)
        self.length: float = length or config.getfloat("LABEL", "STD_BOUNDINGBOX_LENGTH")
        ...
        self.x_rotation: float = 0
        self.y_rotation: float = 0
        self.z_rotation: float = 0
        self.classname: str = LabelConfig().get_default_class_name()
        self.verticies: npt.NDArray = np.zeros((8, 3))
        self.set_axis_aligned_verticies()
```

Followed by `set_rotations(x_angle, y_angle, z_angle)` (`bbox.py:131`, **no** modulo) and
`set_classname(classname)` (`bbox.py:92`). `set_dimensions()` (line 114) silently rejects any
non-positive dimension and logs `"New dimensions are too small."` — a computed box with a zero extent
will silently keep its old size, so clamp before constructing.

The canonical construction for an injected box is therefore:

```python
from labelCloud.model import BBox
b = BBox(cx, cy, cz, length, width, height)   # geometry straight from polewire's box dict
b.set_rotations(rx, ry, rz)                   # degrees, centroid_abs
b.set_classname("pole")                       # or "wire"
```

This is exactly what `CentroidFormat.import_labels` does (`io/labels/centroid.py:28-33`) — verified
working in this venv against the real `labels_auto` files (see §C.8).

### C.3 How a bbox is added to the list

Two options. **Single box** — `control/bbox_controller.py:84-93`:

```python
    def add_bbox(self, bbox: BBox) -> None:
        if isinstance(bbox, BBox):
            self.bboxes.append(bbox)
            self.set_active_bbox(self.bboxes.index(bbox))
            self.view.current_class_dropdown.setCurrentText(self.get_active_bbox().classname)
            self.view.status_manager.update_status(
                "Bounding Box added, it can now be corrected.", Mode.CORRECTION)
```

This is the *only* insertion path used by normal drawing (`control/drawing_manager.py:55`:
`self.bbox_controller.add_bbox(self.drawing_strategy.get_bbox())`). It makes the new box the active one.

**Bulk** — `control/bbox_controller.py:131-138`:

```python
    def set_bboxes(self, bboxes: List[BBox]) -> None:
        self.bboxes = bboxes
        self.deselect_bbox()
        self.update_label_list()

    def reset(self) -> None:
        self.deselect_bbox()
        self.set_bboxes([])
```

For N injected boxes prefer `set_bboxes(list(existing) + new)` (one label-list refresh instead of N),
then `set_active_bbox(idx)` if you want one selected.

**Hard requirement:** both paths dereference `self.view`. `Controller.startup(view)` sets it
(`control/controller.py:43-51`) *after* the startup dialog, so an assist action installed in
`GUI.connect_events()` is safe, but any code that runs before `startup` is not.

### C.4 How the "active bbox" is set

`control/bbox_controller.py:112-120` + the helper at `:353-357`:

```python
    def set_active_bbox(self, bbox_id: int) -> None:
        if 0 <= bbox_id < len(self.bboxes):
            self.active_bbox_id = bbox_id
            self.update_all()
            self.view.status_manager.update_status(
                "Bounding Box selected, it can now be corrected.", mode=Mode.CORRECTION)
        else:
            self.deselect_bbox()

    # HELPER
    def update_all(self) -> None:
        self.update_z_dial()
        self.update_curr_class()
        self.update_label_list()
        self.view.update_bbox_stats(self.get_active_bbox())
```

`active_bbox_id = -1` means "nothing selected" (`has_active_bbox()` at `:66` is
`0 <= self.active_bbox_id < len(self.bboxes)`). Digit keys 1-9 select by index
(`control/controller.py:353-355`), T/G cycle (`:341-346`).

### C.5 How the viewer is asked to redraw

There is **no explicit redraw call to make**. The GUI drives a 20 ms timer
(`view/gui.py:266-269`):

```python
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(20)  # period, in milliseconds
        self.timer.timeout.connect(self.controller.loop_gui)
        self.timer.start()
```

and `control/controller.py:57-61`:

```python
    def loop_gui(self) -> None:
        """Function collection called during each event loop iteration."""
        self.set_crosshair()
        self.set_selected_side()
        self.view.gl_widget.updateGL()
```

`paintGL` (`view/viewer.py:91-133`) then draws everything from the in-memory list each tick:

```python
        # Draw active bbox
        if self.bbox_controller.has_active_bbox():
            self.bbox_controller.get_active_bbox().draw_bbox(highlighted=True)
            ...
        # Draw labeled bboxes
        for bbox in self.bbox_controller.bboxes:
            bbox.draw_bbox()
```

So mutating `bbox_controller.bboxes` is sufficient for the boxes to appear within ~20 ms. Call
`bbox_controller.update_all()` (or `set_active_bbox`) as well to keep the right-hand panel
(label list / class dropdown / position & dimension spin boxes) in sync.

### C.6 How to read the currently loaded point-cloud coordinates

`control/pcd_manager.py:44` (`self.pointcloud: Optional[PointCloud]`) and
`model/point_cloud.py:59` (`self.points = points`). The points are the **raw, absolute PCD xyz as
float32, in file order** — pan/zoom/rotate live only in `trans_x/y/z` and `rot_x/y/z` and are applied at
draw time by `PointCloud.set_gl_background()` (`point_cloud.py:313-328`), *not* baked into `points`.

Verified in this venv:

```
handler points: (45929, 3) float32      max abs diff vs polewire.read_pcd: 5.0e-07
```

So the in-process call is simply:

```python
points = control.pcd_manager.pointcloud.points          # (N,3) float32, absolute coords
pcd_path = control.pcd_manager.pcd_path                 # pathlib.Path of the current frame
boxes, debug = polewire.process_frame(pcd_path, cfg)    # or feed `points` directly, see §E(i)
```

Useful neighbours on the same manager: `pcd_path` (`:50`), `pcd_name` (`:54`), `current_id` (`:38`),
`pcds: List[Path]` (`:37`), `get_labels_from_file()` (`:147-150`), `save_labels_into_file(bboxes)`
(`:160-167`).

### C.7 How label JSON is written on save

`control/controller.py:97-99`:

```python
    def save(self) -> None:
        """Saves all bounding boxes and optionally segmentation labels in the label file."""
        self.pcd_manager.save_labels_into_file(self.bbox_controller.bboxes)
```

→ `control/pcd_manager.py:160-167`:

```python
    def save_labels_into_file(self, bboxes: List[BBox]) -> None:
        if self.pcds:
            self.label_manager.export_labels(self.pcd_path, bboxes)
            self.collected_object_classes.update({bbox.get_classname() for bbox in bboxes})
```

→ `control/label_manager.py:73-74` → `io/labels/centroid.py:40-73` (`CentroidFormat.export_labels`),
which rebuilds the exact `{folder, filename, path, objects[]}` dict, and finally
`io/labels/base.py:46-59`:

```python
    def save_label_to_file(self, pcd_path: Path, data: Union[dict, str]) -> Path:
        label_path = self.label_folder.joinpath(pcd_path.stem + self.FILE_ENDING)
        ...
        if label_path.suffix == ".json":
            with open(label_path, "w") as write_file:
                json.dump(data, write_file, indent="\t")
```

`save()` is triggered by the "save" button (`view/gui.py:349`), by Ctrl+S
(`control/controller.py:266-267`), and implicitly by **every frame change** (`next_pcd(save=True)`,
`prev_pcd`, `custom_pcd`).

Round-trip asymmetry worth knowing: `set_rotations()` does not normalise, but the GUI's
`set_z_rotation()` does `angle % 360` (`model/bbox.py:128-134`), so a hand-written `z: -0.07330383`
becomes `359.92669617` after any GUI edit + save.

### C.8 ⚠️ Blocking defect: `polewire.write_classes_json` produces a file labelCloud cannot load

`polewire/labels.py:124-129`:

```python
def write_classes_json(directory, class_names):
    """Write the LabelCloud class config so the labels open with the right colours."""
    path = os.path.join(directory, "_classes.json")
    with open(path, "w") as fh:
        json.dump(list(class_names), fh, indent=INDENT)
    return path
```

It writes a **flat array**:

```json
[
	"pole",
	"wire"
]
```

But `io/labels/config.py:57-71` expects the labelCloud object schema
(`{"classes": [{"name","id","color"}], "default", "type", "format"}`):

```python
            with config.getpath("FILE", "class_definitions").open("r") as stream:
                data = json.load(stream)
            self.classes = [ClassConfig.from_dict(c) for c in data["classes"]]
            self.default = data["default"]
            self.type = LabelingMode(data["type"])
            self.format = data["format"]
```

Reproduced in this venv with `class_definitions` pointed at the real
`datasets_y40/2026_04131(未标)/labels_auto/_classes.json` and CWD-local `config.ini`:

```
!! LabelConfig FAILED: TypeError : list indices must be integers or slices, not str
  File ".../labelCloud/io/labels/config.py", line 63, in load_config
    self.classes = [ClassConfig.from_dict(c) for c in data["classes"]]
```

`LabelConfig` is instantiated during `Controller()` construction (`control/pcd_manager.py:32`,
`control/label_manager.py:39`), so this is a **hard crash at startup**, not a warning. Consequences:

* The README's workflow step *"打开 LabelCloud，把标注目录指到 labels_auto"* + *"`labels_auto/_classes.json`
  已经写好…LabelCloud 打开时会自动带上类别配置"* is **wrong as written**; pointing `class_definitions`
  at that file kills the app. All 7 `labels_auto*/_classes.json` files in `datasets_y40` have the flat form.
* If `class_definitions` is instead left at the labelCloud default (`labels/_classes.json`, which does not
  exist in these datasets), `load_config()` takes the fallback branch and silently sets
  `self.format = ObjectDetectionFormat.CENTROID_REL` (`config.py:71`) — i.e. **radians**. The polewire JSON
  is degrees. Opening `z: 174.57` as relative rotation yields `np.rad2deg(174.57) = 10002.3°`, then
  `% 360`, i.e. a garbage yaw. Any assist feature must ensure a correct `_classes.json` with
  `"format": "centroid_abs"` exists in the label folder before the app reads labels.
* Fix is trivial (write the dict schema, or have the app generate it from `LabelConfig.save_config()`,
  `config.py:75-85`), but it must be done on purpose, not assumed working.

### C.9 Round-trip proof (run in this venv, no GUI needed)

With a correct `_classes.json` (`format: centroid_abs`, `pole` id 1, `wire` id 2) and
`label_folder` = `datasets_y40/2026_04131(未标)/labels_auto`:

```
classes: [('pole', 1, (1.0, 0.749, 0.208)), ('wire', 2, (0.945, 0.337, 1.0))] format: centroid_abs
Imported 1 labels from .../labels_auto/1776414527378325873.json
Imported 1 labels from .../labels_auto/1776414498383606101.json
1776414527378325873 -> wire center (15.76024848, 5.72610858, 1.34775123) dims (3.106, 15.203, 2.897) rot (0.0, 0.0, 174.57482881)
1776414498383606101 -> pole center (39.77284776, -11.18953794, 4.98293633) dims (2.6, 4.0, 3.0) rot (0.0, 0.0, 0.0)
```

i.e. `LabelManager.import_labels` → `CentroidFormat.import_labels` → `BBox` works unmodified on
polewire output. (`PyOpenGL`/`OpenGL.GL` import is fine headless; constructing `BBox` needs no GL context.)

### C.10 Where a new "assist" UI action would attach

There is no menu bar (`grep menuBar|addMenu` → nothing); the GUI is a button/dock layout. The closest
existing template for "do something to the current frame from the controller" is
`Controller.crop_pointcloud_inside_active_bbox()` (`control/controller.py:381-390`), wired as a
`QAction` in the `label_list` context menu:

* declared + registered — `view/gui.py:205-215`:
  ```python
        self.act_crop_pointcloud_inside = QtWidgets.QAction("Save points inside as")
        self.label_list.addActions([
            self.act_change_class_color, self.act_delete_class, self.act_crop_pointcloud_inside,
        ])
  ```
* connected — `view/gui.py:326-333`:
  ```python
        # context menu
        self.act_delete_class.triggered.connect(
            self.controller.bbox_controller.delete_current_bbox)
        self.act_crop_pointcloud_inside.triggered.connect(
            self.controller.crop_pointcloud_inside_active_bbox)
  ```

A new `act_auto_pole_wire` would follow the same 3-line pattern, plus a `QPushButton` in the left panel
next to `button_save_label` (`view/gui.py:195`, connected at `:349`). The handler should live on
`Controller` so it can reach `self.pcd_manager.pointcloud.points` and
`self.bbox_controller.set_bboxes(...)`.

### C.11 Ready-made minimal injection recipe

```python
# inside a Controller method, after startup():
pts  = self.pcd_manager.pointcloud.points            # (N,3) float32, absolute
path = self.pcd_manager.pcd_path                     # Path
new  = []
for b in polewire_boxes:                             # polewire box dicts
    bb = BBox(*[float(v) for v in b["center"]],
              *[float(v) for v in b["dims"]])
    bb.set_rotations(*[float(v) for v in b["rot"]])
    bb.set_classname(b["name"])
    new.append(bb)
self.bbox_controller.set_bboxes(self.bbox_controller.bboxes + new)   # list, not add_bbox in a loop
self.bbox_controller.set_active_bbox(len(self.bbox_controller.bboxes) - 1)
# redraw happens on the next 20 ms timer tick; save with self.save()
```

Guards worth adding: skip boxes whose class is not in `LabelConfig().get_classes()` (otherwise they
render red and re-save with an unknown name), and de-duplicate against boxes already loaded from disk
(polewire's own `nms` only de-dupes within its own output).

---

## D. Learned-model inventory

**Bottom line: three separate pole/wire model lineages exist in the workspace, and *none* of them can be
executed on this machine.** Details, and exactly why, below.

### D.1 `LitePT/` (4.2 GB) — per-point **semantic segmentation**, classes = background/pole/wire ✅

| item | value |
|---|---|
| Task | point-cloud semantic segmentation, `num_classes = 3` |
| Class order | `0 = background, 1 = pole, 2 = wire` (per `hck_algo/INFERENCE.md:25`; exporter used `sorted(names)+1` with `classes.txt = pole / wire`) |
| Config | `configs/y12_wirepole/semseg-litept-small-v1m1.py` — `DefaultSegmentorV2` + `LitePT`(small), `in_channels=6`, `grid_size=0.05` m, `feat_keys=("color","normal")` |
| Real training config snapshot | `exp/y12_wirepole/wirepole_semseg_train/config.py` (same values, different `data_root`) |
| Checkpoints | `exp/y12_wirepole/wirepole_semseg_train/model/` — `model_best.pth` (**epoch 55, val mIoU 0.9276**, the one to use), `model_last.pth` (epoch 57, 0.9272), `epoch_{3,6,…,57}.pth` ×19. Each **152 829 317 B ≈ 146 MiB** → ~3.0 GB of weights. |
| Class-named tensor inspection | not run (no torch); class names come from the config + INFERENCE.md, which cites `configs/.../semseg-litept-small-v1m1.py:78` |
| Input format | **directory-per-frame numpy**: `coord.npy`, `color.npy`, `normal.npy`, `segment.npy` (+ factory `GridSample` voxelisation at 0.05 m). `infer_pth.py` can also read a `.pcd` but must be patched to feed `color = 0, normal = 0` |
| ⚠️ Feature trap | `color` and `normal` were **identically zero** during training (raw intensity column all-zero, exporter wrote `np.zeros` for normals). Feeding real colours or estimated normals is out-of-distribution. Patch documented at `INFERENCE.md:229-247` |
| Entry points | `tools/test.py` (val eval + 12-view TTA, authoritative), `hck_algo/infer_pth.py` (`.pcd` → per-point `.npy` + labelCloud JSON with **AABB** `vertices`, `--save-labels/--label-dir`), `hck_algo/infer_npy/infer_pth.py` (npy-only, zero-feature default, `--gt-dir` mIoU, `--save-prob`, `--limit`, `--device cpu`) |
| Heaviness | needs `torch + spconv-cu1xx + flash-attn + pointops + pointrope` (the last three are CUDA extensions that must be **compiled** — `libs/pointops`, `libs/pointrope`, `flash-attention/`); `engines/test.py:23` unconditionally imports `wandb`, `engines/hooks/evaluator.py:6` unconditionally imports `pointops` |
| Domain fit | trained on y12 (`26k–106k` points/frame); y40 frames here are `120–50k`. `INFERENCE.md:304-306` explicitly warns the y40 mIoU **must be re-measured** before trusting it |
| Export nuance | `infer_pth.py`'s JSON writer emits **8 axis-aligned `vertices` corners**, not an OBB — for wires an AABB is very loose, so it would still need the polewire-style PCA fit (ACK'd as "补丁 2" in `INFERENCE.md:249-251`) |

### D.2 `OpenPCDet-master/` (6.1 GB) — PointPillars **3D detector**, classes pole + wire ✅ (configs only)

| item | value |
|---|---|
| Class names | `tools/cfgs/my_models/pointpillar_pole.yaml:1` → `CLASS_NAMES: ['pole', 'wire']   # 聂元林：自定义数据集` |
| Sibling configs | `pointpillar_pole_hck.yaml`, `pointpillar_pole_rot60.yaml`, `pointpillar_pole_rot60_pole.yaml`, `pointpillar_wire_v1.yaml` — all in `tools/cfgs/my_models/` |
| Anchors | pole `[3.58, 3.28, 12.50]`, wire `[14.10, 2.50, 3.90]  # TODO 有问题`; `DIR_OFFSET 0.78539`, `NUM_DIR_BINS 2` |
| **Checkpoints** | **NONE.** `find . -name "*.pth"` over the whole tree returns nothing. The configs reference `output/cfgs/my_models/pointpillar_pole/default/ckpt/checkpoint_epoch_{150,300}.pth` and `.../best_model.pth` — **the `output/` directory does not exist here**; those paths are from the original training host (`/home/eav-nanjin/pointcloud/…`) |
| What *is* here | exports only: `deploy_out_0312/`, `deploy_out_0319/`, `deploy_out_0331wire/` — each `pp_backbone_head.onnx` (≈19.3 MB) + `pp_backbone_head.rknn` + `pp_vfe_weights/` (`vfe_weight_64x10.bin` 2.5 KB, `vfe_bias_64.bin` 256 B, `vfe_index.json`); plus 4 root-level `check{0..3}_*.onnx` (~19 MB each, ONNX-graph surgery experiments) |
| `meta.json` | gives the deploy contract: `voxel_size`, `point_cloud_range`, `grid_size_nx_ny_nz`, `bev_shape_BCHW`, `used_feature_list: [x,y,z,intensity]`, and the note *"ONNX input is scatter output spatial_features. Decode/NMS should use the same cfg anchors/post_processing."* `deploy_out_0331wire` = `pointpillar_pole_rot60.yaml` / `best_model.pth`, range `[0,-6,-15, 40,6,15]`, voxel `[0.25,0.10,30]`, BEV `[1,64,120,160]`; `0312`/`0319` use `[0,-12,-15, 40,12,15]`, voxel `[0.25,0.20,30]`, BEV `[1,64,120,160]` |
| Input format | KITTI-style `.bin`, `float32 (N,4)` = `x,y,z,intensity`; `pcdet` voxelisation + anchor decode + NMS with the matching yaml |
| Entry points | `hck_algo/onnx_infer.py` (ONNX + VFE weight files, "无 ckpt 依赖", but still uses `pcdet`+`torch` for `DatasetTemplate`/voxelisation), `tools/demo.py`, `hck_algo/test.py`, `tools/cfgs/my_models/*.yaml` |
| Heaviness | ONNX head ≈ 19 MB; but the Python path pulls in `pcdet` + torch + spconv. Nothing was compiled for this host (`build/` is stale). |

### D.3 `pointpillars/` (69 MB) — C++/ONNX-Runtime **deployment** of the same detector ✅ classes, ❌ binary arch

| item | value |
|---|---|
| Class names | `src/Detector.cpp:105` → `int num_classes = 2;  // pole, wire`; `src/Detector.h:14` → `int cls_id; // 0: pole, 1: wire`; `num_anchors_per_loc = 4  // 2 classes * 2 rotations` |
| Weights | `inconfig/pp_backbone_head.onnx` (19.3 MB) + `inconfig/vfe_weight_64x10.bin` / `vfe_bias_64.bin` / `vfe_index.json` / `meta.json`; `meta.json` names `.../my_models/pointpillar_pole.yaml` and `checkpoint_epoch_150.pth` (**absent**) |
| Prebuilt binaries | `build/pp_single` (205 KB), `build/pp_folder` (287 KB) — `file` says **`ELF 64-bit LSB shared object, ARM aarch64`**, interpreter `/lib/ld-linux-aarch64.so.1`. Host is `x86_64` → **cannot execute here** |
| Runtime | `third_party/onnxruntime/lib/libonnxruntime.so.1.16.3` (also aarch64), OpenMP, C++17 |
| Input format | KITTI `.bin` `(N,4)`; `pcd2bin.py` converts ASCII PCD `(x,y,z[,i])` → `.bin`; `src/main.cpp` hardcodes `x∈[0,40], y∈[-6,6], z∈[-15,15]`, `voxel 0.2/0.075/30`, `grid 200×160×1` |
| Sample data | `bin_converted/` ≈ 40 frames, `1000.bin`/`1000.pcd` |
| Entry point | `./pp_single <frame.bin>` → writes detections into `build/vis_results/*.txt`; `visit.py` (Open3D) replays them |

### D.4 Can any of them detect poles or wires?

| model | poles | wires | runnable on this machine? |
|---|---|---|---|
| LitePT `y12_wirepole` | ✅ class 1 | ✅ class 2 | ❌ no torch, no CUDA GPU; needs 3 compiled CUDA extensions |
| OpenPCDet PointPillars `pointpillar_pole.yaml` (+ `_rot60`, `_wire_v1`) | ✅ class 0 | ✅ class 1 | ❌ **no `.pth` checkpoints present**; Python path needs torch/pcdet |
| pointpillars C++ `pp_single` | ✅ cls 0 | ✅ cls 1 | ❌ aarch64 binary; won't load on x86_64 |
| OpenPCDet stock configs (`custom_models/pointpillar_my_lidar.yaml`, `second.yaml`, `pv_rcnn.yaml`) | ❌ | ❌ | classes are `Car/Pedestrian/Cyclist` / `Vehicle/Pedestrian/Cyclist` — irrelevant |

So: a trained pole+wire detector **does exist in this project's history** (both a segmentation model with
mIoU 0.93 and a PointPillars detector), but all the *executable* forms live on other hardware.

---

## E. Feasibility verdicts

### (i) Call `polewire` in-process from inside the labelCloud GUI on the currently loaded frame

**Verdict: ✅ FEASIBLE — the only real work is threading and packaging.**

Evidence:

* Dependency check passes inside the labelCloud venv: `numpy 1.24.4`, `scipy 1.10.1`,
  `from scipy.spatial import cKDTree; from scipy import ndimage` → OK. No torch, no GPU, no network.
* The point-cloud coordinates are already in memory and are byte-for-byte the file's xyz
  (`max abs diff 5.0e-07` on a 45 929-point frame) — no re-read and no transform needed (§C.6).
* The produced boxes are plain dicts that map 1:1 onto `BBox(cx,cy,cz,length,width,height)` +
  `set_rotations` + `set_classname` (§C.2); injection is `bbox_controller.set_bboxes(...)`; the 20 ms
  timer repaints without any explicit call (§C.3–C.5).
* End-to-end JSON compatibility independently verified (§C.9).

**Blockers / required work:**
1. **Thread it.** 18 ms–1.14 s per frame on the UI thread (median 80 ms; wire dominates at ~0.8–1.1 s on
   35–46 k-point frames) against a 20 ms repaint timer → visible freeze. Run in a `QThread`/
   `QtConcurrent.run` and marshal the result back with a signal; guard against frame changes mid-run
   (`pcd_manager.current_id` captured before, compared after).
2. **Packaging.** `polewire` is not importable from the installed package: either
   `sys.path.insert(0, "/home/tyy/DSH-WS/tools/pole_wire_autolabel")` (hard-coded path, works today) or
   vendor `polewire/` into `labelCloud/` as a sub-package (cleaner, ~60 KB of source).
3. `import polewire` pulls in `scipy` at import time via `pipeline` — import `polewire.poles` /
   `polewire.wires` / `polewire.ground` directly if startup latency matters, or keep `scipy` lazy.
4. Feeding `points` directly needs a thin wrapper: `process_frame` only accepts a **path**; call
   `estimate_ground(points)` + `poles.detect_boxes(...)` + `wires.detect_boxes(...)` yourself for a
   zero-copy path, or pass `pcd_manager.pcd_path` and accept a redundant file read.
5. `polewire.write_classes_json` must **not** be used to seed the label folder (§C.8) — generate the
   `_classes.json` from `LabelConfig().save_config()` semantics instead.

### (ii) Run it as a subprocess and hot-reload the produced JSON

**Verdict: ✅ FEASIBLE and the lowest-risk path — but "hot reload" has to be an explicit trigger, and the
`_classes.json` trap still applies.**

Evidence:

* `autolabel.py --dataset <dir> --out <dir> --limit N --classes pole,wire` runs standalone with no
  import of labelCloud; it writes one `<stem>.json` per frame in exactly the schema
  `CentroidFormat.import_labels` expects (verified, §C.9). It also writes empty `objects: []` for frames
  that fail, so the file set stays complete.
* Reload is one existing call: `bbox_controller.set_bboxes(pcd_manager.get_labels_from_file())`
  (`control/pcd_manager.py:147`, used by `next_pcd`/`prev_pcd`).

**Blockers / required work:**
1. **No file watcher exists** in labelCloud (`grep` finds no `QFileSystemWatcher`/watchdog). "Hot reload"
   means a button/shortcut that (a) optionally `controller.save()`s current edits, (b) re-reads the
   current frame's JSON, (c) calls `set_bboxes`. Without (a) you silently discard the user's unsaved boxes.
2. **Whole-directory batching.** The CLI has no single-frame mode; `--limit N` truncates *and*
   `--no-overwrite` skips existing files, so per-frame invocation from the GUI is awkward. Either add a
   `--stem`/`--pcd` option to `autolabel.py`, or call `polewire.pipeline.process_frame` + `write_labels`
   from a tiny CLI shim. `process_directory` also does not parallelise (`jobs` is ignored).
3. **Do not point `class_definitions` at the `_classes.json` that `autolabel.py` writes** — it crashes
   labelCloud at startup (§C.8). Keep `class_definitions` on a correct, hand-written/labelCloud-generated
   file and treat `labels_auto/_classes.json` as a stray artifact (consider deleting it from the output).
4. Subprocess latency: the whole-process startup plus per-frame cost is the same 0.4–1.7 s profile, but
   it now happens off the UI thread for free. SMB-backed datasets will be I/O-bound on top of that.

### (iii) Use a trained segmentation model instead

**Verdict: ❌ NOT ON THIS MACHINE — the models and weights exist and cover pole+wire, but there is no
runtime for them here. ⚠️ Even with a runtime, the y12→y40 domain shift has to be re-measured first.**

Evidence:

* No `torch` in `labelcloud-hzh` (the only venv in the workspace) nor in `python3`/`/usr/bin/python3`;
  `find` for a `site-packages/torch` under the workspace returns nothing. `nvidia-smi` is not installed →
  no NVIDIA driver/GPU.
* LitePT needs `spconv-cu1xx` + the compiled `pointops`, `pointrope`, `flash-attention` CUDA extensions;
  `engines/test.py` unconditionally imports `wandb` and `engines/hooks/evaluator.py` unconditionally
  imports `pointops`, so a partial install fails at import with a misleading "config" error.
* OpenPCDet has **no `.pth` checkpoint at all** in the workspace (only ONNX/RKNN exports of the
  head); the `output/` tree named in `meta.json` belongs to the original training host.
* The one prebuilt executable detector, `pointpillars/build/pp_single`, is an **aarch64** ELF; the host is
  x86_64.
* Quality is not the problem: `model_best.pth` is epoch 55 at **val mIoU 0.9276** over 3 classes
  (background/pole/wire). But `INFERENCE.md:304-306` warns it was trained on y12 at 26k–106k pts/frame
  while the y40 frames here are 120–50k pts/frame — the 0.92 must be re-measured on GT frames before any
  decision.

**Blocker: runtime/environment, not model availability.** To unblock, run inference on the training/deploy
host and bring back per-point labels (`.npy`), then either (a) filter the cloud by predicted pole/wire
points and feed that subset into `polewire`'s geometric fitting — the interface point the polewire README
itself proposes at `README.md:157-158`: *"只需在 `pipeline.process_frame` 前做一次点云筛选"* — or
(b) build OBBs from the predicted points with `wires.fit_box` / `poles.fit_box` semantics. Two extra
requirements from `INFERENCE.md`: feed `color = 0, normal = 0` (zero-feature training), and clear the
`result/` cache directory whenever the weights change (`engines/test.py:163` silently reuses stale
`.npy` predictions).

---

## Appendix — quick file/line index used above

| thing | location |
|---|---|
| `BBox.__init__` | `labelCloud/model/bbox.py:26-48` |
| `BBox.set_rotations` / `set_classname` / `set_dimensions` | `model/bbox.py:131-134` / `:92-94` / `:114-120` |
| `BBox.get_vertices` (OBB corners, `Rz@Ry@Rx`) | `model/bbox.py:73-79` |
| `PointCloud.points` (raw absolute xyz) | `model/point_cloud.py:59` |
| draw-time transform only | `model/point_cloud.py:313-328` |
| `BoundingBoxController.bboxes` / `active_bbox_id` | `control/bbox_controller.py:62-63` |
| `add_bbox` | `control/bbox_controller.py:84-93` |
| `set_bboxes` / `reset` | `control/bbox_controller.py:131-138` |
| `set_active_bbox` / `has_active_bbox` | `control/bbox_controller.py:112-120` / `:66-67` |
| `update_all` / `update_label_list` | `control/bbox_controller.py:353-357` / `:373-388` |
| `pcd_manager.pointcloud` / `pcd_path` / `pcd_name` | `control/pcd_manager.py:44` / `:50` / `:54` |
| `get_labels_from_file` / `save_labels_into_file` | `control/pcd_manager.py:147-150` / `:160-167` |
| label folder + strategy construction | `control/label_manager.py:42-53`, `:11-35` |
| `Controller.save` / `startup` / `loop_gui` | `control/controller.py:97-103` / `:43-51` / `:57-61` |
| `Controller.next_pcd` (label reload) | `control/controller.py:64-77` |
| `Controller.crop_pointcloud_inside_active_bbox` (action template) | `control/controller.py:381-390` |
| `CentroidFormat.import_labels` / `export_labels` | `io/labels/centroid.py:13-38` / `:40-73` |
| `BaseLabelFormat.save_label_to_file` | `io/labels/base.py:46-59` |
| `LabelConfig.load_config` (crash site) | `io/labels/config.py:57-73` |
| `LabelConfig.save_config` (correct writer) | `io/labels/config.py:75-85` |
| `export_precision = 8` | `resources/default_config.ini:33` |
| 20 ms repaint timer | `view/gui.py:266-269` |
| `paintGL` draws all bboxes | `view/viewer.py:91-133` |
| context-menu action template | `view/gui.py:205-215`, `:326-333` |
| save button wiring | `view/gui.py:349` |
| polewire wire axis convention | `tools/pole_wire_autolabel/polewire/wires.py:122-133` |
| polewire `_classes.json` defect | `tools/pole_wire_autolabel/polewire/labels.py:124-129` |
| polewire box record | `tools/pole_wire_autolabel/polewire/labels.py:35-39` |
| polewire JSON writer | `tools/pole_wire_autolabel/polewire/labels.py:98-121` |
| polewire frame entry point | `tools/pole_wire_autolabel/polewire/pipeline.py:36-57` |
| LitePT inference guide | `LitePT/hck_algo/INFERENCE.md` (esp. §1.2, §4.2, §6 step 5) |
| LitePT best weights | `LitePT/exp/y12_wirepole/wirepole_semseg_train/model/model_best.pth` |
| PointPillars class names (python cfg) | `OpenPCDet-master/tools/cfgs/my_models/pointpillar_pole.yaml:1` |
| PointPillars class names (C++) | `pointpillars/src/Detector.cpp:105`, `src/Detector.h:14` |
| deploy contract | `OpenPCDet-master/deploy_out_*/pp_backbone_head.meta.json`, `pointpillars/inconfig/meta.json` |
