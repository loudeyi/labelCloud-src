#!/usr/bin/env python3
"""Rebuild the Simplified-Chinese translation files.

Steps
-----
1. ``pylupdate5`` scans every module and ``.ui`` file and refreshes
   ``labelCloud/i18n/labelCloud_zh_CN.ts`` (existing translations are preserved).
2. Translations from :mod:`labelCloud.i18n.translations_zh_cn` are merged in.
3. ``lrelease`` compiles the ``.ts`` into the ``.qm`` the application loads.
4. Anything still untranslated is printed, so nothing goes missing silently.

Usage::

    python tools/update_translations.py [--check]

``--check`` exits non-zero if any string is untranslated (useful in CI); it still
rewrites the files.

Note for maintainers: ``pylupdate5`` only recognises a ``translate(...)`` call when
the source text is **not** followed by a trailing comma, and when the context and
the text are on the same line. Keep new strings in that shape or they will silently
never be extracted.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PACKAGE = REPO / "labelCloud"
I18N_DIR = PACKAGE / "i18n"
TS_FILE = I18N_DIR / "labelCloud_zh_CN.ts"
QM_FILE = I18N_DIR / "labelCloud_zh_CN.qm"
TRANSLATIONS_MODULE = I18N_DIR / "translations_zh_cn.py"

sys.path.insert(0, str(REPO))


def load_translations() -> dict:
    namespace: dict = {}
    source = TRANSLATIONS_MODULE.read_text()
    exec(compile(source, str(TRANSLATIONS_MODULE), "exec"), namespace)  # noqa: S102
    return namespace["TRANSLATIONS"]


def find_tool(name: str) -> str:
    """Prefer the tool shipped with the active interpreter's environment."""
    candidate = Path(sys.executable).parent / name
    if candidate.is_file():
        return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    print(f"error: {name} not found (install PyQt5 tools / Qt linguist)", file=sys.stderr)
    raise SystemExit(2)


def run_pylupdate() -> None:
    sources = sorted(
        str(p) for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts
    )
    ui_files = sorted(str(p) for p in (PACKAGE / "resources" / "interfaces").glob("*.ui"))
    cmd = [
        find_tool("pylupdate5"),
        "-noobsolete",
        *sources,
        *ui_files,
        "-ts",
        str(TS_FILE),
    ]
    subprocess.run(cmd, check=True, cwd=REPO)


def ensure_extra_messages(root, context_name: str, sources) -> None:
    """Add messages pylupdate5 cannot discover.

    The F1 dialog translates the labels of the binding table in
    ``control/keymap.py``. They live in a data structure rather than in a
    ``tr()`` call, so the extractor never sees them and they are injected here.
    """
    context = None
    for candidate in root.findall("context"):
        name = candidate.find("name")
        if name is not None and name.text == context_name:
            context = candidate
            break
    if context is None:
        context = ET.SubElement(root, "context")
        ET.SubElement(context, "name").text = context_name

    existing = {
        (message.find("source").text or "")
        for message in context.findall("message")
    }
    for source in sources:
        if not source or source in existing:
            continue
        message = ET.SubElement(context, "message")
        ET.SubElement(message, "source").text = source
        translation = ET.SubElement(message, "translation")
        translation.set("type", "unfinished")
        translation.text = ""
        existing.add(source)  # a source may be listed by several bindings


def merge_translations(translations: dict) -> tuple[int, int, list[str]]:
    tree = ET.parse(TS_FILE)
    root = tree.getroot()
    total = translated = 0
    missing: list[str] = []

    for context in root.findall("context"):
        for message in context.findall("message"):
            source_el = message.find("source")
            translation_el = message.find("translation")
            if source_el is None or translation_el is None:
                continue
            source = source_el.text or ""
            total += 1
            value = translations.get(source)
            if value is None:
                if (translation_el.text or "").strip():
                    translated += 1
                else:
                    missing.append(source)
                continue
            if translation_el.text != value:
                translation_el.text = value
            translation_el.attrib.pop("type", None)
            translated += 1

    tree.write(TS_FILE, encoding="utf-8", xml_declaration=True)
    return total, translated, missing


def add_keymap_messages() -> None:
    """Register the binding labels and group names of the F1 dialog."""
    from labelCloud.control.keymap import BINDINGS

    tree = ET.parse(TS_FILE)
    labels = [binding.label for binding in BINDINGS]
    groups = [binding.group for binding in BINDINGS]
    ensure_extra_messages(tree.getroot(), "keymap", labels + groups)
    tree.write(TS_FILE, encoding="utf-8", xml_declaration=True)


def add_quality_messages() -> None:
    """Register the wording of the quality check's issue kinds.

    They are a dictionary in ``view/quality_dialog.py`` rather than ``tr()`` calls, so
    pylupdate5 cannot see them (same situation as the F1 dialog's binding labels).
    """
    from labelCloud.control.quality import DETAIL_TEMPLATES
    from labelCloud.view.quality_dialog import KIND_LABELS

    tree = ET.parse(TS_FILE)
    ensure_extra_messages(
        tree.getroot(),
        "QualityDialog",
        list(KIND_LABELS.values()) + list(DETAIL_TEMPLATES.values()),
    )
    tree.write(TS_FILE, encoding="utf-8", xml_declaration=True)


def add_stepper_messages() -> None:
    """Register the labels of the parameter stepper's combo box.

    ``view/gui.py`` fills it from ``Controller.STEP_PARAMETERS``, so the nine labels
    are translated through the table rather than through ``tr()`` literals and
    pylupdate5 never sees them.
    """
    from labelCloud.control.controller import Controller

    tree = ET.parse(TS_FILE)
    ensure_extra_messages(
        tree.getroot(), "GUI", [label for _value, label in Controller.STEP_PARAMETERS]
    )
    tree.write(TS_FILE, encoding="utf-8", xml_declaration=True)


def run_lrelease() -> None:
    subprocess.run(
        [find_tool("lrelease"), str(TS_FILE), "-qm", str(QM_FILE)],
        check=True,
        cwd=REPO,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero when strings are still untranslated",
    )
    args = parser.parse_args()

    translations = load_translations()
    run_pylupdate()
    add_keymap_messages()
    add_quality_messages()
    add_stepper_messages()
    total, translated, missing = merge_translations(translations)
    run_lrelease()

    print(f"{TS_FILE.relative_to(REPO)}: {translated}/{total} strings translated")
    print(f"{QM_FILE.relative_to(REPO)}: {QM_FILE.stat().st_size} bytes")
    if missing:
        print(f"\nstill untranslated ({len(missing)}):")
        for source in missing:
            print(f"  - {source!r}")
        if args.check:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
