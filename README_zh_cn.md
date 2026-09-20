# labelCloud — 电线 / 电线杆辅助标注分支

> 基于 [labelCloud](https://github.com/ch-sa/labelCloud)（GPL-3.0）的分支，面向**电线（`wire`）**
> 与**电线杆（`pole`）**的激光点云序列标注。保留 labelCloud 的文件格式，补上真正省时间的部分 ——
> 尤其是"同一根杆在连续上百帧里反复出现"这件事。

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.8-blue.svg)
![Platform](https://img.shields.io/badge/platform-linux-lightgrey.svg)

[English](README.md) · **简体中文** · [更新日志](CHANGELOG.md)

---

## 为什么会有这个分支

在 labelCloud 1.1.1 里手工标电线杆和电线慢，原因很具体，这个分支逐条解决：

| 原来的问题 | 现在的做法 |
| --- | --- |
| 新建框固定 0.75 × 0.55 × 0.15 m，而杆高 8~18 m、线长 5~21 m | **按类别尺寸模板**（`Ctrl+T`）+ **点一下自动拟合**（`Ctrl+G`） |
| 框只能一个一个调，改错还回不去 | **撤销/重做**、**复制/粘贴/原地复制**、**沿框自身轴微调**、**鼠标拖拽**、**± 步进器** |
| 自动预标注一次给一整个目录的框，只能逐帧手删 | **候选框复核队列**：`Ctrl+Shift+G` 预标注本帧，`Enter` 确认并自动跳到下一个 |
| 5~10 Hz 序列里同一根杆每帧重复劳动 | **跨帧存活的剪贴板**、类别模板，以及关键帧插值的接口准备 |
| 好几个框常常要做同样的修正 | **成组编辑**：`Shift`+左键点选加入一组，之后移动/旋转/缩放/改类别/删除/翻转都同时作用在整组上（`Esc` 清空） |

界面支持**中英文切换**（`设置 → 语言`），**切换即时生效，无需重启**。

## 辅助标注功能

| 功能 | 快捷键 | 说明 |
| --- | --- | --- |
| **一键拟合** | `Ctrl+G` | 在目标上点一下：区域生长 + 拟合成当前类别的有向框 |
| **重新拟合** | `Ctrl+R` | 把当前框重新拟合到框内的点，**保留你设定的截面尺寸** |
| **吸附地面** | `Ctrl+E` | 把框底吸附到当地地面 |
| **预标注本帧** | `Ctrl+Shift+G` | 后台线程跑离线杆/线检测，候选框排队待确认 |
| **确认候选** | `Enter` | 把橙色虚线候选变成正式框，并跳到下一个 |
| **遍历候选** | `Ctrl+←` / `Ctrl+→` | 上一个 / 下一个未确认候选 |
| **拒绝候选** | `Ctrl+Shift+Del` | 一次清掉本帧所有未确认候选 |
| **翻转 180°** | `Ctrl+U` | 电线朝向经常有歧义，一键翻转 |
| **聚焦视图** | `Ctrl+F` | 只画当前框内的点（密集帧里找杆） |
| **数据集统计** | `Ctrl+I` | 已标注 / 确认无目标 / 未标注帧数，以及各类别框数 |

候选框用**橙色虚线**绘制，绝不会和已确认的框混淆；确认一个框只要一个键，整批拒绝也只要一个键。

## 操作与数据安全功能

| 功能 | 位置 | 说明 |
| --- | --- | --- |
| **指针模式** | 建框按钮旁边，或按 `Esc` | 退出所有建框模式，鼠标回到"只浏览点云"。建框按钮再点一次也会关闭；**拖动不会建框** —— 只有真正的点击（位移 ≤ 5 像素）才会拟合 |
| **下一帧新框类别** | "下一帧新框类别"下拉框 | 固定后续各帧新建框的类别：可以这一遍只标杆、下一遍只标线，不用每帧重新选类别 |
| **保存状态指示** | 状态栏右侧 | `✓ 已保存 13:38:09  labels_lc/xxx.json`、`● 有未保存修改`、红色 `✗ 保存失败`；鼠标悬停显示完整路径 |
| **保存日志** | 点状态栏指示、`Ctrl+Shift+S`、或 *文件 → 保存日志* | 列出最近写入的时间、结果与完整路径 |
| **自动保存** | 每 60 秒（`LABEL/autosave_interval_seconds`） | **只在真的改过东西时才写盘**；只是翻过去的帧**完全不写**，想把它记为"已确认无目标"就按一次 `Ctrl+S` |
| **成组编辑** | `Shift`+左键点选 | 移动/旋转/缩放/改类别/删除/翻转同时作用于整组 |
| **撤销/重做** | `Ctrl+Z` / `Ctrl+Shift+Z` | 一次拖动、一串连按都算一步，撤销一次回到操作前 |
| **尺寸锁定 + 模板** | `Ctrl+L` / `Ctrl+T` | 锁定已拟合好的尺寸；模板固定杆的截面与线的截面 |

## 检测框约定

拟合代码严格遵循本项目标注数据里的约定：

| 类别 | 约定 |
| --- | --- |
| `pole` | 竖直框（`rz = 0`），**底部贴当地地面**，截面用模板（长 ≈ 2.6 m、宽 ≈ 4.0 m），高度随结构 |
| `wire` | **长轴写在 `dimensions.width`**（不是 `length`），yaw 使框的局部 **+y** 沿电线走向 |

逐类行为写在类别文件 `_classes.json` 里：

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

* `z_rotation_only`：杆只需要绕 z 的偏航；电线是悬链线、不平行于地面，所以放开俯仰/横滚。
  填 `null` 或不写 = 跟随全局 `USER_INTERFACE/z_rotation_only`。
* `default_dimensions`：某维为 `null` 表示"保留当前值"——所以杆的模板可以只固定截面，高度留给结构本身。

导出格式与上游 labelCloud 完全一致：`folder` / `filename` / `path` /
`objects[{name, centroid, dimensions, rotations}]`，角度为**度**（`centroid_abs`）。
读取时**逐文件识别编码**：编码不同（如 8 角点 `vertices`）的文件**绝不会被覆盖**，重写前还会留 `.bak` 备份。

## 安装

```bash
git clone <本仓库> labelCloud-src
cd labelCloud-src

python3.8 -m venv .venv
.venv/bin/pip install -e .

.venv/bin/labelCloud --version
```

依赖：`numpy<2`、`open3d`、`PyOpenGL`、`PyOpenGL-accelerate`、`PyQt5>=5.15.7`、`scipy`。
在 Python 3.8 / Linux + 可用的 OpenGL 显示环境下验证。

## 快速开始

```bash
./run_labelcloud.sh --list                    # 列出 DATASETS_ROOT 下的数据集
./run_labelcloud.sh                           # 用默认数据集启动
./run_labelcloud.sh 2026_0416 labels_lc       # 指定数据集与标注目录
DRY_RUN=1 ./run_labelcloud.sh                 # 只重新生成 config.ini，不启动界面
```

启动脚本把运行期文件集中到一个工作目录，不再散落在"碰巧启动时的那个目录"：

```
labelcloud-work/
├── config.ini          每次启动重新生成（旧的存为 config.ini.bak）
└── _classes.json       pole/wire 类别、颜色与模板
```

如果标注目录里是 8 角点 `vertices` 文件、而当前会话按 `centroid` 读取，脚本会**拒绝打开** ——
否则那些帧会显示成"没有框"，并在下一次自动保存时被改写成空文件。

## 推荐工作流

```
        ┌──────────────────────── 一帧之内 ────────────────────────┐
        │                                                          │
 Ctrl+Shift+G ──► 候选框（橙色虚线） ──► Enter 确认一个             │
        │              │                        │                 │
        │              └── Ctrl+→ 遍历 ──────────┘                 │
        │              └── Ctrl+Shift+Del 整批拒绝                  │
        │                                                          │
 没有候选？ ──► Ctrl+G 点一下拟合 ──► Ctrl+R 重拟合 ──► Ctrl+E 贴地  │
        │                                                          │
        └──────────────► Ctrl+S / 自动保存 ──► 下一帧 ─────────────┘
                  （Ctrl+Z 撤销，Ctrl+C / Ctrl+V 复用框）
```

0. 平时停在**指针模式**浏览，要拟合时再点"辅助拟合"，按 `Esc` 或点指针按钮即可退出。
1. **预标注本帧**，然后用 `Enter` 一路确认候选框。
2. 漏掉的目标**点一下**（`Ctrl+G`）—— 框是拟合到点上的，不是固定尺寸丢下来的。
3. 用 `Ctrl+R`（重拟合）、`Ctrl+E`（贴地）和 `U/J/M/;`（沿框自身轴微调）收尾。
4. 好的框 `Ctrl+C` 复制、下一帧 `Ctrl+V` 粘贴 —— 剪贴板**故意设计成跨帧存活**。

## 快捷键一览

`Shift` 把步长 ×**10**，`Alt` 把步长 ÷**10**（移动 / 旋转 / 缩放类按键）。
所有快捷键都可以在 `config.ini` 的 `[SHORTCUTS]` 段里改，例如 `copy_box = Ctrl+Shift+C`；
程序里按 `F1` 也能弹出同一张表（已中文化）。

<!-- BEGIN SHORTCUTS -->

### 点云

| 按键 | 功能 |
| --- | --- |
| `R / Left` | 加载上一帧点云 |
| `F / Right` | 加载下一帧点云 |
| `P / Home` | 重置点云视角 |
| `Ctrl+S` | 保存标注 |

### 检测框

| 按键 | 功能 |
| --- | --- |
| `W` | 检测框后移 |
| `S` | 检测框前移 |
| `A` | 检测框左移 |
| `D` | 检测框右移 |
| `Q` | 检测框上移 |
| `E` | 检测框下移 |
| `U` | 沿检测框自身 x 轴正向移动 |
| `J` | 沿检测框自身 x 轴负向移动 |
| `M` | 沿检测框自身 y 轴正向移动 |
| `;` | 沿检测框自身 y 轴负向移动 |
| `Z` | 绕 Z 轴逆时针旋转 |
| `X` | 绕 Z 轴顺时针旋转 |
| `C` | 绕 Y 轴逆时针旋转 |
| `V` | 绕 Y 轴顺时针旋转 |
| `B` | 绕 X 轴逆时针旋转 |
| `N` | 绕 X 轴顺时针旋转 |
| `I` | 增大长度 |
| `O` | 减小长度 |
| `K` | 增大宽度 |
| `L` | 减小宽度 |
| `,` | 增大高度 |
| `.` | 减小高度 |

### 标注

| 按键 | 功能 |
| --- | --- |
| `T / Up` | 选中上一个检测框 |
| `G / Down` | 选中下一个检测框 |
| `Y` | 切换为上一个类别 |
| `H` | 切换为下一个类别 |
| `Del` | 删除当前检测框 |
| `Esc` | 取消绘制 / 取消选中 |
| `Ctrl+Z` | 撤销 |
| `Ctrl+Shift+Z / Ctrl+Y` | 重做 |
| `Ctrl+C` | 复制当前检测框 |
| `Ctrl+V` | 粘贴检测框 |
| `Ctrl+D` | 原地复制当前检测框 |
| `Ctrl+L` | 锁定/解锁检测框尺寸 |
| `Ctrl+T` | 套用类别模板（尺寸 + 竖直朝向） |

### 辅助

| 按键 | 功能 |
| --- | --- |
| `Ctrl+G` | 在光标处的目标上拟合检测框 |
| `Ctrl+R` | 把当前检测框重新拟合到框内点 |
| `Ctrl+Shift+G` | 自动预标注本帧，候选框排队待确认 |
| `Return / Enter` | 确认当前候选框 |
| `Ctrl+Right` | 下一个未确认的候选框 |
| `Ctrl+Left` | 上一个未确认的候选框 |
| `Ctrl+Shift+Del` | 拒绝本帧全部候选框 |
| `Ctrl+U` | 把检测框翻转 180° |
| `Ctrl+E` | 把当前检测框吸附到地面 |

### 帮助

| 按键 | 功能 |
| --- | --- |
| `Ctrl+I` | 显示数据集统计 |
| `Ctrl+Shift+S` | 显示保存日志 |
| `F1` | 显示本快捷键表 |

### 视图

| 按键 | 功能 |
| --- | --- |
| `Ctrl+F` | 只显示当前框内的点 |

<!-- END SHORTCUTS -->

鼠标：拖动框体=平移，拖动悬停的面=缩放，中键拖动=绕 Z 旋转，双击框=选中，
**`Shift`+左键点选把框加入/移出成组选择**（状态栏会显示组内数量）。选中多个框时，
移动、旋转、缩放、改类别、删除、翻转都会同时作用于整组。按住 `Ctrl` 时保持 labelCloud 原有行为不变。

## 配置

`config.ini` 从**当前工作目录**读取，并与 `labelCloud/resources/default_config.ini` 合并，
所以升级新增的配置项不会让旧文件报错。除上游选项外新增：

```ini
[LABEL]
; 每 N 秒自动保存当前帧（0 = 关闭）
autosave_interval_seconds = 60

[USER_INTERFACE]
; system = 跟随系统语言，也可写 en 或 zh_CN
language = system

[ASSIST]
; 离线杆/线预标注工具所在目录；留空即关闭该功能
polewire_path = /path/to/tools/pole_wire_autolabel
classes = pole,wire
; 杆的参数档：recall（宁可多框，少漏）/ strict（框少、更干净）
pole_profile = recall

[SHORTCUTS]
; 任何命令都能改键，例如：
; copy_box = Ctrl+Shift+C
```

## 配套的离线工具

`Ctrl+Shift+G` 用的预标注来自一个独立的纯几何工具（`tools/pole_wire_autolabel`：
地面模型、树冠排除、邻域 PCA 提线）。**本仓库不依赖它** —— 没有它时该按钮会提示失败，
其余功能全部照常。

在 1292 帧数据集上抽 12 帧实测：程序内调用与离线工具输出**逐框一致**
（`pole` 召回 0.92 / 精度 0.79；`wire` 召回 0.33 / 精度 1.00，命中框 BEV IoU 均值 0.74），
单帧 0.03~1.18 s，且在**后台线程**里跑，不卡界面。

## 开发

```bash
# 回归检查（不需要 pytest，每条用例在独立工作目录里跑）
.venv/bin/python tests/check_assist.py

# 新增文案后重建中文翻译
.venv/bin/python tools/update_translations.py
```

`tests/check_assist.py` 覆盖：类别配置兼容性、逐文件编码识别与防误覆盖、语言切换、快捷键表、
撤销与合并、模板与锁定、合成数据上的杆/线拟合、候选队列、数据集统计、保存失败处理。

新增可翻译文案的做法：在 `QObject` 里用 `self.tr(...)`，非 `QObject` 用
`QCoreApplication.translate("labelCloud", ...)`；把中文写进
`labelCloud/i18n/translations_zh_cn.py`，再跑一次 `tools/update_translations.py`。
注意：**`pylupdate5` 会忽略源字符串后面带尾逗号的 `translate()` 调用**。

## 兼容性与边界

* 标注文件与上游 labelCloud 字节级兼容（`centroid_abs`、角度为度）。
* `centroid_rel`（弧度）、8 角点 `vertices`、KITTI 标注目录都能正确读取；编码不同的目录不会被误覆盖。
* 角度单位只在**能从数值证明**时才判定（|角度| > 2π 必为度）；有歧义时按配置来，不猜。
* 拟合是**纯几何**的：不需要模型，也不假装自己是模型。密林里杆被植被包住导致召回下降的场景，
  才是点级语义分割该上场的地方。
* 程序内预标注是 CPU、逐帧的。
* 拟合有合理性保护：点在树篱/路缘/墙上会被**拒绝**（不会给出一个巨大的框），超过 35 m 的"电线"按泄漏区域处理。

## 致谢与许可

派生自 Christoph Sager 的 [ch-sa/labelCloud](https://github.com/ch-sa/labelCloud) 1.1.1。
采用 **GNU General Public License v3.0 或更新版本** —— 见 [LICENSE](LICENSE)。
作为衍生作品，再分发必须沿用同一许可。
