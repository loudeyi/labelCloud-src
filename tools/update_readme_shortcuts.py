#!/usr/bin/env python3
"""Regenerate the shortcut tables inside both READMEs from the live keymap.

The READMEs embed the shortcut list between ``<!-- BEGIN SHORTCUTS -->`` and
``<!-- END SHORTCUTS -->`` markers. Keeping them in sync by hand is exactly the
kind of chore that rots, so this script regenerates the block:

* ``README.md`` gets the English labels from ``control/keymap.py``,
* ``README_zh_cn.md`` gets the Chinese ones out of
  ``labelCloud/i18n/translations_zh_cn.py``.

``tests/check_assist.py`` fails when the English block is stale, so run this after
touching the binding table.

Usage::

    python tools/update_readme_shortcuts.py [--check]
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

BEGIN = "<!-- BEGIN SHORTCUTS -->"
END = "<!-- END SHORTCUTS -->"


def translations() -> dict:
    namespace: dict = {}
    source = REPO / "labelCloud" / "i18n" / "translations_zh_cn.py"
    exec(compile(source.read_text(), str(source), "exec"), namespace)  # noqa: S102
    return namespace["TRANSLATIONS"]


def build_block(translate=None) -> str:
    from labelCloud.control.keymap import KeyMap

    lines = [BEGIN, ""]
    for group, bindings in KeyMap().groups():
        title = translate(group) if translate else group
        lines.append(f"### {title}")
        lines.append("")
        header_keys = translate("Keys") if translate else "Keys"
        header_action = translate("Action") if translate else "Action"
        lines.append(f"| {header_keys} | {header_action} |")
        lines.append("| --- | --- |")
        for binding in bindings:
            label = translate(binding.label) if translate else binding.label
            lines.append(f"| `{binding.sequence}` | {label} |")
        lines.append("")
    lines.append(END)
    return "\n".join(lines)


def replace_block(path: Path, block: str) -> bool:
    text = path.read_text()
    if BEGIN not in text or END not in text:
        raise SystemExit(f"error: {path.name} has no shortcut markers")
    head, rest = text.split(BEGIN, 1)
    _old, tail = rest.split(END, 1)
    new_text = head + block + tail
    if new_text == text:
        return False
    path.write_text(new_text)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 when out of date")
    args = parser.parse_args()

    table = translations()
    pairs = [
        (REPO / "README.md", build_block()),
        (
            REPO / "README_zh_cn.md",
            build_block(lambda text: table.get(text, text)),
        ),
    ]
    stale = []
    for path, block in pairs:
        if not replace_block(path, block):
            continue
        stale.append(path.name)
        print(f"updated {path.name}")
    if not stale:
        print("shortcut tables are up to date")
    elif args.check:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
