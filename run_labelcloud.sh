#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# labelCloud 启动脚本（固定工作目录，不再把 config.ini / labels 写到 venv/bin 里）
#
# 用法:
#   ./run_labelcloud.sh                          # 用下面的默认数据集
#   ./run_labelcloud.sh <数据集目录> [标注目录名]  # 换数据集；标注目录默认 labels_lc
#   ./run_labelcloud.sh --list                   # 列出 datasets_y40 下的数据集
#   DRY_RUN=1 ./run_labelcloud.sh                # 只生成 config.ini，不启动界面
#
# 说明:
#   * 工作目录固定为 $WORKDIR，labelCloud 只会在那里读写 config.ini
#   * 点云/标注目录写成**绝对路径**，指向你的数据集，不改动任何原始标注
#   * 每次启动前把旧 config.ini 备份成 config.ini.bak
# ---------------------------------------------------------------------------
set -euo pipefail

VENV=/home/tyy/DSH-WS/labelcloud-hzh
PY="$VENV/bin/python"
DATASETS_ROOT=/home/tyy/DSH-WS/datasets_y40
WORKDIR=/home/tyy/DSH-WS/labelcloud-work

DEFAULT_DATASET="2026_04131(未标)"
DEFAULT_LABELS="labels_lc"

if [ ! -x "$PY" ]; then
  echo "找不到虚拟环境解释器: $PY" >&2
  exit 1
fi

if [ "${1:-}" = "--list" ] || [ "${1:-}" = "-l" ]; then
  echo "可用数据集($DATASETS_ROOT):"
  for d in "$DATASETS_ROOT"/*/; do
    name=$(basename "$d")
    [ -d "$d/images" ] || continue
    n_pcd=$(find "$d/images" -name '*.pcd' 2>/dev/null | wc -l)
    printf '  %-20s %5s 帧  labels: %s\n' "$name" "$n_pcd" "$(ls "$d" | grep '^labels' | tr '\n' ' ')"
  done
  exit 0
fi

DATASET="${1:-$DEFAULT_DATASET}"
LABELS="${2:-$DEFAULT_LABELS}"

# 允许直接给绝对路径，或只给数据集名
case "$DATASET" in
  /*) DS_DIR="$DATASET" ;;
  *)  DS_DIR="$DATASETS_ROOT/$DATASET" ;;
esac

PCD_DIR="$DS_DIR/images"
LABEL_DIR="$DS_DIR/$LABELS"

if [ ! -d "$PCD_DIR" ]; then
  echo "点云目录不存在: $PCD_DIR" >&2
  echo "用 ./run_labelcloud.sh --list 看看有哪些数据集。" >&2
  exit 1
fi
if [ ! -d "$LABEL_DIR" ]; then
  echo "标注目录不存在，自动创建: $LABEL_DIR"
  mkdir -p "$LABEL_DIR"
fi

mkdir -p "$WORKDIR"
cd "$WORKDIR"

# --- 安全闸门：不认识的老标注格式先别动 -------------------------------------
# labelCloud 现在按 centroid 读；若标注目录里是 8 角点 vertices 文件，会读成 0 个框，
# 而切帧 / Ctrl+S 都会自动保存，把原标注改写成空文件。F-05 之前先在这里拦一下。
if [ "${FORCE:-0}" != "1" ]; then
  probe=$(grep -l '"vertices"' "$LABEL_DIR"/*.json 2>/dev/null | head -1 || true)
  if [ -n "$probe" ]; then
    echo >&2
    echo "⚠️  标注目录里是 vertices(8 角点) 格式，例如：" >&2
    echo "    $probe" >&2
    echo "    当前类别配置是 centroid_abs，labelCloud 会把这类文件读成 0 个框，" >&2
    echo "    并在切帧/保存时覆盖掉原始标注。" >&2
    echo "    请改用 labels_auto 目录（centroid 格式），或等 F-05 格式识别做完。" >&2
    echo "    确实要以 centroid 方式打开：FORCE=1 ./run_labelcloud.sh ..." >&2
    exit 2
  fi
fi

# 类别定义文件（labelCloud 需要 dict 结构；pole/wire + 颜色 + centroid_abs）
CLASSES="$WORKDIR/_classes.json"
if [ ! -f "$CLASSES" ]; then
  cat > "$CLASSES" <<'JSON'
{
    "classes": [
        { "name": "pole", "id": 1, "color": "#00ff7f", "z_rotation_only": true },
        { "name": "wire", "id": 2, "color": "#00aaff", "z_rotation_only": false }
    ],
    "default": 1,
    "type": "object_detection",
    "format": "centroid_abs",
    "created_with": { "name": "labelCloud", "version": "1.1.1" }
}
JSON
  echo "已生成类别配置: $CLASSES"
fi

# 备份旧配置，然后写一份路径为绝对路径的新配置
if [ -f config.ini ]; then
  cp -f config.ini "config.ini.bak"
fi
cat > config.ini <<INI
[FILE]
; source of point clouds
pointcloud_folder = $PCD_DIR
; sink for label files
label_folder = $LABEL_DIR
; definition of classes and export format
class_definitions = $CLASSES
; only for kitti: calibration file for each point cloud
calib_folder = $WORKDIR/calib/
; sink for segmentation files (*.bin point clouds) [optional]
segmentation_folder = $WORKDIR/segmentation/
; 2d image folder [optional]
image_folder = $PCD_DIR

[POINTCLOUD]
; drawing size for points in point cloud
point_size = 4.0
; point color for colorless point clouds (r,g,b)
colorless_color = 0.9, 0.9, 0.9
; colerize colorless point clouds by height value [optional]
colorless_colorize = True
; standard step for point cloud translation (for mouse move)
std_translation = 0.5
; standard step for zooming (for scrolling)
std_zoom = 0.1
; blend the color with segmentation labels [optional]
color_with_label = True
; mix ratio between label colors and rgb colors [optional]
label_color_mix_ratio = 0.3

[LABEL]
; number of decimal places for exporting the bounding box parameter.
export_precision = 8
; default length of the bounding box (for picking mode)
std_boundingbox_length = 0.75
; default width of the bounding box (for picking mode)
std_boundingbox_width = 0.53
; default height of the bounding box (for picking mode)
std_boundingbox_height = 0.18
; standard step for translating the bounding box with button or key (in meter)
std_translation = 0.03
; standard step for rotating the bounding box with button or key (in degree)
std_rotation = 0.5
; standard step for scaling the bounding box  with button
std_scaling = 0.03
; minimum value for the length, width and height of a bounding box
min_boundingbox_dimension = 0.01
; propagate labels to next point cloud if it has no labels yet
propagate_labels = False
; save the current frame automatically every N seconds (0 disables it)
autosave_interval_seconds = 60

[ASSIST]
; folder of the offline pole/wire pre-annotation tool (tools/pole_wire_autolabel);
; leave empty to disable the "pre-annotate this frame" command
polewire_path = /home/tyy/DSH-WS/tools/pole_wire_autolabel
; classes the pre-annotation should propose
classes = pole,wire
; pole parameters: recall (more boxes, fewer misses) or strict (fewer, cleaner)
pole_profile = recall

[USER_INTERFACE]
; only allow z-rotation of bounding boxes. set false to also label x- & y-rotation
z_rotation_only = True
; visualizes the pointcloud floor (x-y-plane) as a grid
show_floor = False
; visualizes the object's orientation with an arrow
show_orientation = True
; background color of the point cloud viewer (rgb)
background_color = 100, 100, 100
; number of decimal places shown for the parameters of the active bounding box
viewing_precision = 2
; near and far clipping plane for opengl (where objects are visible, in meter)
near_plane = 0.1
far_plane = 300
; keep last perspective between point clouds [optional]
keep_perspective = False
; show button to visualize related images in a separate window [optional]
show_2d_image = False
; delete the bounding box after assigning the label to the points [optional]
delete_box_after_assign = True
INI

echo "工作目录 : $WORKDIR"
echo "点云目录 : $PCD_DIR"
echo "标注目录 : $LABEL_DIR"

if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "(dry-run：只生成配置，不启动界面)"
  exit 0
fi

echo "启动 labelCloud ..."
exec "$PY" -m labelCloud
