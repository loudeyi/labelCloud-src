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

#: Labels of the shortcut table in ``control/keymap.py`` (context ``keymap``),
#: plus the strings of the F1 dialog itself.
KEYMAP_LABELS = {
    # groups
    "Point Cloud": "点云",
    "Bounding Box": "检测框",
    "Labels": "标注",
    "View": "视图",
    "Help": "帮助",
    # point cloud
    "Load previous point cloud": "加载上一帧点云",
    "Load next point cloud": "加载下一帧点云",
    "Reset the point cloud view": "重置点云视角",
    "Save labels": "保存标注",
    # movement
    "Move bounding box backward": "检测框后移",
    "Move bounding box forward": "检测框前移",
    "Move bounding box left": "检测框左移",
    "Move bounding box right": "检测框右移",
    "Move bounding box up": "检测框上移",
    "Move bounding box down": "检测框下移",
    "Move along the box's own x-axis": "沿检测框自身 x 轴正向移动",
    "Move against the box's own x-axis": "沿检测框自身 x 轴负向移动",
    "Move along the box's own y-axis": "沿检测框自身 y 轴正向移动",
    "Move against the box's own y-axis": "沿检测框自身 y 轴负向移动",
    # rotation / scaling
    "Rotate around z-axis counterclockwise": "绕 Z 轴逆时针旋转",
    "Rotate around z-axis clockwise": "绕 Z 轴顺时针旋转",
    "Rotate around y-axis counterclockwise": "绕 Y 轴逆时针旋转",
    "Rotate around y-axis clockwise": "绕 Y 轴顺时针旋转",
    "Rotate around x-axis counterclockwise": "绕 X 轴逆时针旋转",
    "Rotate around x-axis clockwise": "绕 X 轴顺时针旋转",
    "Increase length": "增大长度",
    "Decrease length": "减小长度",
    "Increase width": "增大宽度",
    "Decrease width": "减小宽度",
    "Increase height": "增大高度",
    "Decrease height": "减小高度",
    # selection / editing
    "Select previous bounding box": "选中上一个检测框",
    "Select next bounding box": "选中下一个检测框",
    "Assign previous class": "切换为上一个类别",
    "Assign next class": "切换为下一个类别",
    "Delete the active bounding box": "删除当前检测框",
    "Cancel drawing / deselect": "取消绘制 / 取消选中",
    "Undo": "撤销",
    "Redo": "重做",
    "Copy the active bounding box": "复制当前检测框",
    "Paste the copied bounding box": "粘贴检测框",
    "Duplicate the active bounding box in place": "原地复制当前检测框",
    "Lock/unlock the box dimensions": "锁定/解锁检测框尺寸",
    "Apply the class template (dimensions + upright)": "套用类别模板（尺寸 + 竖直朝向）",
    "Show only the points inside the active box": "只显示当前框内的点",
    "Show this shortcut list": "显示本快捷键表",
}

TRANSLATIONS.update(KEYMAP_LABELS)

TRANSLATIONS.update({
    # status messages of the new editing commands
    "The box size is locked (Ctrl+L unlocks it).": "检测框尺寸已锁定（Ctrl+L 解锁）。",
    "Undone the last change.": "已撤销上一步操作。",
    "Nothing to undo.": "没有可撤销的操作。",
    "Redone the last change.": "已重做。",
    "Nothing to redo.": "没有可重做的操作。",
    "Copied the box; Ctrl+V pastes it (also in the next frame).": (
        "已复制检测框；Ctrl+V 粘贴（切到下一帧也能粘贴）。"
    ),
    "Pasted the box.": "已粘贴检测框。",
    "Nothing to paste: copy a box first.": "没有可粘贴的检测框，请先复制。",
    "Box size locked (Ctrl+L).": "检测框尺寸已锁定（Ctrl+L）。",
    "Box size unlocked (Ctrl+L).": "检测框尺寸已解锁（Ctrl+L）。",
    "Select a box first to focus on its points.": "请先选中一个检测框，再聚焦显示框内点。",
    "No points inside the active box to focus on.": "当前检测框内没有点，无法聚焦。",
    "Focus on the active box (Ctrl+F shows everything again).": (
        "已聚焦到当前检测框（Ctrl+F 恢复显示全部点）。"
    ),
})

TRANSLATIONS.update({
    # assist menu + pre-annotation queue (phase 2)
    "Pre-annotate This Frame [Ctrl+Shift+G]": "自动预标注本帧 [Ctrl+Shift+G]",
    "Confirm Proposal [Enter]": "确认候选框 [Enter]",
    "Reject All Proposals [Ctrl+Shift+Del]": "拒绝全部候选框 [Ctrl+Shift+Del]",
    "Fit Box at Cursor [Ctrl+G]": "在光标处拟合 [Ctrl+G]",
    "Refit Active Box [Ctrl+R]": "重新拟合当前框 [Ctrl+R]",
    "Snap Box to Ground [Ctrl+E]": "吸附到地面 [Ctrl+E]",
    "Flip Box 180° [Ctrl+U]": "检测框翻转 180° [Ctrl+U]",
    "Dataset Statistics ... [Ctrl+I]": "数据集统计 … [Ctrl+I]",
    "Dataset Statistics": "数据集统计",
    "Pre-annotate this frame and queue the proposals": "自动预标注本帧，候选框排队待确认",
    "Confirm the proposal under review": "确认当前候选框",
    "Next unconfirmed proposal": "下一个未确认的候选框",
    "Previous unconfirmed proposal": "上一个未确认的候选框",
    "Reject all proposals in this frame": "拒绝本帧全部候选框",
    "Flip the box by 180 degrees": "把检测框翻转 180°",
    "Show dataset statistics": "显示数据集统计",
    "Pre-annotation is still running ...": "预标注还在运行中 …",
    "Running pre-annotation in the background ...": "正在后台运行预标注 …",
    "%s proposals added; Enter confirms one, Ctrl+Right jumps to the next.": (
        "已加入 %s 个候选框；Enter 确认，Ctrl+→ 跳到下一个。"
    ),
    "Pre-annotation failed - see the log for details.": "预标注失败，详见日志。",
    "Confirmed. %s proposals left in this frame.": "已确认。本帧还剩 %s 个候选框。",
    "Rejected %s proposals in this frame.": "已拒绝本帧 %s 个候选框。",
    "Scanning %s ...": "正在统计 %s …",
    "Frames found": "点云帧数",
    "Frames with boxes": "有标注框的帧",
    "Frames confirmed empty": "确认无目标的帧",
    "Frames not labelled yet": "尚未标注的帧",
    "Unreadable label files": "无法解析的标注文件",
    "Boxes in total": "检测框总数",
    "Boxes per class": "各类别检测框数",
    "This frame: %s boxes, %s of them unconfirmed proposals.": (
        "本帧：%s 个检测框，其中 %s 个是未确认的候选框。"
    ),
    "Item": "项目",
    "Count": "数量",
    "Class": "类别",
    "Boxes": "检测框数",
    # assist (phase 2)
    "Fit Box (click object)": "辅助拟合（点目标）",
    "Click a pole or a wire to fit a box around it. [Ctrl+G]": (
        "在电线杆或电线上点一下，自动拟合出检测框。[Ctrl+G]"
    ),
    "Fit a box around the object under the cursor": "在光标处的目标上拟合检测框",
    "Refit the active box to the points inside it": "把当前检测框重新拟合到框内点",
    "Fit boxes automatically and queue them for review": "自动拟合检测框并排队待确认",
    "Snap the active box onto the ground": "把当前检测框吸附到地面",
    "Assist": "辅助",
    "Click a pole or a wire to fit a box around it.": "在电线杆或电线上点一下，自动拟合出检测框。",
    "Could not fit a box here - try clicking directly on the object.": (
        "这里拟合不出检测框——请点在目标本体上。"
    ),
    "Could not fit a box here - click closer to the object.": "这里拟合不出检测框——请点得离目标更近。",
    "Move the mouse over an object first.": "请先把鼠标移到目标上。",
    "Fitted a %s box.": "已拟合一个 %s 检测框。",
    "Select a box first, then refit it.": "请先选中一个检测框，再重新拟合。",
    "Not enough points inside the box to refit it.": "框内点太少，无法重新拟合。",
    "Refit the box to the points inside it.": "已把检测框重新拟合到框内的点。",
    "Snapped the box onto the ground.": "已把检测框吸附到地面。",
    "The box already sits on the ground.": "检测框已经贴在地面上了。",
    "Saving failed - your edits are NOT on disk (see the log).": (
        "保存失败——你的修改还没写进磁盘（详见日志）。"
    ),
    "Saving failed": "保存失败",
    "The labels could not be written:\n\n%s\n\n"
    "The frame stays marked as unsaved; check the folder "
    "permissions and free space.": (
        "标注文件写入失败：\n\n%s\n\n当前帧仍标记为未保存，请检查目录权限与磁盘空间。"
    ),
    "Autosaved.": "已自动保存。",
})

#: Parameter names of the ± stepper and the new menu entry.
TRANSLATIONS.update({
    "X position": "X 坐标",
    "Y position": "Y 坐标",
    "Z position": "Z 坐标",
    "Length": "长度",
    "Width": "宽度",
    "Height": "高度",
    "Rotation X": "X 轴旋转",
    "Rotation Y": "Y 轴旋转",
    "Rotation Z": "Z 轴旋转",
    "Keyboard Shortcuts ...": "快捷键一览 …",
    "Shows every keyboard shortcut. [F1]": "显示全部快捷键 [F1]",
    # symbols are identical in both languages but must be listed so the
    # "everything is translated" check stays meaningful
    "−": "−",
    "+": "+",
    "Parameter changed by the - / + buttons below.": "下面 − / + 按钮所调整的参数。",
    "Decrease the selected parameter by one step.": "把所选参数减小一个步长。",
    "Increase the selected parameter by one step.": "把所选参数增大一个步长。",
})

#: Strings of the F1 dialog (context ``ShortcutDialog``).
TRANSLATIONS.update({
    "Keyboard Shortcuts": "快捷键一览",
    "Shift multiplies the step by %s, Alt by %s (movement, rotation and "
    "scaling keys).": "移动 / 旋转 / 缩放类按键：Shift 步长 ×%s，Alt 步长 ×%s。",
    "Any binding can be changed in the [SHORTCUTS] section of config.ini, "
    'for example "copy_box = Ctrl+C".': (
        "所有快捷键都可以在 config.ini 的 [SHORTCUTS] 段里改，例如 "
        '"copy_box = Ctrl+C"。'
    ),
})
