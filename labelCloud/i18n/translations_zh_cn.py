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
    # carry a box forward + multi-frame overlay
    "Carry This Box Forward to the End [Ctrl+Shift+E]": "把当前框带到后续帧直到目标消失 [Ctrl+Shift+E]",
    "Carry the box forward through the next frames": "把当前框带到后续帧",
    "Follows the active box through the following frames, writing it where\nthe object is still there, and stops when its points are gone.": (
        "把当前框逐帧带到后面：目标还在就写入，点数没了就自动停止。"
    ),
    "Overlay previous frames:": "叠加前几帧：",
    "How many previous frames to overlay (0 = off).": "叠加多少帧之前的点云（0 = 关闭）。",
    "Draws the points of the previous frames in a dim colour, so an object that is only partly visible in this frame can be seen as a whole. The data has no ego pose, so the copies shift while the vehicle moves: this is a viewing aid, not a merged cloud.": (
        "把前几帧的点用暗色叠加上去，这一帧只看得到一部分的目标（被树挡住的杆、断续的电线）就能看全。"
        "数据没有位姿，车一动副本会错开 —— 这是观察辅助，不是合并后的点云。"
    ),
    "Propagation is still running ...": "传播还在运行中 …",
    "Select a box first: it will be carried forward.": "请先选中一个检测框，程序会把它带到后续帧。",
    "There are no later frames.": "后面没有帧了。",
    "Carrying the box forward through the next frames ...": "正在把检测框带到后续帧 …",
    "Propagating: frame %s/%s, %s written.": "传播中：第 %s/%s 帧，已写入 %s 帧。",
    "Propagated to %s frames (%s skipped): %s.": "已向后写入 %s 帧（跳过 %s）：%s。",
    "Propagation failed - see the log for details.": "传播失败，详见日志。",
    "Overlaying the %s previous frames.": "已叠加前 %s 帧。",
    "Overlay off.": "已关闭叠加。",
    # refit settings
    "Refit ...": "重拟合设置 …",
    "How far Ctrl+R looks for points, and when it trims empty stretches.": (
        "Ctrl+R 往外找多远、以及什么时候把没有点的空段剪掉。"
    ),
    "Refit Settings": "重拟合设置",
    "Look this far beyond the box:": "在框外再多找：",
    "A point further than this is not part of the object:": "离目标超过这个距离的点就不算它的一部分：",
    "Trim empty stretches longer than:": "剪掉超过这个长度的空段：",
    "Ignore clusters smaller than:": "忽略小于这个点数的碎块：",
    " points": " 个点",
    "Also re-fit the cross-section (off keeps the size you set)": (
        "同时重新拟合截面尺寸（关闭则保留你设定的尺寸）"
    ),
    "Raise \"look beyond the box\" and \"not part of the object\" when the "
    "refit leaves points out; lower \"trim empty stretches\" when the box "
    "covers a section without points. Ctrl+Shift+R applies the settings to "
    "the active box.": (
        "拟合漏点时，把「在框外再多找」和「不算它的一部分」两个值调大；框住空段时，"
    "把「剪掉空段」调小。Ctrl+Shift+R 用当前设置再拟合一次。"
    ),
    "Restore defaults": "恢复默认",
    "Refit: length %.2f -> %.2f, height %.2f -> %.2f m.": (
        "重拟合：长度 %.2f → %.2f，高度 %.2f → %.2f 米。"
    ),
    "Refit again after changing the refit settings": "用新的设置再拟合一次",
    # session panel + prediction settings (right panel)
    "Frame and saving": "本帧与保存",
    "Activity log": "活动日志",
    "Prediction ...": "预测设置 …",
    "— no point cloud loaded": "— 未载入点云",
    "Frame: <b>%s</b><br/>%s/%s in %s": "本帧：<b>%s</b><br/>%s/%s（目录 %s）",
    "Frame %s/%s · <b>%s</b>": "第 %s/%s 帧 · <b>%s</b>",
    "Saving: %s": "保存：%s",
    "Recent:": "最近：",
    "Prediction: off": "预测：关",
    "Prediction: on (%s)": "预测：开（%s）",
    "Prediction: on · %s": "预测：开 · %s",
    "adaptive, %s%% floor": "自适应，下限 %s%%",
    "adaptive %s%%": "自适应 %s%%",
    "fixed %s%%": "固定 %s%%",
    "✓ saved · %s": "✓ 已保存 · %s",
    "drop below %s%% of the previous count": "低于上一帧点数的 %s%% 就丢弃",
    "Next-Frame Prediction": "下一帧预测设置",
    "Predict even when the frame already has its own labels": "下一帧已有标注框时也预测",
    "Follow the object's motion (extrapolate from the last frames)": (
        "跟随目标运动（按前几帧外推位置与朝向）"
    ),
    "Carry forward writes this many frames:": "一键向后带多少帧：",
    "Carry boxes into the next frame": "把本帧的检测框带到下一帧",
    "Show them as unconfirmed proposals (Enter confirms)": "先作为未确认候选（按 Enter 确认）",
    "Re-fit each prediction to the points inside it": "每个预测框按框内点重新拟合",
    "Adaptive threshold (compare with the object's own history)": "自适应阈值（与该目标自己的历史比较）",
    "Adaptive sensitivity (mean - k x deviation):": "自适应灵敏度（均值 − k×标准差）：",
    "Drop when fewer than this share of the previous points:": "框内点数低于上一帧的这个比例就丢弃：",
    "... and always below this absolute count:": "… 并且绝对点数低于这个值也丢弃：",
    "Example: with 50 %, a pole whose points halve between two frames is "
    "dropped, so it is not predicted once it is behind the vehicle. The "
    "adaptive threshold follows each object separately and is usually the "
    "better choice.": (
        "举例：设为 50% 时，两根帧之间点数减半的杆会被丢弃 —— 它已经到车后面了，不该再预测。"
        "自适应阈值会分别跟踪每个目标，通常更省心。"
    ),
    # save indicator states (context StatusManager)
    "● unsaved changes": "● 有未保存修改",
    "✓ saved": "✓ 已保存",
    "✗ save FAILED": "✗ 保存失败",
    "— not saved yet": "— 尚未保存",
    "— unchanged, nothing to write": "— 未修改，无需写盘",
    "This frame was not edited, so nothing is written to %s.": (
        "这一帧没有改动，因此不会写入 %s。"
    ),
    # pointer mode, save indicator, next-frame class
    "Pointer (no drawing)": "指针（不建框）",
    "Leave the drawing modes: the mouse only navigates the point cloud again. [Esc]": (
        "退出建框模式：鼠标只用来浏览点云。[Esc]"
    ),
    "New boxes in next frames:": "下一帧新框类别：",
    "Class every new box gets when you move to the next frames, so one pass can label poles and the next pass wires.": (
        "切到下一帧后新建的框默认用这个类别 —— 这样你可以一遍只标杆、下一遍只标线。"
    ),
    "Class used for new boxes frame after frame (persists across frames).": (
        "后续各帧新建框使用的类别（跨帧保持）。"
    ),
    "Follow the active / default class": "跟随当前/默认类别",
    "Click to see where the labels were saved.": "点击查看标注保存到了哪里。",
    "Save Log": "保存日志",
    "Activity Log": "活动日志",
    "▸ loaded %s%s": "▸ 已载入 %s%s",
    "What": "类型",
    "loaded": "载入",
    "ok": "成功",
    "Predict Boxes for the Next Frame [Ctrl+Shift+P]": "预测下一帧的检测框 [Ctrl+Shift+P]",
    "Carries the boxes of this frame into the next one, keeps their size and\ndrops the ones whose points are gone.": (
        "把本帧的检测框带到下一帧：尺寸保持，位置跟着点走；框内点明显变少的目标不再预测。"
    ),
    "Predicted %s boxes from the previous frame (%s dropped).": (
        "已从上一帧预测 %s 个检测框（丢弃 %s 个）。"
    ),
    "No box predicted: the objects are no longer there.": "没有可预测的检测框：目标已经不在视野里。",
    "Next-frame prediction enabled.": "已开启下一帧预测。",
    "Next-frame prediction disabled.": "已关闭下一帧预测。",
    "Toggle next-frame prediction": "开关下一帧预测",
    "Show the activity log": "显示活动日志",
    "Loading a frame, and every write of an edited frame, is listed here. "
    "The status bar shows the most recent of each.": (
        "每次载入点云、以及每次写出修改过的帧都会记在这里；状态栏显示最近的一条。"
    ),
    "Save Log ... [Ctrl+Shift+S]": "保存日志 … [Ctrl+Shift+S]",
    "Shows where and when the labels of the recent frames were written.": (
        "显示最近各帧的标注写入时间与路径。"
    ),
    "Show the save log": "显示保存日志",
    "Label folder: %s": "标注目录：%s",
    "Time": "时间",
    "Result": "结果",
    "File": "文件",
    "saved": "已保存",
    "FAILED: %s": "失败：%s",
    "Every frame is written when you move to another frame or press Ctrl+S; "
    "autosave writes the current frame periodically.": (
        "切帧和 Ctrl+S 都会写盘；自动保存会定期写入当前帧。"
    ),
    "Keys": "按键",
    "Action": "功能",
    # group selection (F-11b)
    "Group selection: %s boxes.": "已选中 %s 个检测框（成组操作）。",
    "Changed %s boxes.": "已同时修改 %s 个检测框。",
    "Deleted %s boxes.": "已删除 %s 个检测框。",
    "Cleared the group selection.": "已清空成组选择。",
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
    "—": "—",
    "+": "+",
    "Parameter changed by the - / + buttons below.": "下面 − / + 按钮所调整的参数。",
    "Decrease the selected parameter by one step.": "把所选参数减小一个步长。",
    "Increase the selected parameter by one step.": "把所选参数增大一个步长。",
})

TRANSLATIONS.update({
    # the parameter stepper's combo box (``Controller.STEP_PARAMETERS``)
    "X position": "X 位置",
    "Y position": "Y 位置",
    "Z position": "Z 位置",
    "Length": "长",
    "Width": "宽",
    "Height": "高",
    "Rotation X": "绕 X 旋转",
    "Rotation Y": "绕 Y 旋转",
    "Rotation Z": "绕 Z 旋转",
    # the label list's context menu
    "Change class color": "修改类别颜色",
    "Delete label": "删除标注",
    "Save points inside as": "把框内点另存为",
    "NOT saved: this file holds labels in another format (see the log). Nothing was written.": (
        "未保存：该文件里是另一种格式的标注（见日志），本次没有写入任何内容。"
    ),
    "Set a keyframe first (Ctrl+Shift+I) in the earlier frame.": (
        "请先在前面的一帧按 Ctrl+Shift+I 设置关键帧。"
    ),
})

#: Keyframe interpolation (feature: fill the frames between two keyframes).
TRANSLATIONS.update({
    "Keyframe: none (Ctrl+Shift+I sets one)": "关键帧：未设置（Ctrl+Shift+I 设置）",
    "Keyframe: frame %s · %s": "关键帧：第 %s 帧 · %s",
    "Set Keyframe Here [Ctrl+Shift+I]": "在此设置关键帧 [Ctrl+Shift+I]",
    "Remembers the active box as the first keyframe of an interpolation.": (
        "把当前检测框记为插值的第一个关键帧。"
    ),
    "Interpolate from the Keyframe to Here [Ctrl+Shift+K]": "从关键帧插值到这里 [Ctrl+Shift+K]",
    "Fills the frames between the two keyframes, moving and rotating the box\n"
    "across the gap and checking each frame for the object's points.": (
        "填充两个关键帧之间的所有帧：让检测框在间隔中平移和旋转，\n"
        "并在每一帧核对目标点云是否存在。"
    ),
    "Select a box first: it becomes the first keyframe.": "请先选中一个检测框，它将成为第一个关键帧。",
    "Keyframe 1 set on frame %s (%s).": "已把第 %s 帧的 %s 设为关键帧 1。",
    "A fill job is still running ...": "已有填充任务正在运行……",
    "Select the box of the second keyframe in this frame.": "请在本帧选中第二个关键帧的检测框。",
    "The second keyframe must be a later frame.": "第二个关键帧必须在更后面的帧上。",
    "The two keyframes are adjacent: nothing to fill.": "两个关键帧相邻，中间没有需要填充的帧。",
    "Interpolating %s frames between the keyframes ...": "正在插值两个关键帧之间的 %s 帧……",
    "Interpolation: %s": "插值：%s",
    "Set the first keyframe for interpolation": "设置插值的第一个关键帧",
    "Fill the frames between the keyframe and here": "填充关键帧到当前帧之间的所有帧",
})

#: Quality check (Ctrl+Shift+Q) — the window and its issue kinds.
TRANSLATIONS.update({
    "Quality Check": "标注质检",
    "Quality Check ... [Ctrl+Shift+Q]": "标注质检 … [Ctrl+Shift+Q]",
    "Check the labels of the whole folder for mistakes": "检查整个文件夹里的标注有没有问题",
    "Reads every label file and lists the boxes that look wrong: sizes far from\n"
    "the usual size of their class, duplicates, tilted poles, wires whose long axis is\n"
    "in the wrong field and boxes that cover no points.": (
        "读一遍全部标注文件，列出可疑的框：尺寸和同类别常见尺寸差太多的、重复的、"
        "该竖直却歪了的、长轴写错字段的电线，以及框内没有点的框。"
    ),
    "Scanning the label files ...": "正在扫描标注文件……",
    "Show": "显示",
    "All issues": "全部问题",
    "Check the points of the current frame (slower)": "同时检查当前帧的点云（较慢）",
    "Check again": "重新检查",
    "Frame": "帧",
    "Issue": "问题",
    "Detail": "说明",
    "Go to Frame": "跳到该帧",
    "The check failed: %s": "检查失败：%s",
    "%s of %s frames hold boxes (%s boxes)": "%s / %s 帧有标注（共 %s 个框）",
    "Frames with at least one issue: %s": "至少有一处问题的帧数：%s",
    "Double-click a row (or press Go to Frame) to open that frame. "
    "The check never edits your labels.": (
        "双击一行（或按“跳到该帧”）即可打开那一帧。质检只读，绝不改动你的标注。"
    ),
    "There is no frame %s.": "没有第 %s 帧。",
    "not one of the configured classes": "不属于已配置的类别",
    "size %(length).2f x %(width).2f x %(height).2f m is not a real object": (
        "尺寸 %(length).2f × %(width).2f × %(height).2f m 不可能是真实目标"
    ),
    "tilted by %(tilt).1f deg, but this class is always upright": (
        "歪了 %(tilt).1f°，但该类别要求始终竖直"
    ),
    "long axis is in length (%(length).2f m) instead of width (%(width).2f m)": (
        "长轴写进了 length（%(length).2f m），应该在 width（%(width).2f m）"
    ),
    "%(axis)s %(value).2f m is %(ratio).1fx the usual %(expected).2f m": (
        "%(axis)s 为 %(value).2f m，是同类别常见值 %(expected).2f m 的 %(ratio).1f 倍"
    ),
    "two %(name)s boxes %(distance).2f m apart": "两个 %(name)s 框相距只有 %(distance).2f m",
    "overlaps the next %(name)s box by %(share).0f %%": (
        "与下一个 %(name)s 框重叠 %(share).0f%%"
    ),
    "only %(count)s point(s) inside": "框内只有 %(count)s 个点",
    "cannot be read: %(error)s": "读不出来：%(error)s",
    "the quality check reads 'centroid' JSON labels; this session uses '%s'": (
        "质检只能读 'centroid' JSON 标注，当前会话用的是 '%s'"
    ),
    "Class not in _classes.json": "类别不在 _classes.json 里",
    "Impossible size": "尺寸不可能是真的",
    "Tilted although the class is upright": "类别要求竖直，但框是斜的",
    "Long axis in length instead of width": "长轴写进了 length 而不是 width",
    "Size far from the usual size of its class": "尺寸和同类别的常见尺寸差太多",
    "Duplicate or overlapping box": "重复或重叠的框",
    "Covers (almost) no points": "框里（几乎）没有点",
    "Label file cannot be read": "标注文件读不出来",
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
