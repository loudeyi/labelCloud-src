# labelCloud（电线/电线杆辅助标注分支）

在点云中标注三维检测框 —— 基于 [labelCloud](https://github.com/ch-sa/labelCloud) 的分支，
增加了面向**电线（wire）与电线杆（pole）**的半自动标注辅助功能。

> 状态：开发中。完整功能清单见工作仓库的 `.scratch/labelcloud-assist/spec.md`。

## 安装（editable）

```bash
python3.8 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/labelCloud --version
```

## 运行

```bash
./run_labelcloud.sh          # 使用脚本里配置的工作目录
```
