# labelCloud (pole/wire assist fork)

Label 3D bounding boxes in point clouds — a fork of [labelCloud](https://github.com/ch-sa/labelCloud)
extended with **semi-automatic annotation assists for power lines (wire) and utility poles (pole)**.

> Status: work in progress. The full feature list lives in
> `.scratch/labelcloud-assist/spec.md` of the working repository.

## Install (editable)

```bash
python3.8 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/labelCloud --version
```

## Run

```bash
./run_labelcloud.sh          # uses the work directory configured in the script
```
