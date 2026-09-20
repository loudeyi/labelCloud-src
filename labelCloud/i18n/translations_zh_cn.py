"""Simplified-Chinese translations for the labelCloud interface.

Source of truth for the ``zh_CN`` locale. Keyed by the **exact** English source
string as it appears in the code or the ``.ui`` files; ``tools/update_translations.py``
merges this dictionary into ``labelCloud_zh_CN.ts`` and compiles it with ``lrelease``.

Why a dictionary instead of editing the ``.ts`` by hand (or in Qt Linguist): the
whole translation fits in one reviewable file, diffs cleanly in git, and adding a
string never needs a Qt toolchain beyond ``pylupdate5``/``lrelease``. Strings that
are missing here simply stay English, and the build script lists them.

Log messages are intentionally not translated.
"""

TRANSLATIONS = {
    # ------------------------------------------------------------------ GUI --
    "labelCloud": "labelCloud",
    "No 2D Image File": "没有对应的二维图像",
    "Could not find a related image in the image folder (%s).\n"
    "Check your path to the folder or if an image for this point cloud exists.": (
        "在图像目录（%s）里找不到对应图像。\n请检查目录路径，或确认这帧点云是否有对应图像。"
    ),
    "2D Image (%s)": "二维图像（%s）",
    "<b>labelCloud could not find any valid point cloud files inside the "
    "specified folder.</b>": "<b>labelCloud 在指定目录里没有找到任何有效的点云文件。</b>",
    "Please copy all your point clouds into <code>%s</code> or update "
    "the point cloud folder location. labelCloud supports the following point "
    "cloud file formats:\n %s.": (
        "请把点云复制到 <code>%s</code>，或修改点云目录。labelCloud 支持以下点云格式：\n %s。"
    ),
    "No Point Clouds Found": "未找到点云文件",
    "Current: <em>%s</em>": "当前：<em>%s</em>",
    "Change Point Cloud Folder": "更改点云目录",
    "Change Label Folder": "更改标注目录",
    "Insert Point Cloud number: ()": "输入点云序号：()",
    "Insert Point Cloud number: %s": "输入点云序号：%s",
    "Point Cloud File (%s)": "点云文件（%s）",
    "Select a file name to save the point cloud": "选择点云保存的文件名",
    "Failed to save a point cloud": "保存点云失败",
    # -------------------------------------------------------------- MainWindow --
    "MainWindow": "MainWindow",
    "Point Cloud": "点云",
    "%v/%m": "%v/%m",
    "Save current labels and load previous point cloud.": "保存当前标注并加载上一帧点云。",
    "« Previous": "« 上一帧",
    "Set": "跳转",
    "Save current labels and load next point cloud.": "保存当前标注并加载下一帧点云。",
    "Next »": "下一帧 »",
    "Bounding Box Controls": "检测框操作",
    "Move bounding box up. [Q]": "上移检测框 [Q]",
    "Move bounding box down. [E]": "下移检测框 [E]",
    "Move bounding box right. [D]": "右移检测框 [D]",
    "Move bounding box left. [A]": "左移检测框 [A]",
    "Move bounding box backward. [W]": "后移检测框 [W]",
    "Move bounding box forward. [S]": "前移检测框 [S]",
    "Rotate bounding box around the Z-axis. [Y]/[X]": "绕 Z 轴旋转检测框 [Y]/[X]",
    "Increase bounding box dimensions.": "放大检测框尺寸",
    "Decrease bounding box dimensions.": "缩小检测框尺寸",
    "Open 2D image": "打开二维图像",
    "Pick Bounding Box": "点选建框",
    "Span Bounding Box": "四点建框",
    "Save Label": "保存标注",
    "Labels": "标注",
    "Current Class:": "当前类别：",
    "Current BBox:": "当前检测框：",
    "Center": "中心",
    "Rotation": "旋转",
    "Dimension": "尺寸",
    "Volume": "体积",
    "Deselect current bounding box.": "取消选中当前检测框。",
    "Deselect": "取消选中",
    "Delete current bounding box. [DEL]": "删除当前检测框 [DEL]",
    "Delete": "删除",
    "Assign labels to points inside a box": "把框内点云标记为该类别",
    "Assign": "标记",
    "File": "文件",
    "Set Default Object Class …": "设置默认类别 …",
    "Settings": "设置",
    "Language": "语言",
    "Set Point Cloud Folder…": "设置点云目录…",
    "Set Label Folder…": "设置标注目录…",
    "Load Single Point Cloud…": "加载单个点云…",
    "Z-Rotation Only Mode": "仅绕 Z 轴旋转",
    "Only allows bounding box rotation around the z-axis.": "只允许检测框绕 Z 轴旋转。",
    "Color with labels": "按标注着色",
    "Delete All Current Labels": "删除当前所有标注",
    "Set Default Bounding Box Dimensions ...": "设置默认检测框尺寸 …",
    "Set Default Transformation Steps …": "设置默认变换步长 …",
    "Point Size": "点大小",
    "Show Floor": "显示地面网格",
    "Shows a grid along the x-y-plane (z=0).": "在 x-y 平面（z=0）上显示网格。",
    "Show Orientation": "显示朝向",
    "Keep Perspective": "保持视角",
    "Saves the last perspective and reuses it,\n"
    "when opening that point cloud again.": "记住上一帧的视角，再次打开该点云时沿用。",
    "Align Point Cloud": "对齐点云",
    "Transforms the point cloud so that the floor is the x-y-plane.": (
        "把点云变换到“地面为 x-y 平面”的姿态。"
    ),
    "Change Settings ...": "修改设置 …",
    "test": "测试",
    "Propagate Labels": "沿用上一帧标注",
    "Propagate Labels to the next Point Cloud\n"
    "if it does not have labels yet.": "下一帧还没有标注时，沿用上一帧的检测框。",
    "Follow System Language": "跟随系统语言",
    "English": "English",
    "中文（简体）": "中文（简体）",
    # ----------------------------------------------------------- SettingsDialog --
    "Change Settings": "修改设置",
    "Applies the last perspective of the previous point cloud to the current point "
    "cloud when loading.": "加载时把上一帧点云的视角应用到当前点云。",
    "Keep last Perspective between Point Clouds": "在点云之间保持视角",
    "Point color for colorless point clouds (r,g,b).": "无颜色点云的点颜色（r,g,b）。",
    "Point Color\n(for colorless point clouds)": "点颜色\n（用于无颜色点云）",
    "Path to the folder where the label files will be saved.": "标注文件的保存目录。",
    "Label Folder": "标注目录",
    "User Interface": "界面",
    "Note: Some settings might require a restart to take effect!": (
        "注意：部分设置可能需要重启后生效！"
    ),
    "Standard step for point cloud translation.": "点云平移的标准步长。",
    "Standard Translation": "标准平移步长",
    "Background color of the point cloud viewer (rgb).": "点云视图的背景色（rgb）。",
    "Path to the folder that contains the point cloud files.": "点云文件所在目录。",
    "Visualizes the object's orientation with an arrow.": "用箭头显示目标朝向。",
    "Show Bounding Box Orientation": "显示检测框朝向",
    "Standard step for zooming.": "缩放的标准步长。",
    "Standard Zoom Factor": "标准缩放步长",
    "Colerize colorless point clouds by height value.": "按高度为无颜色点云着色。",
    "Colorize colorless point clouds by height": "按高度着色",
    "Rasterized diameter of each point from the point cloud.": "每个点的绘制直径。",
    "number of decimal places shown for the parameters of the active bounding box.": (
        "当前检测框参数显示的小数位数。"
    ),
    "Visualizes the pointcloud floor (x-y-plane) as a grid.": "把地面（x-y 平面）显示为网格。",
    "Show Point Cloud Floor (x-y-Plane)": "显示地面网格（x-y 平面）",
    "Viewing Precision of\nBounding Box Parameter": "检测框参数\n显示精度",
    "Background Color": "背景颜色",
    "File Settings": "文件设置",
    "Point Cloud Settings": "点云设置",
    "Point Cloud Folder": "点云目录",
    "Show related 2D Images in new Window": "在新窗口显示对应的二维图像",
    "Standard step for scaling the bounding box.": "检测框缩放的标准步长。",
    "Standard step for translating the bounding box (meter).": (
        "检测框平移的标准步长（米）。"
    ),
    "Standard Translation Step": "标准平移步长",
    "List of object classes for autocompletion in the text field.": "自动补全用的类别列表。",
    "Object Classes": "目标类别",
    "Number of decimal places shown for the parameters of the active bounding box.": (
        "当前检测框参数显示的小数位数。"
    ),
    "Export Precision": "导出精度",
    "Default length of the bounding box (for picking mode).": (
        "检测框的默认长度（点选建框时使用）。"
    ),
    "Default height of the bounding box (for picking mode).": (
        "检测框的默认高度（点选建框时使用）。"
    ),
    "Standard Bounding Box Height": "检测框默认高度",
    "Default width of the bounding box (for picking mode).": (
        "检测框的默认宽度（点选建框时使用）。"
    ),
    "Format for exporting labels.": "标注导出格式。",
    "Label Format": "标注格式",
    "Minimum value for the length, width and height of a bounding box.": (
        "检测框长、宽、高的最小值。"
    ),
    "Label Settings": "标注设置",
    "Standard step for rotating the bounding box (degree).": (
        "检测框旋转的标准步长（度）。"
    ),
    "Standard Rotation Step": "标准旋转步长",
    "Standard Bounding Box Width": "检测框默认宽度",
    "Standard Scaling Step": "标准缩放步长",
    "Standard Bounding Box Length": "检测框默认长度",
    "Min. Bounding Box Dimensions": "检测框最小尺寸",
    "Only allow z-rotation of bounding boxes. Deactivate to also label x- & "
    "y-rotation.": "只允许检测框绕 Z 轴旋转；关闭后可标注 x/y 轴旋转。",
    "Z-Rotation-Only Mode (otherwise rotation around x, y and z)": (
        "仅绕 Z 轴旋转（关闭后可绕 x/y/z 轴旋转）"
    ),
    "Default object class for new bounding boxes.": "新建检测框的默认类别。",
    "Default Object Class": "默认类别",
    "Reset to Default": "恢复默认",
    "Propagate Labels (copy all bounding boxes to the next point cloud)": (
        "沿用上一帧标注（把全部检测框复制到下一帧）"
    ),
    # ------------------------------------------------------------ StartupDialog --
    "Welcome to labelCloud": "欢迎使用 labelCloud",
    "Select labeling mode:": "选择标注模式：",
    "Default class:": "默认类别：",
    "Label export format:": "标注导出格式：",
    "Change class labels:": "修改类别列表：",
    "Add new label": "新增类别",
    "Something went wrong": "出错了",
    " Do you want to overwrite the default to the first label `%s`?": (
        " 是否把默认类别改为第一个类别 `%s`？"
    ),
    # ------------------------------------------------------------ StatusManager --
    "Alignment Mode": "对齐模式",
    "Correction Mode": "修正模式",
    "Drawing Mode": "绘制模式",
    "Navigation Mode": "导航模式",
    # ---------------------------------------------------------------- labelCloud --
    "Aligned point cloud with the selected floor.": "已按所选地面对齐点云。",
    "Scroll to change the bounding box dimension.": "滚动滚轮可修改检测框尺寸。",
    "Please pick the location for the bounding box front center.": (
        "请在目标上点一下，确定检测框前中心的位置。"
    ),
    "Begin by selecting a vertex of the bounding box.": "先选择检测框的一个顶点。",
    "Select a point representing the length of the bounding box.": (
        "选择一点来确定检测框的长度。"
    ),
    "Select any point for the depth of the bounding box.": "选择任意一点确定检测框的进深。",
    "Select any point for the height of the bounding box.": "选择任意一点确定检测框的高度。",
    "Invalid segmentation label": "无效的语义分割标注",
    "Bounding Box added, it can now be corrected.": "已添加检测框，可以开始修正。",
    "Bounding Box selected, it can now be corrected.": "已选中检测框，可以开始修正。",
    "Found {count} point clouds in the point cloud folder.": (
        "在点云目录中找到 {count} 帧点云。"
    ),
    "Please set the point cloud folder to a location that contains point cloud files.": (
        "请把点云目录设置为包含点云文件的目录。"
    ),
    "Select three points on the plane that should be the floor.": (
        "在地面所在的平面上选择三个点。"
    ),
    "The triangle area should be part over and part under the floor points.": (
        "这个三角形应当一部分在所选地面之上、一部分之下。"
    ),
    "Hold right mouse button to translate or left mouse button to rotate "
    "the bounding box.": "按住鼠标右键平移、按住左键旋转检测框。",
}
